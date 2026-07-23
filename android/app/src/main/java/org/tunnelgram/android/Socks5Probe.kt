package org.tunnelgram.android

import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.InetSocketAddress
import java.net.Socket
import kotlin.system.measureTimeMillis

object Socks5Probe {
    data class Result(val ok: Boolean, val message: String, val elapsedMs: Long)

    fun handshake(proxyHost: String, proxyPort: Int, timeoutMs: Int = 1_500): Result {
        var message = ""
        val elapsed = measureTimeMillis {
            message = try {
                Socket().use { socket ->
                    socket.soTimeout = timeoutMs
                    socket.connect(InetSocketAddress(proxyHost, proxyPort), timeoutMs)
                    negotiate(socket)
                    "SOCKS5 отвечает"
                }
            } catch (error: Exception) {
                "SOCKS5 не отвечает: ${shortError(error)}"
            }
        }
        return Result(message == "SOCKS5 отвечает", message, elapsed)
    }

    fun connect(
        proxyHost: String,
        proxyPort: Int,
        targetHost: String,
        targetPort: Int,
        timeoutMs: Int = 5_000,
    ): Result {
        var ok = false
        var message = ""
        val elapsed = measureTimeMillis {
            message = try {
                val hostBytes = targetHost.toByteArray(Charsets.UTF_8)
                require(hostBytes.size in 1..255) { "Слишком длинное имя диагностического сервера" }
                Socket().use { socket ->
                    socket.soTimeout = timeoutMs
                    socket.connect(InetSocketAddress(proxyHost, proxyPort), timeoutMs)
                    negotiate(socket)
                    val output = DataOutputStream(socket.getOutputStream())
                    val input = DataInputStream(socket.getInputStream())
                    output.write(byteArrayOf(0x05, 0x01, 0x00, 0x03, hostBytes.size.toByte()))
                    output.write(hostBytes)
                    output.writeShort(targetPort)
                    output.flush()

                    val version = input.readUnsignedByte()
                    val reply = input.readUnsignedByte()
                    input.readUnsignedByte()
                    val addressType = input.readUnsignedByte()
                    if (version != 5) throw IllegalStateException("неверная версия ответа $version")
                    if (reply != 0) throw IllegalStateException(replyMessage(reply))
                    skipBoundAddress(input, addressType)
                    input.readUnsignedShort()
                    ok = true
                    "Выход через профиль доступен: $targetHost:$targetPort"
                }
            } catch (error: Exception) {
                "Не удалось подключиться к $targetHost:$targetPort: ${shortError(error)}"
            }
        }
        return Result(ok, message, elapsed)
    }

    private fun negotiate(socket: Socket) {
        val output = DataOutputStream(socket.getOutputStream())
        val input = DataInputStream(socket.getInputStream())
        output.write(byteArrayOf(0x05, 0x01, 0x00))
        output.flush()
        val version = input.readUnsignedByte()
        val method = input.readUnsignedByte()
        if (version != 5) throw IllegalStateException("локальный порт ответил не как SOCKS5")
        if (method == 0xFF) throw IllegalStateException("SOCKS5 отклонил способ авторизации")
        if (method != 0x00) throw IllegalStateException("SOCKS5 запросил неподдерживаемую авторизацию $method")
    }

    private fun skipBoundAddress(input: DataInputStream, addressType: Int) {
        when (addressType) {
            0x01 -> input.skipFully(4)
            0x03 -> input.skipFully(input.readUnsignedByte())
            0x04 -> input.skipFully(16)
            else -> throw IllegalStateException("неизвестный тип адреса SOCKS5 $addressType")
        }
    }

    private fun DataInputStream.skipFully(count: Int) {
        val buffer = ByteArray(count)
        readFully(buffer)
    }

    private fun replyMessage(reply: Int): String = when (reply) {
        1 -> "общая ошибка прокси"
        2 -> "соединение запрещено правилами"
        3 -> "сеть недоступна"
        4 -> "узел недоступен"
        5 -> "соединение отклонено"
        6 -> "истёк TTL"
        7 -> "команда не поддерживается"
        8 -> "тип адреса не поддерживается"
        else -> "ошибка SOCKS5 $reply"
    }

    private fun shortError(error: Exception): String {
        return error.message?.trim()?.takeIf { it.isNotEmpty() } ?: error.javaClass.simpleName
    }
}
