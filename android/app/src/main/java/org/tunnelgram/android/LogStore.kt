package org.tunnelgram.android

import android.content.Context
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object LogStore {
    private const val MAX_BYTES = 768 * 1024L
    private const val KEEP_BYTES = 512 * 1024
    private val lock = Any()
    private val ansiPattern = Regex("\\u001B\\[[;\\d]*[ -/]*[@-~]")
    private val timeFormat = SimpleDateFormat("HH:mm:ss", Locale.US)

    fun file(context: Context): File = File(context.filesDir, "tunnelgram.log")

    fun append(context: Context, message: String) {
        val clean = ansiPattern.replace(message, "").replace('\u0000', ' ').trimEnd()
        if (clean.isEmpty()) return
        synchronized(lock) {
            val logFile = file(context)
            if (logFile.exists() && logFile.length() > MAX_BYTES) {
                val bytes = logFile.readBytes()
                val start = (bytes.size - KEEP_BYTES).coerceAtLeast(0)
                logFile.writeBytes(bytes.copyOfRange(start, bytes.size))
            }
            logFile.appendText("${timeFormat.format(Date())} $clean\n", Charsets.UTF_8)
        }
    }

    fun read(context: Context): String = synchronized(lock) {
        val logFile = file(context)
        if (!logFile.exists()) "" else logFile.readText(Charsets.UTF_8)
    }

    fun clear(context: Context) = synchronized(lock) {
        file(context).writeText("", Charsets.UTF_8)
    }
}
