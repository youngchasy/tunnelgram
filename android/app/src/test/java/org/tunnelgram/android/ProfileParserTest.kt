package org.tunnelgram.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ProfileParserTest {
    @Test
    fun parsesVlessReality() {
        val profile = ProfileParser.parse(
            "vless://11111111-1111-1111-1111-111111111111@example.com:443" +
                "?security=reality&sni=www.example.com&fp=chrome&pbk=PUBLIC&sid=abcd&flow=xtls-rprx-vision",
        )
        assertEquals("vless", profile.scheme)
        assertEquals("vless", profile.outbound.getString("type"))
        assertEquals(443, profile.outbound.getInt("server_port"))
        assertTrue(profile.outbound.getJSONObject("tls").getJSONObject("reality").getBoolean("enabled"))
        assertEquals("chrome", profile.outbound.getJSONObject("tls").getJSONObject("utls").getString("fingerprint"))
    }

    @Test
    fun parsesVlessWebSocket() {
        val profile = ProfileParser.parse(
            "vless://uuid@example.com:8443?security=tls&type=ws&path=%2Ftelegram&host=cdn.example",
        )
        val transport = profile.outbound.getJSONObject("transport")
        assertEquals("ws", transport.getString("type"))
        assertEquals("/telegram", transport.getString("path"))
        assertEquals("cdn.example", transport.getJSONObject("headers").getString("Host"))
    }

    @Test
    fun parsesHysteria2() {
        val profile = ProfileParser.parse(
            "hysteria2://secret@example.com:443?sni=cdn.example&obfs=salamander&obfs-password=mask&upmbps=20&downmbps=80",
        )
        assertEquals("hysteria2", profile.outbound.getString("type"))
        assertEquals("secret", profile.outbound.getString("password"))
        assertEquals(20, profile.outbound.getInt("up_mbps"))
        assertEquals("salamander", profile.outbound.getJSONObject("obfs").getString("type"))
    }

    @Test
    fun parsesAuthenticatedHttpAndSocks() {
        val http = ProfileParser.parse("https://user:pass@example.com:8443?sni=proxy.example")
        assertEquals("user", http.outbound.getString("username"))
        assertEquals("pass", http.outbound.getString("password"))
        assertEquals("proxy.example", http.outbound.getJSONObject("tls").getString("server_name"))

        val socks = ProfileParser.parse("socks5://user:pass@example.com:1080")
        assertEquals("5", socks.outbound.getString("version"))
        assertEquals("user", socks.outbound.getString("username"))
    }

    @Test
    fun buildsLocalMixedProxy() {
        val (_, config) = SingBoxConfigBuilder.build("socks5://example.com:1080", 9443)
        val inbound = config.getJSONArray("inbounds").getJSONObject(0)
        assertEquals("mixed", inbound.getString("type"))
        assertEquals("127.0.0.1", inbound.getString("listen"))
        assertEquals(9443, inbound.getInt("listen_port"))
        assertEquals("proxy-out", config.getJSONObject("route").getString("final"))
        assertTrue(config.getJSONObject("route").getBoolean("auto_detect_interface"))
    }

    @Test(expected = ProfileException::class)
    fun rejectsMissingVlessUuid() {
        ProfileParser.parse("vless://example.com:443?security=tls")
    }

    @Test(expected = ProfileException::class)
    fun rejectsUnsupportedScheme() {
        ProfileParser.parse("trojan://secret@example.com:443")
    }

    @Test
    fun preservesPlusInPassword() {
        val profile = ProfileParser.parse("socks5://user:p+a%2Bss@example.com:1080")
        assertEquals("p+a+ss", profile.outbound.getString("password"))
        assertFalse(profile.outbound.getString("password").contains(' '))
    }
}
