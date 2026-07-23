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
    }
}
