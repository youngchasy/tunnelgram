package org.tunnelgram.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RuntimeConfigSmokeTest {
    @Test
    fun outputIsValidJsonWithOneOutbound() {
        val (_, config) = SingBoxConfigBuilder.build(
            "vless://11111111-1111-1111-1111-111111111111@example.com:443?security=tls&sni=example.com",
            9443,
        )
        val serialized = config.toString()
        assertTrue(serialized.startsWith("{"))
        assertEquals(1, config.getJSONArray("outbounds").length())

        val dns = config.getJSONObject("dns")
        assertEquals("bootstrap-doh", dns.getString("final"))
        assertEquals("prefer_ipv4", dns.getString("strategy"))
        val server = dns.getJSONArray("servers").getJSONObject(0)
        assertEquals("https", server.getString("type"))
        assertEquals("1.1.1.1", server.getString("server"))
        assertEquals("cloudflare-dns.com", server.getJSONObject("tls").getString("server_name"))

        val outbound = config.getJSONArray("outbounds").getJSONObject(0)
        assertEquals("bootstrap-doh", outbound.getString("domain_resolver"))
        assertEquals(
            "bootstrap-doh",
            config.getJSONObject("route").getString("default_domain_resolver"),
        )
    }
}
