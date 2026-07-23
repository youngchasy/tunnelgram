package org.tunnelgram.android

import android.Manifest
import android.app.Activity
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : Activity() {
    companion object {
        private const val PREFS = "user_settings"
        private const val KEY_PROFILE = "profile_uri"
        private const val KEY_PORT_TEXT = "listen_port_text"
        private const val STATE_PROFILE = "state_profile_uri"
        private const val STATE_PORT = "state_listen_port"
        private const val NOTIFICATION_REQUEST = 3001
        private const val EXPORT_LOG_REQUEST = 3002
    }

    private lateinit var profileInput: EditText
    private lateinit var portInput: EditText
    private lateinit var statusView: TextView
    private lateinit var logView: TextView
    private lateinit var startButton: Button
    private lateinit var stopButton: Button

    private var lastLogRevision = Long.MIN_VALUE
    private val handler = Handler(Looper.getMainLooper())
    private val refreshTask = object : Runnable {
        override fun run() {
            refreshState()
            handler.postDelayed(this, 1_500L)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = "Tunnelgram"
        setContentView(createContent())
        restoreInputs(savedInstanceState)
        refreshState(forceLogs = true)
    }

    override fun onResume() {
        super.onResume()
        handler.removeCallbacks(refreshTask)
        handler.post(refreshTask)
    }

    override fun onPause() {
        handler.removeCallbacks(refreshTask)
        saveDraftSettings()
        super.onPause()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString(STATE_PROFILE, profileInput.text.toString())
        outState.putString(STATE_PORT, portInput.text.toString())
        super.onSaveInstanceState(outState)
    }

    @Deprecated("Deprecated in Android API, retained for Android 7 compatibility")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != EXPORT_LOG_REQUEST || resultCode != RESULT_OK) return
        val uri = data?.data ?: return
        try {
            val state = RuntimeState.read(this)
            val report = buildString {
                appendLine("Tunnelgram Android diagnostic log")
                appendLine("App: ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})")
                appendLine("Android: ${Build.VERSION.RELEASE} / API ${Build.VERSION.SDK_INT}")
                appendLine("Device: ${Build.MANUFACTURER} ${Build.MODEL}")
                appendLine("ABI: ${Build.SUPPORTED_ABIS.joinToString()}")
                appendLine("Exported: ${Date()}")
                appendLine("Running: ${state.running}")
                appendLine("Status: ${state.status}")
                appendLine("Profile: ${state.profile.ifEmpty { "not selected" }}")
                appendLine("Local proxy: 127.0.0.1:${portInput.text.toString().trim()}")
                appendLine()
                append(LogStore.readAll(this@MainActivity).ifBlank { "Журнал пуст\n" })
            }
            val output = contentResolver.openOutputStream(uri, "w")
                ?: throw IllegalStateException("Не удалось открыть выбранный файл")
            output.bufferedWriter(Charsets.UTF_8).use { writer: java.io.BufferedWriter -> writer.write(report) }
            Toast.makeText(this, "Журнал экспортирован", Toast.LENGTH_LONG).show()
        } catch (error: Exception) {
            showError("Не удалось экспортировать журнал: ${error.message}")
        }
    }

    private fun createContent(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(18), dp(18), dp(24))
            setBackgroundColor(Color.rgb(245, 247, 250))
        }

        root.addView(TextView(this).apply {
            text = "Tunnelgram Android"
            textSize = 25f
            setTextColor(Color.rgb(32, 45, 64))
        }, matchWrap())

        root.addView(TextView(this).apply {
            text = "Локальная HTTP/SOCKS5-прокси через VLESS, Hysteria2, HTTP или SOCKS5. Android 7.0+, ARM 32/64-bit."
            textSize = 14f
            setTextColor(Color.DKGRAY)
            setPadding(0, dp(6), 0, dp(16))
        }, matchWrap())

        root.addView(label("Ссылка внешнего профиля"))
        profileInput = EditText(this).apply {
            id = View.generateViewId()
            minLines = 4
            maxLines = 8
            gravity = Gravity.TOP or Gravity.START
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_VARIATION_URI
            hint = "vless://…  hysteria2://…  https://…  socks5://…"
            setHorizontallyScrolling(false)
        }
        root.addView(profileInput, matchWrap())

        val profileActions = horizontalRow()
        profileActions.addView(button("Вставить") { pasteProfile() }, rowButton())
        profileActions.addView(button("Проверить") { validateProfile(true) }, rowButton())
        root.addView(profileActions, matchWrap())

        root.addView(label("Локальный порт"))
        portInput = EditText(this).apply {
            id = View.generateViewId()
            inputType = InputType.TYPE_CLASS_NUMBER
            setText("9443")
            hint = "9443"
        }
        root.addView(portInput, matchWrap())

        val controlRow = horizontalRow()
        startButton = button("Запустить") { startProxy() }
        stopButton = button("Остановить") { stopProxy() }
        controlRow.addView(startButton, rowButton())
        controlRow.addView(stopButton, rowButton())
        root.addView(controlRow, matchWrap())

        root.addView(button("Открыть SOCKS5 в Telegram") { openTelegram() }, matchWrapWithTop())
        root.addView(button("Диагностика соединения") { diagnoseProxy() }, matchWrapWithTop())

        root.addView(TextView(this).apply {
            text = "В Telegram укажите именно SOCKS5: сервер 127.0.0.1, порт как выше, логин и пароль пустые. Не вводите Wi-Fi IP телефона."
            textSize = 13f
            setTextColor(Color.rgb(90, 55, 20))
            setPadding(dp(8), dp(10), dp(8), 0)
        }, matchWrap())

        statusView = TextView(this).apply {
            textSize = 16f
            setTextColor(Color.rgb(32, 45, 64))
            setPadding(dp(12), dp(12), dp(12), dp(12))
            setBackgroundColor(Color.WHITE)
        }
        root.addView(statusView, matchWrapWithTop())

        val logHeader = horizontalRow().apply { gravity = Gravity.CENTER_VERTICAL }
        logHeader.addView(TextView(this).apply {
            text = "Журнал"
            textSize = 18f
            setTextColor(Color.rgb(32, 45, 64))
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        logHeader.addView(button("Очистить") {
            LogStore.clear(this)
            lastLogRevision = Long.MIN_VALUE
            refreshState(forceLogs = true)
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        root.addView(logHeader, matchWrapWithTop())
        root.addView(button("Экспорт логов") { exportLogs() }, matchWrap())

        logView = TextView(this).apply {
            textSize = 11f
            typeface = android.graphics.Typeface.MONOSPACE
            setTextColor(Color.rgb(25, 31, 39))
            setBackgroundColor(Color.WHITE)
            setPadding(dp(10), dp(10), dp(10), dp(10))
            minLines = 6
            maxLines = 8
        }
        root.addView(logView, matchWrap())

        root.addView(TextView(this).apply {
            text = "На экране показываются только последние 8 строк. Экспорт содержит весь ограниченный журнал и данные устройства без полной ссылки профиля."
            textSize = 12f
            setTextColor(Color.GRAY)
            setPadding(0, dp(8), 0, 0)
        }, matchWrap())

        root.addView(TextView(this).apply {
            text = "Профиль хранится только в закрытых данных приложения. Не публикуйте полную ссылку и журнал без проверки."
            textSize = 12f
            setTextColor(Color.GRAY)
            setPadding(0, dp(8), 0, 0)
        }, matchWrap())

        return ScrollView(this).apply {
            isFillViewport = true
            addView(root, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        }
    }

    private fun startProxy() {
        val profile = profileInput.text.toString().trim()
        val port = readPort() ?: return
        try {
            val parsed = ProfileParser.parse(profile)
            saveSettings(profile, port.toString())
            LogStore.append(this, "Запуск: ${parsed.name}")
            requestNotificationPermissionIfNeeded()
            val intent = Intent(this, ProxyService::class.java)
                .setAction(ProxyService.ACTION_START)
                .putExtra(ProxyService.EXTRA_PROFILE_URI, profile)
                .putExtra(ProxyService.EXTRA_PORT, port)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent) else startService(intent)
            Toast.makeText(this, "Запуск прокси…", Toast.LENGTH_SHORT).show()
        } catch (error: Exception) {
            showError(error.message ?: "Не удалось разобрать профиль")
        }
    }

    private fun stopProxy() {
        val intent = Intent(this, ProxyService::class.java).setAction(ProxyService.ACTION_STOP)
        try {
            startService(intent)
        } catch (_: Exception) {
            stopService(Intent(this, ProxyService::class.java))
        }
        Toast.makeText(this, "Остановка…", Toast.LENGTH_SHORT).show()
    }

    private fun diagnoseProxy() {
        val state = RuntimeState.read(this)
        if (!state.running) {
            showError("Сначала запустите прокси и дождитесь статуса «Работает»")
            return
        }
        val port = readPort() ?: return
        val intent = Intent(this, ProxyService::class.java)
            .setAction(ProxyService.ACTION_DIAGNOSE)
            .putExtra(ProxyService.EXTRA_PORT, port)
        startService(intent)
        Toast.makeText(this, "Диагностика запущена; результат появится в статусе и журнале", Toast.LENGTH_LONG).show()
    }

    private fun validateProfile(showToast: Boolean): ProxyProfile? {
        return try {
            val profile = ProfileParser.parse(profileInput.text.toString())
            val port = readPort() ?: return null
            SingBoxConfigBuilder.build(profileInput.text.toString(), port)
            saveDraftSettings()
            if (showToast) Toast.makeText(this, "Профиль корректен: ${profile.name}", Toast.LENGTH_LONG).show()
            profile
        } catch (error: Exception) {
            if (showToast) showError(error.message ?: "Профиль не прошёл проверку")
            null
        }
    }

    private fun pasteProfile() {
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val text = clipboard.primaryClip?.getItemAt(0)?.coerceToText(this)?.toString().orEmpty().trim()
        if (text.isEmpty()) {
            Toast.makeText(this, "Буфер обмена пуст", Toast.LENGTH_SHORT).show()
        } else {
            profileInput.setText(text)
            profileInput.setSelection(profileInput.text.length)
            saveDraftSettings()
        }
    }

    private fun openTelegram() {
        val port = readPort() ?: return
        val link = "tg://socks?server=127.0.0.1&port=" +
            URLEncoder.encode(port.toString(), StandardCharsets.UTF_8.name())
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(link)))
        } catch (_: Exception) {
            showError("Telegram не найден или не поддерживает ссылку SOCKS5")
        }
    }

    private fun exportLogs() {
        val stamp = SimpleDateFormat("yyyy-MM-dd_HH-mm-ss", Locale.US).format(Date())
        val intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
            .addCategory(Intent.CATEGORY_OPENABLE)
            .setType("text/plain")
            .putExtra(Intent.EXTRA_TITLE, "tunnelgram_logs_$stamp.txt")
        try {
            @Suppress("DEPRECATION")
            startActivityForResult(intent, EXPORT_LOG_REQUEST)
        } catch (error: Exception) {
            showError("На устройстве нет приложения для сохранения файла: ${error.message}")
        }
    }

    private fun readPort(): Int? {
        val port = portInput.text.toString().trim().toIntOrNull()
        if (port == null || port !in 1..65535) {
            showError("Локальный порт должен быть числом от 1 до 65535")
            return null
        }
        return port
    }

    private fun refreshState(forceLogs: Boolean = false) {
        val state = RuntimeState.read(this)
        statusView.text = buildString {
            append(if (state.running) "● Подключено" else "○ Не подключено")
            append("\n")
            append(state.status)
            if (state.profile.isNotEmpty()) {
                append("\n")
                append(state.profile)
            }
        }
        statusView.setTextColor(if (state.running) Color.rgb(20, 110, 55) else Color.rgb(90, 45, 35))
        val busy = state.status.contains("Запуск") || state.status.contains("Проверка") || state.status.contains("Диагностика")
        startButton.isEnabled = !state.running && !busy
        stopButton.isEnabled = state.running || busy

        val snapshot = LogStore.readTail(this, maxLines = 8, maxChars = 6_000)
        if (forceLogs || snapshot.revision != lastLogRevision) {
            lastLogRevision = snapshot.revision
            logView.text = snapshot.text.ifBlank { "Журнал пуст" }
        }
    }

    private fun restoreInputs(savedInstanceState: Bundle?) {
        val prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val profile = savedInstanceState?.getString(STATE_PROFILE)
            ?: prefs.getString(KEY_PROFILE, "").orEmpty()
        val port = savedInstanceState?.getString(STATE_PORT)
            ?: prefs.getString(KEY_PORT_TEXT, "9443").orEmpty().ifBlank { "9443" }
        profileInput.setText(profile)
        portInput.setText(port)
    }

    private fun saveDraftSettings() {
        if (!::profileInput.isInitialized || !::portInput.isInitialized) return
        saveSettings(profileInput.text.toString(), portInput.text.toString())
    }

    private fun saveSettings(profile: String, portText: String) {
        getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_PROFILE, profile)
            .putString(KEY_PORT_TEXT, portText)
            .apply()
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), NOTIFICATION_REQUEST)
        }
    }

    private fun showError(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }

    private fun label(text: String): TextView = TextView(this).apply {
        this.text = text
        textSize = 15f
        setTextColor(Color.rgb(32, 45, 64))
        setPadding(0, dp(14), 0, dp(4))
    }

    private fun button(text: String, action: () -> Unit): Button = Button(this).apply {
        this.text = text
        setOnClickListener { action() }
        isAllCaps = false
    }

    private fun horizontalRow(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
    }

    private fun rowButton(): LinearLayout.LayoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
        marginEnd = dp(6)
    }

    private fun matchWrap(): LinearLayout.LayoutParams = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT,
        ViewGroup.LayoutParams.WRAP_CONTENT,
    )

    private fun matchWrapWithTop(): LinearLayout.LayoutParams = matchWrap().apply {
        topMargin = dp(10)
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}
