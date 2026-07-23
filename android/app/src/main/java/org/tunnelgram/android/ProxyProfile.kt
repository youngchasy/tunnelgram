package org.tunnelgram.android

import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.net.URLDecoder
import java.nio.charset.StandardCharsets

class ProfileException(message: String, cause: Throwable? = null) : IllegalArgumentException(message, cause)

data class ProxyProfile(
    val scheme: String,
    val name: String,
    val outbound: JSONObject,
)

object ProfileParser {
    private val supportedSchemes = setOf(
        "http",
        "https",
        "socks",
        "socks4",
        "socks4a",
        "socks5",
        "socks5h",
        "vless",
        "hysteria2",
        "hy2",
    )

    fun parse(rawValue: String): ProxyProfile {
        val value = rawValue.trim()
        if (value.isEmpty()) throw ProfileException("Введите ссылку внешнего профиля")

        val uri = try {
            URI(value)
        } catch (error: Exception) {
            throw ProfileException("Ссылка профиля имеет неверный формат", error)
        }

        val scheme = uri.scheme?.lowercase().orEmpty()
        if (scheme !in supportedSchemes) {
            throw ProfileException(
                "Неподдерживаемая схема ${scheme.ifEmpty { "(не указана)" }}. " +
                    "Доступны HTTP, HTTPS, SOCKS5, VLESS и Hysteria2",
            )
        }

        val query = parseQuery(uri.rawQuery)
        return when (scheme) {
            "http", "https" -> parseHttp(uri, query, scheme)
            "socks", "socks4", "socks4a", "socks5", "socks5h" -> parseSocks(uri, query, scheme)
            "vless" -> parseVless(uri, query)
            else -> parseHysteria2(uri, query)
        }
    }

    private fun parseHttp(uri: URI, query: Map<String, List<String>>, scheme: String): ProxyProfile {
        val host = requireHost(uri)
        val port = requirePort(uri, if (scheme == "https") 443 else 80)
        val credentials = userInfo(uri)
        val outbound = JSONObject()
            .put("type", "http")
            .put("tag", "proxy-out")
            .put("server", host)
            .put("server_port", port)

        credentials.first?.let { outbound.put("username", it) }
        credentials.second?.let { outbound.put("password", it) }

        val path = decode(uri.rawPath.orEmpty())
        if (path.isNotEmpty() && path != "/") outbound.put("path", path)

        if (scheme == "https") {
            outbound.put(
                "tls",
                tlsConfig(
                    enabled = true,
                    serverName = first(query, "sni", "serverName", "server_name", default = host),
                    insecure = bool(first(query, "insecure", "allowInsecure")),
                    alpn = first(query, "alpn"),
                ),
            )
        }

        return ProxyProfile(scheme, "HTTP-прокси $host:$port", outbound)
    }

    private fun parseSocks(uri: URI, query: Map<String, List<String>>, scheme: String): ProxyProfile {
        val host = requireHost(uri)
        val port = requirePort(uri, 1080)
        val version = when (scheme) {
            "socks4" -> "4"
            "socks4a" -> "4a"
            else -> "5"
        }
        val credentials = userInfo(uri)
        val outbound = JSONObject()
            .put("type", "socks")
            .put("tag", "proxy-out")
            .put("server", host)
            .put("server_port", port)
            .put("version", version)

        credentials.first?.let { outbound.put("username", it) }
        credentials.second?.let { outbound.put("password", it) }
        first(query, "network").takeIf { it == "tcp" || it == "udp" }?.let {
            outbound.put("network", it)
        }

        return ProxyProfile(scheme, "SOCKS$version-прокси $host:$port", outbound)
    }

    private fun parseVless(uri: URI, query: Map<String, List<String>>): ProxyProfile {
        val host = requireHost(uri)
        val port = requirePort(uri, 443)
        val uuid = userInfo(uri).first.orEmpty().trim()
        if (uuid.isEmpty()) throw ProfileException("В VLESS-ссылке отсутствует UUID перед символом @")

        val security = first(query, "security").lowercase()
        val realityPublicKey = first(query, "pbk", "publicKey", "public_key")
        val tlsEnabled = security == "tls" || security == "reality" || realityPublicKey.isNotEmpty()

        val outbound = JSONObject()
            .put("type", "vless")
            .put("tag", "proxy-out")
            .put("server", host)
            .put("server_port", port)
            .put("uuid", uuid)

        first(query, "flow").takeIf { it.isNotEmpty() }?.let { outbound.put("flow", it) }
        first(query, "network").takeIf { it == "tcp" || it == "udp" }?.let {
            outbound.put("network", it)
        }

        tlsConfig(
            enabled = tlsEnabled,
            serverName = first(query, "sni", "serverName", "server_name", default = host),
            insecure = bool(first(query, "insecure", "allowInsecure")),
            alpn = first(query, "alpn"),
            fingerprint = first(query, "fp", "fingerprint"),
            realityPublicKey = realityPublicKey,
            realityShortId = first(query, "sid", "shortId", "short_id"),
        )?.let { outbound.put("tls", it) }

        vlessTransport(query)?.let { outbound.put("transport", it) }
        first(query, "packetEncoding", "packet_encoding")
            .takeIf { it == "xudp" || it == "packetaddr" }
            ?.let { outbound.put("packet_encoding", it) }

        return ProxyProfile("vless", "VLESS $host:$port", outbound)
    }

