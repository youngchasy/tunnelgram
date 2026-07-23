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

class MainActivity : Activity() {
    companion object {
        private const val PREFS = "user_settings"
        private const val KEY_PROFILE = "profile_uri"
        private const val KEY_PORT = "listen_port"
        private const val NOTIFICATION_REQUEST = 3001
    }

    private lateinit var profileInput: EditText
    private lateinit var portInput: EditText
    private lateinit var statusView: TextView
    private lateinit var logView: TextView
    private lateinit var startButton: Button
    private lateinit var stopButton: Button

    private val handler = Handler(Looper.getMainLooper())
    private val refreshTask = object : Runnable {
        override fun run() {
            refreshState()
            handler.postDelayed(this, 750L)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = "Tunnelgram"
        setContentView(createContent())
        restoreSettings()
        refreshState()
    }

    override fun onResume() {
        super.onResume()
        handler.post(refreshTask)
    }

    override fun onPause() {
        handler.removeCallbacks(refreshTask)
        super.onPause()
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
            text = "Этап 1: локальная HTTP/SOCKS5-прокси через VLESS, Hysteria2, HTTP или SOCKS5. Поддерживается Android 7.0+ и ARM 32/64-bit."
            textSize = 14f
            setTextColor(Color.DKGRAY)
            setPadding(0, dp(6), 0, dp(16))
        }, matchWrap())

        root.addView(label("Ссылка внешнего профиля"))
        profileInput = EditText(this).apply {
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

        statusView = TextView(this).apply {
            textSize = 16f
            setTextColor(Color.rgb(32, 45, 64))
            setPadding(dp(12), dp(12), dp(12), dp(12))
            setBackgroundColor(Color.WHITE)
        }
        root.addView(statusView, matchWrapWithTop())

        val logHeader = horizontalRow().apply {
            gravity = Gravity.CENTER_VERTICAL
        }
        logHeader.addView(TextView(this).apply {
            text = "Журнал"
            textSize = 18f
            setTextColor(Color.rgb(32, 45, 64))
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        logHeader.addView(button("Очистить") {
            LogStore.clear(this)
            refreshState()
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        root.addView(logHeader, matchWrapWithTop())

        logView = TextView(this).apply {
            textSize = 12f
            typeface = android.graphics.Typeface.MONOSPACE
            setTextIsSelectable(true)
            setTextColor(Color.rgb(25, 31, 39))
            setBackgroundColor(Color.WHITE)
            setPadding(dp(10), dp(10), dp(10), dp(10))
            minHeight = dp(280)
        }
        root.addView(logView, matchWrap())

        root.addView(TextView(this).apply {
            text = "Профиль хранится только в закрытых данных приложения. Не публикуйте полную ссылку и журнал с секретами."
            textSize = 12f
            setTextColor(Color.GRAY)
            setPadding(0, dp(12), 0, 0)
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
            saveSettings(profile, port)
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

    private fun validateProfile(showToast: Boolean): ProxyProfile? {
        return try {
            val profile = ProfileParser.parse(profileInput.text.toString())
            val port = readPort() ?: return null
            SingBoxConfigBuilder.build(profileInput.text.toString(), port)
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

    private fun readPort(): Int? {
        val port = portInput.text.toString().trim().toIntOrNull()
        if (port == null || port !in 1..65535) {
            showError("Локальный порт должен быть числом от 1 до 65535")
            return null
        }
        return port
    }

    private fun refreshState() {
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
        val busy = state.status.contains("Запуск") || state.status.contains("Проверка")
        startButton.isEnabled = !state.running && !busy
        stopButton.isEnabled = state.running || busy

        val logs = LogStore.read(this)
        if (logView.text.toString() != logs) logView.text = logs
    }

    private fun restoreSettings() {
        val prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        profileInput.setText(prefs.getString(KEY_PROFILE, "") ?: "")
        portInput.setText(prefs.getInt(KEY_PORT, 9443).toString())
    }

    private fun saveSettings(profile: String, port: Int) {
        getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_PROFILE, profile)
            .putInt(KEY_PORT, port)
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
