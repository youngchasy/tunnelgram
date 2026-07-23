package org.tunnelgram.android

import android.content.Context
import java.io.File
import java.io.RandomAccessFile
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object LogStore {
    private const val MAX_BYTES = 192 * 1024L
    private const val KEEP_BYTES = 128 * 1024
    private const val TAIL_READ_BYTES = 24 * 1024
    private const val MAX_LINE_CHARS = 2_000
    private val lock = Any()
    private val ansiPattern = Regex("\\u001B\\[[;\\d]*[ -/]*[@-~]")
    private val timeFormat = SimpleDateFormat("HH:mm:ss", Locale.US)

    data class TailSnapshot(val revision: Long, val text: String)

    fun file(context: Context): File = File(context.filesDir, "tunnelgram.log")

    fun append(context: Context, message: String) {
        appendBatch(context, listOf(message))
    }

    fun appendBatch(context: Context, messages: Iterable<String>) {
        synchronized(lock) {
            val prepared = buildString {
                for (message in messages) {
                    for (line in cleanLines(message)) {
                        append(timeFormat.format(Date()))
                        append(' ')
                        append(line)
                        append('\n')
                    }
                }
            }
            if (prepared.isEmpty()) return

            val logFile = file(context)
            logFile.parentFile?.mkdirs()
            logFile.appendText(prepared, Charsets.UTF_8)
            rotateIfNeeded(logFile)
        }
    }

    fun readTail(context: Context, maxLines: Int = 8, maxChars: Int = 6_000): TailSnapshot = synchronized(lock) {
        val logFile = file(context)
        if (!logFile.isFile || logFile.length() == 0L) return@synchronized TailSnapshot(0L, "")

        val length = logFile.length()
        val revision = (logFile.lastModified() shl 20) xor length
        val readLength = minOf(length, TAIL_READ_BYTES.toLong()).toInt()
        val start = length - readLength
        val bytes = ByteArray(readLength)
        RandomAccessFile(logFile, "r").use { input ->
            input.seek(start)
            input.readFully(bytes)
        }

        var decoded = bytes.toString(Charsets.UTF_8)
        if (start > 0L) decoded = decoded.substringAfter('\n', "")
        val lines = decoded.split('\n').filter { it.isNotBlank() }
        var tail = lines.takeLast(maxLines.coerceAtLeast(1)).joinToString("\n")
        if (tail.length > maxChars) {
            tail = tail.takeLast(maxChars).substringAfter('\n', tail.takeLast(maxChars))
        }
        TailSnapshot(revision, tail)
    }

    fun readAll(context: Context): String = synchronized(lock) {
        val logFile = file(context)
        if (!logFile.isFile) "" else logFile.readText(Charsets.UTF_8)
    }

    fun clear(context: Context) = synchronized(lock) {
        val logFile = file(context)
        logFile.parentFile?.mkdirs()
        logFile.writeText("", Charsets.UTF_8)
        logFile.setLastModified(System.currentTimeMillis())
    }

    private fun cleanLines(message: String): List<String> {
        val clean = ansiPattern.replace(message, "").replace('\u0000', ' ')
        return clean.lineSequence()
            .map { it.trimEnd().take(MAX_LINE_CHARS) }
            .filter { it.isNotBlank() }
            .toList()
    }

    private fun rotateIfNeeded(logFile: File) {
        if (logFile.length() <= MAX_BYTES) return
        val length = logFile.length()
        val keep = minOf(length, KEEP_BYTES.toLong()).toInt()
        val bytes = ByteArray(keep)
        RandomAccessFile(logFile, "r").use { input ->
            input.seek(length - keep)
            input.readFully(bytes)
        }
        val newline = bytes.indexOf('\n'.code.toByte())
        val safeStart = if (newline >= 0) newline + 1 else 0
        logFile.writeBytes(bytes.copyOfRange(safeStart, bytes.size))
    }
}
