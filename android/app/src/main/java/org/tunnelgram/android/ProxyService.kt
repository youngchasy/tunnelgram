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
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

class ProxyService : Service() {
    companion object {
        const val ACTION_START = "org.tunnelgram.android.action.START"
        const val ACTION_STOP = "org.tunnelgram.android.action.STOP"
        const val ACTION_DIAGNOSE = "org.tunnelgram.android.action.DIAGNOSE"
        const val EXTRA_PROFILE_URI = "profile_uri"
        const val EXTRA_PORT = "listen_port"

        private const val CHANNEL_ID = "tunnelgram_proxy"
        private const val NOTIFICATION_ID = 2001
    }

    private val coreExecutor = Executors.newSingleThreadExecutor()
    private val diagnosticExecutor = Executors.newSingleThreadExecutor()
    private val stopping = AtomicBoolean(false)
    private val active = AtomicBoolean(false)
    private val diagnosticRunning = AtomicBoolean(false)

    @Volatile
    private var process: Process? = null

    @Volatile
    private var currentProfileName: String = ""

    @Volatile
    private var currentPort: Int = 9443

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        RuntimeState.update(this, false, "Запуск службы…")
        startForeground(NOTIFICATION_ID, buildNotification("Запуск локальной прокси…"))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                LogStore.append(this, "Остановка по команде пользователя")
                stopSelf()
                return START_NOT_STICKY
            }

            ACTION_DIAGNOSE -> {
                val requestedPort = intent.getIntExtra(EXTRA_PORT, currentPort)
                scheduleDiagnostics(requestedPort, automatic = false)
                return START_NOT_STICKY
            }
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

        currentPort = port
        stopping.set(false)
        coreExecutor.execute {
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
        coreExecutor.shutdownNow()
        diagnosticExecutor.shutdownNow()
        RuntimeState.update(this, false, "Остановлено", currentProfileName)
        LogStore.append(this, "Прокси остановлена")
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun runProxy(profileUri: String, port: Int) {
        try {
            val (profile, config) = SingBoxConfigBuilder.build(profileUri, port, logLevel = "warn")
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

            val readiness = waitForSocks5(port, startedProcess, 12_000L)
            if (!readiness.ok) {
                val exit = exitCodeOrNull(startedProcess)
                throw IllegalStateException(
                    if (exit == null) "Локальная SOCKS5-прокси не готова: ${readiness.message}"
                    else "sing-box завершился с кодом $exit до запуска SOCKS5",
                )
            }

            RuntimeState.update(this, true, "Работает: 127.0.0.1:$port\nЛокальный SOCKS5 отвечает", profile.name)
            updateNotification("SOCKS5/HTTP 127.0.0.1:$port")
            LogStore.append(this, "Локальная HTTP/SOCKS5-прокси готова на 127.0.0.1:$port (${readiness.elapsedMs} мс)")
            scheduleDiagnostics(port, automatic = true)

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

    private fun scheduleDiagnostics(port: Int, automatic: Boolean) {
        val activeProcess = process
        if (!active.get() || activeProcess == null || exitCodeOrNull(activeProcess) != null) {
            if (!automatic) {
                RuntimeState.update(this, false, "Прокси не запущена", currentProfileName)
                LogStore.append(this, "Диагностика отменена: прокси не запущена")
                stopSelf()
            }
            return
        }
        if (!diagnosticRunning.compareAndSet(false, true)) {
            if (!automatic) LogStore.append(this, "Диагностика уже выполняется")
            return
        }
        diagnosticExecutor.execute {
            try {
                runDiagnostics(port, automatic)
            } finally {
                diagnosticRunning.set(false)
            }
        }
    }

    private fun runDiagnostics(port: Int, automatic: Boolean) {
        if (stopping.get()) return
        RuntimeState.update(this, true, "Диагностика SOCKS5 и выхода…", currentProfileName)
        if (!automatic) LogStore.append(this, "Запущена ручная диагностика")

        val local = Socks5Probe.handshake("127.0.0.1", port, 2_000)
        LogStore.append(this, "Диагностика локальной прокси: ${local.message} (${local.elapsedMs} мс)")
        if (!local.ok) {
            RuntimeState.update(
                this,
                true,
                "Прокси-процесс запущен, но SOCKS5 на 127.0.0.1:$port не отвечает: ${local.message}",
                currentProfileName,
            )
            updateNotification("Ошибка локального SOCKS5")
            return
        }

        val targets = listOf("venus.web.telegram.org", "pluto.web.telegram.org")
        var lastFailure: Socks5Probe.Result? = null
        for (target in targets) {
            if (stopping.get()) return
            val result = Socks5Probe.connect("127.0.0.1", port, target, 443, 6_000)
            LogStore.append(this, "Диагностика выхода: ${result.message} (${result.elapsedMs} мс)")
            if (result.ok) {
                RuntimeState.update(
                    this,
                    true,
                    "Работает: 127.0.0.1:$port\nSOCKS5 и выход к Telegram проверены",
                    currentProfileName,
                )
                updateNotification("SOCKS5 и выход проверены")
                return
            }
            lastFailure = result
        }

        val failure = lastFailure?.message ?: "неизвестная ошибка"
        RuntimeState.update(
            this,
            true,
            "Локальный SOCKS5 работает, но выход через профиль не прошёл проверку: $failure",
            currentProfileName,
        )
        updateNotification("Прокси запущена, выход не проверен")
    }

    private fun locateCore(): File {
        val core = File(applicationInfo.nativeLibraryDir, "libsingbox.so")
        if (!core.isFile) {
            throw IllegalStateException(
                "Ядро sing-box не найдено для архитектуры ${Build.SUPPORTED_ABIS.joinToString()}",
            )
        }
        if (!core.canExecute()) core.setExecutable(true, false)
        LogStore.append(this, "Ядро найдено для ABI ${Build.SUPPORTED_ABIS.firstOrNull().orEmpty()}")
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
        val lines = output.lineSequence().filter { it.isNotBlank() }.map { "check: $it" }.toList()
        LogStore.appendBatch(this, lines)
        if (code != 0) {
            throw IllegalStateException(
                output.lineSequence().lastOrNull { it.isNotBlank() }
                    ?: "Проверка конфигурации завершилась с кодом $code",
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
        builder.environment()["NO_COLOR"] = "1"
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

    private fun waitForSocks5(port: Int, activeProcess: Process, timeoutMillis: Long): Socks5Probe.Result {
        val deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(timeoutMillis)
        var last = Socks5Probe.Result(false, "порт ещё не открыт", 0L)
        while (System.nanoTime() < deadline && !stopping.get()) {
            if (exitCodeOrNull(activeProcess) != null) return last
            last = Socks5Probe.handshake("127.0.0.1", port, 500)
            if (last.ok) return last
            Thread.sleep(200)
        }
        return last
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