    private fun parseHysteria2(uri: URI, query: Map<String, List<String>>): ProxyProfile {
        val host = requireHost(uri)
        val port = requirePort(uri, 443)
        val credentials = userInfo(uri)
        val password = first(query, "auth", "password").ifEmpty {
            credentials.second?.let { rawPassword ->
                if (credentials.first.isNullOrEmpty()) rawPassword else "${credentials.first}:$rawPassword"
            } ?: credentials.first.orEmpty()
        }
        if (password.isEmpty()) throw ProfileException("В Hysteria2-ссылке отсутствует пароль")

        val outbound = JSONObject()
            .put("type", "hysteria2")
            .put("tag", "proxy-out")
            .put("server", host)
            .put("server_port", port)
            .put("password", password)

        val serverPorts = first(query, "mport", "ports", "server_ports")
        if (serverPorts.isNotEmpty()) {
            outbound.remove("server_port")
            outbound.put("server_ports", JSONArray(splitCsv(serverPorts.replace("-", ":"))))
            first(query, "hopInterval", "hop_interval").takeIf { it.isNotEmpty() }?.let {
                outbound.put("hop_interval", it)
            }
        }

        first(query, "upmbps", "up_mbps", "up").takeIf { it.isNotEmpty() }?.let {
            outbound.put("up_mbps", intValue(it, "Скорость отдачи Hysteria2", 1, 1_000_000))
        }
        first(query, "downmbps", "down_mbps", "down").takeIf { it.isNotEmpty() }?.let {
            outbound.put("down_mbps", intValue(it, "Скорость загрузки Hysteria2", 1, 1_000_000))
        }

        val obfsType = first(query, "obfs").lowercase()
        if (obfsType.isNotEmpty()) {
            if (obfsType != "salamander" && obfsType != "gecko") {
                throw ProfileException("Неподдерживаемое Hysteria2 obfs: $obfsType")
            }
            outbound.put(
                "obfs",
                JSONObject()
                    .put("type", obfsType)
                    .put("password", first(query, "obfs-password", "obfs_password", "obfsParam")),
            )
        }

        outbound.put(
            "tls",
            tlsConfig(
                enabled = true,
                serverName = first(query, "sni", "serverName", "server_name", default = host),
                insecure = bool(first(query, "insecure", "allowInsecure")),
                alpn = first(query, "alpn"),
            ),
        )

        return ProxyProfile("hysteria2", "Hysteria2 $host:$port", outbound)
    }

    private fun vlessTransport(query: Map<String, List<String>>): JSONObject? {
        val type = first(query, "type", "transport").trim().lowercase()
        if (type.isEmpty() || type == "tcp" || type == "none" || type == "raw") return null

        val path = decode(first(query, "path"))
        val host = first(query, "host")
        return when (type) {
            "ws", "websocket" -> JSONObject().put("type", "ws").apply {
                if (path.isNotEmpty()) put("path", path)
                if (host.isNotEmpty()) put("headers", JSONObject().put("Host", host))
                first(query, "ed", "max_early_data").takeIf { it.isNotEmpty() }?.let {
                    put("max_early_data", intValue(it, "WebSocket early data", 0, 65535))
                }
                first(query, "eh", "early_data_header_name").takeIf { it.isNotEmpty() }?.let {
                    put("early_data_header_name", it)
                }
            }

            "grpc" -> JSONObject().put("type", "grpc").apply {
                val service = first(query, "serviceName", "service_name").ifEmpty { path.trimStart('/') }
                if (service.isNotEmpty()) put("service_name", service)
            }

            "httpupgrade", "http-upgrade" -> JSONObject().put("type", "httpupgrade").apply {
                if (host.isNotEmpty()) put("host", host)
                if (path.isNotEmpty()) put("path", path)
            }

            "http", "h2" -> JSONObject().put("type", "http").apply {
                if (host.isNotEmpty()) put("host", JSONArray(splitCsv(host)))
                if (path.isNotEmpty()) put("path", path)
            }

            "quic" -> JSONObject().put("type", "quic")
            else -> throw ProfileException("Неподдерживаемый транспорт VLESS: $type")
        }
    }

