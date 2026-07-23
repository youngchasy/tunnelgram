package org.tunnelgram.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import java.io.File
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

class ProxyService : Service() {
    companion object {
        const val ACTION_START = "org.tunnelgram.android.action.START"
        const val ACTION_STOP = "org.tunnelgram.android.action.STOP"
        const val EXTRA_PROFILE_URI = "profile_uri"
        const val EXTRA_PORT = "listen_port"

        private const val CHANNEL_ID = "tunnelgram_proxy"
        private const val NOTIFICATION_ID = 2001
    }

    private val executor = Executors.newSingleThreadExecutor()
    private val stopping = AtomicBoolean(false)
    private val active = AtomicBoolean(false)

    @Volatile
    private var process: Process? = null

    @Volatile
    private var currentProfileName: String = ""

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        RuntimeState.update(this, false, "Запуск службы…")
        startForeground(NOTIFICATION_ID, buildNotification("Запуск локальной прокси…"))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            LogStore.append(this, "Остановка по команде пользователя")
            stopSelf()
            return START_NOT_STICKY
        }

        val profileUri = intent?.getStringExtra(EXTRA_PROFILE_URI).orEmpty().trim()
        val port = intent?.getIntExtra(EXTRA_PORT, 9443) ?: 9443
        if (profileUri.isEmpty()) {
            failAndStop("Не передана ссылка профиля")
            return START_NOT_STICKY
        }

        if (!active.compareAndSet(false, true)) {
            LogStore.append(this, "Прокси уже запущена или запускается")
            return START_NOT_STICKY
        }

        stopping.set(false)
        executor.execute {
            try {
                runProxy(profileUri, port)
            } finally {
                active.set(false)
            }
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        stopping.set(true)
        active.set(false)
        stopCore()
        executor.shutdownNow()
        RuntimeState.update(this, false, "Остановлено", currentProfileName)
        LogStore.append(this, "Прокси остановлена")
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun runProxy(profileUri: String, port: Int) {
        try {
            val (profile, config) = SingBoxConfigBuilder.build(profileUri, port)
            currentProfileName = profile.name
            RuntimeState.update(this, false, "Проверка профиля…", profile.name)
            updateNotification("Проверка ${profile.name}")
            LogStore.append(this, "Профиль распознан: ${profile.name}")

            val core = locateCore()
            val configFile = writeConfig(config.toString(2))
            checkConfiguration(core, configFile)
            if (stopping.get()) return

            RuntimeState.update(this, false, "Запуск ядра…", profile.name)
            updateNotification("Запуск ${profile.name}")
            val startedProcess = createProcess(core, configFile, "run")
            process = startedProcess
            startLogReader(startedProcess)

            if (!waitForPort(port, startedProcess, 10_000L)) {
                val exit = exitCodeOrNull(startedProcess)
                throw IllegalStateException(
                    if (exit == null) "Локальный порт 127.0.0.1:$port не открылся за 10 секунд"
                    else "sing-box завершился с кодом $exit до открытия локального порта",
                )
            }

            RuntimeState.update(this, true, "Работает: 127.0.0.1:$port", profile.name)
            updateNotification("SOCKS5/HTTP 127.0.0.1:$port")
            LogStore.append(this, "Локальная HTTP/SOCKS5-прокси готова на 127.0.0.1:$port")

            val exitCode = startedProcess.waitFor()
            process = null
            if (!stopping.get()) {
                throw IllegalStateException("sing-box неожиданно завершился с кодом $exitCode")
            }
        } catch (error: InterruptedException) {
            Thread.currentThread().interrupt()
        } catch (error: Exception) {
            if (!stopping.get()) {
                val message = error.message?.takeIf { it.isNotBlank() } ?: error.javaClass.simpleName
                LogStore.append(this, "ОШИБКА: $message")
                RuntimeState.update(this, false, "Ошибка: $message", currentProfileName)
                updateNotification("Ошибка запуска")
                stopSelf()
            }
        }
    }

    private fun locateCore(): File {
        val core = File(applicationInfo.nativeLibraryDir, "libsingbox.so")
        if (!core.isFile) {
            throw IllegalStateException(
                "Ядро sing-box не найдено для архитектуры ${Build.SUPPORTED_ABIS.joinToString()}",
            )
        }
        if (!core.canExecute()) core.setExecutable(true, false)
        LogStore.append(this, "Ядро: ${core.absolutePath}")
        return core
    }

    private fun writeConfig(payload: String): File {
        val runtimeDir = File(filesDir, "runtime").apply { mkdirs() }
        val temporary = File(runtimeDir, "sing-box.json.tmp")
        val target = File(runtimeDir, "sing-box.json")
        temporary.writeText(payload + "\n", Charsets.UTF_8)
        if (target.exists() && !target.delete()) {
            throw IllegalStateException("Не удалось заменить старую конфигурацию")
        }
        if (!temporary.renameTo(target)) {
            temporary.copyTo(target, overwrite = true)
            temporary.delete()
        }
        if (!target.isFile || target.length() == 0L) {
            throw IllegalStateException("Конфигурация sing-box не была записана")
        }
        return target
    }

    private fun checkConfiguration(core: File, configFile: File) {
        val check = createProcess(core, configFile, "check")
        val output = check.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        val code = check.waitFor()
        output.lineSequence().filter { it.isNotBlank() }.forEach {
            LogStore.append(this, "check: $it")
        }
        if (code != 0) {
            throw IllegalStateException(
                output.lineSequence().lastOrNull { it.isNotBlank() } ?: "Проверка конфигурации завершилась с кодом $code",
            )
        }
        LogStore.append(this, "Проверка конфигурации пройдена")
    }

    private fun createProcess(core: File, configFile: File, command: String): Process {
        val builder = ProcessBuilder(core.absolutePath, command, "-c", configFile.absolutePath)
            .directory(filesDir)
            .redirectErrorStream(true)
        builder.environment()["HOME"] = filesDir.absolutePath
        builder.environment()["TMPDIR"] = cacheDir.absolutePath
        builder.environment()["XDG_CACHE_HOME"] = cacheDir.absolutePath
        return builder.start()
    }

    private fun startLogReader(activeProcess: Process) {
        Thread({
            try {
                activeProcess.inputStream.bufferedReader(Charsets.UTF_8).useLines { lines ->
                    lines.forEach { line -> LogStore.append(this, line) }
                }
            } catch (error: Exception) {
                if (!stopping.get()) LogStore.append(this, "Ошибка чтения журнала: ${error.message}")
            }
        }, "tunnelgram-core-log").apply {
            isDaemon = true
            start()
        }
    }

    private fun waitForPort(port: Int, activeProcess: Process, timeoutMillis: Long): Boolean {
        val deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(timeoutMillis)
        while (System.nanoTime() < deadline && !stopping.get()) {
            if (exitCodeOrNull(activeProcess) != null) return false
            try {
                Socket().use { socket ->
                    socket.connect(InetSocketAddress("127.0.0.1", port), 150)
                    return true
                }
            } catch (_: Exception) {
                Thread.sleep(150)
            }
        }
        return false
    }

    private fun exitCodeOrNull(activeProcess: Process): Int? {
        return try {
            activeProcess.exitValue()
        } catch (_: IllegalThreadStateException) {
            null
        }
    }

    private fun stopCore() {
        val activeProcess = process ?: return
        process = null
        try {
            activeProcess.destroy()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                if (!activeProcess.waitFor(2, TimeUnit.SECONDS)) activeProcess.destroyForcibly()
            }
        } catch (_: Exception) {
            // Android will reclaim the child process together with the app UID if needed.
        }
    }

    private fun failAndStop(message: String) {
        RuntimeState.update(this, false, "Ошибка: $message")
        LogStore.append(this, "ОШИБКА: $message")
        stopSelf()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.notification_channel_name),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = getString(R.string.notification_channel_description)
            setShowBadge(false)
        }
        manager.createNotificationChannel(channel)
    }

    private fun buildNotification(text: String): Notification {
        val openIntent = Intent(this, MainActivity::class.java)
        val openPending = PendingIntent.getActivity(
            this,
            1,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or immutableFlag(),
        )
        val stopIntent = Intent(this, ProxyService::class.java).setAction(ACTION_STOP)
        val stopPending = PendingIntent.getService(
            this,
            2,
            stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or immutableFlag(),
        )

        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        return builder
            .setSmallIcon(R.drawable.ic_stat_tunnelgram)
            .setContentTitle("Tunnelgram работает")
            .setContentText(text)
            .setContentIntent(openPending)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .addAction(Notification.Action.Builder(null, "Остановить", stopPending).build())
            .build()
    }

    private fun updateNotification(text: String) {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(NOTIFICATION_ID, buildNotification(text))
    }

    private fun immutableFlag(): Int = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
        PendingIntent.FLAG_IMMUTABLE
    } else {
        0
    }
}
