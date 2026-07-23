package org.tunnelgram.android

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.ServerSocket
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class Socks5ProbeTest {
    @Test
    fun handshakeRecognizesLocalSocks5() {
        withFakeSocksServer(replyCode = 0) { port ->
            val result = Socks5Probe.handshake("127.0.0.1", port, 2_000)
            assertTrue(result.message, result.ok)
        }
    }

    @Test
    fun connectSendsDomainRequestAndAcceptsSuccess() {
        withFakeSocksServer(replyCode = 0) { port ->
            val result = Socks5Probe.connect("127.0.0.1", port, "venus.web.telegram.org", 443, 2_000)
            assertTrue(result.message, result.ok)
        }
    }

    @Test
    fun connectReportsProxyRefusal() {
        withFakeSocksServer(replyCode = 5) { port ->
            val result = Socks5Probe.connect("127.0.0.1", port, "venus.web.telegram.org", 443, 2_000)
            assertFalse(result.ok)
            assertTrue(result.message.contains("отклонено"))
        }
    }

    private fun withFakeSocksServer(replyCode: Int, block: (Int) -> Unit) {
        val server = ServerSocket(0)
        val ready = CountDownLatch(1)
        val thread = Thread {
            ready.countDown()
            server.accept().use { socket ->
                val input = DataInputStream(socket.getInputStream())
                val output = DataOutputStream(socket.getOutputStream())
                input.readUnsignedByte()
                val methods = input.readUnsignedByte()
                repeat(methods) { input.readUnsignedByte() }
                output.write(byteArrayOf(0x05, 0x00))
                output.flush()

                socket.soTimeout = 300
                try {
                    input.readUnsignedByte()
                    input.readUnsignedByte()
                    input.readUnsignedByte()
                    val type = input.readUnsignedByte()
                    when (type) {
                        0x01 -> ByteArray(4).also { input.readFully(it) }
                        0x03 -> ByteArray(input.readUnsignedByte()).also { input.readFully(it) }
                        0x04 -> ByteArray(16).also { input.readFully(it) }
                    }
                    input.readUnsignedShort()
                    output.write(byteArrayOf(0x05, replyCode.toByte(), 0x00, 0x01, 127, 0, 0, 1, 0x23, 0x28))
                    output.flush()
                } catch (_: Exception) {
                    // Handshake-only test closes after negotiation.
                }
            }
            server.close()
        }
        thread.start()
        assertTrue(ready.await(1, TimeUnit.SECONDS))
        try {
            block(server.localPort)
        } finally {
            server.close()
            thread.join(2_000)
        }
    }
}