    private fun tlsConfig(
        enabled: Boolean,
        serverName: String,
        insecure: Boolean,
        alpn: String = "",
        fingerprint: String = "",
        realityPublicKey: String = "",
        realityShortId: String = "",
    ): JSONObject? {
        if (!enabled) return null
        return JSONObject()
            .put("enabled", true)
            .put("server_name", serverName)
            .put("insecure", insecure)
            .apply {
                if (alpn.isNotEmpty()) put("alpn", JSONArray(splitCsv(alpn)))
                if (fingerprint.isNotEmpty() && fingerprint.lowercase() !in setOf("none", "off", "disabled")) {
                    put("utls", JSONObject().put("enabled", true).put("fingerprint", fingerprint))
                }
                if (realityPublicKey.isNotEmpty()) {
                    put(
                        "reality",
                        JSONObject()
                            .put("enabled", true)
                            .put("public_key", realityPublicKey)
                            .put("short_id", realityShortId),
                    )
                }
            }
    }

    private fun parseQuery(rawQuery: String?): Map<String, List<String>> {
        if (rawQuery.isNullOrBlank()) return emptyMap()
        val result = linkedMapOf<String, MutableList<String>>()
        rawQuery.split('&').forEach { item ->
            if (item.isEmpty()) return@forEach
            val index = item.indexOf('=')
            val key = decode(if (index >= 0) item.substring(0, index) else item)
            val value = decode(if (index >= 0) item.substring(index + 1) else "")
            result.getOrPut(key) { mutableListOf() }.add(value)
        }
        return result
    }

    private fun first(query: Map<String, List<String>>, vararg keys: String, default: String = ""): String {
        for (key in keys) query[key]?.firstOrNull()?.let { return it }
        return default
    }

    private fun requireHost(uri: URI): String {
        return uri.host?.trim()?.takeIf { it.isNotEmpty() }
            ?: throw ProfileException("Ссылка профиля должна содержать адрес сервера")
    }

    private fun requirePort(uri: URI, default: Int): Int {
        val port = if (uri.port == -1) default else uri.port
        if (port !in 1..65535) throw ProfileException("Порт сервера должен быть от 1 до 65535")
        return port
    }

    private fun userInfo(uri: URI): Pair<String?, String?> {
        val raw = uri.rawUserInfo ?: return null to null
        val index = raw.indexOf(':')
        return if (index < 0) {
            decode(raw) to null
        } else {
            decode(raw.substring(0, index)) to decode(raw.substring(index + 1))
        }
    }

    private fun bool(value: String): Boolean = value.trim().lowercase() in setOf("1", "true", "yes", "on", "enabled")

    private fun intValue(value: String, field: String, minimum: Int, maximum: Int): Int {
        val number = value.toIntOrNull() ?: throw ProfileException("$field должно быть числом")
        if (number !in minimum..maximum) throw ProfileException("$field должно быть от $minimum до $maximum")
        return number
    }

    private fun splitCsv(value: String): List<String> = value.split(',').map { it.trim() }.filter { it.isNotEmpty() }

    private fun decode(value: String): String {
        return try {
            // URLDecoder treats '+' as a space; proxy links commonly use '+' literally in credentials.
            URLDecoder.decode(value.replace("+", "%2B"), StandardCharsets.UTF_8.name())
        } catch (error: Exception) {
            throw ProfileException("В ссылке профиля содержится неверное percent-кодирование", error)
        }
    }
}

object SingBoxConfigBuilder {
    fun build(
        profileUri: String,
        listenPort: Int,
        logLevel: String = "warn",
    ): Pair<ProxyProfile, JSONObject> {
        if (listenPort !in 1..65535) throw ProfileException("Локальный порт должен быть от 1 до 65535")
        val profile = ProfileParser.parse(profileUri)
        val inbound = JSONObject()
            .put("type", "mixed")
            .put("tag", "mixed-in")
            .put("listen", "127.0.0.1")
            .put("listen_port", listenPort)

        // The standalone Android core cannot use the graphical client's platform DNS API.
        // Some ROMs expose localhost/::1 as the system resolver to child processes even though
        // no DNS daemon is reachable from the app sandbox. Use a bootstrap-free DoH endpoint
        // addressed by IP so upstream hostnames can always be resolved.
        val dnsTag = "bootstrap-doh"
        val dns = JSONObject()
            .put(
                "servers",
                JSONArray().put(
                    JSONObject()
                        .put("type", "https")
                        .put("tag", dnsTag)
                        .put("server", "1.1.1.1")
                        .put("server_port", 443)
                        .put("path", "/dns-query")
                        .put(
                            "tls",
                            JSONObject()
                                .put("enabled", true)
                                .put("server_name", "cloudflare-dns.com"),
                        ),
                ),
            )
            .put("final", dnsTag)
            .put("strategy", "prefer_ipv4")

        profile.outbound.put("domain_resolver", dnsTag)

        val config = JSONObject()
            .put("log", JSONObject().put("level", logLevel).put("timestamp", true))
            .put("dns", dns)
            .put("inbounds", JSONArray().put(inbound))
            .put("outbounds", JSONArray().put(profile.outbound))
            .put(
                "route",
                JSONObject()
                    .put("final", "proxy-out")
                    .put("auto_detect_interface", true)
                    .put("default_domain_resolver", dnsTag),
            )
        return profile to config
    }
}
