from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit


class ProxyProfileError(ValueError):
    """Raised when an upstream proxy URI cannot be parsed safely."""


SUPPORTED_SCHEMES = {
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
}


@dataclass(frozen=True)
class ProxyProfile:
    scheme: str
    name: str
    outbound: dict[str, Any]


def _first(query: dict[str, list[str]], *keys: str, default: str = "") -> str:
    for key in keys:
        values = query.get(key)
        if values:
            return values[0]
    return default


def _bool(value: str | bool | None, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _int(value: str, *, field: str, minimum: int = 1, maximum: int = 65535) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ProxyProfileError(f"{field} must be a number") from exc
    if not (minimum <= number <= maximum):
        raise ProxyProfileError(f"{field} must be between {minimum} and {maximum}")
    return number


def _host_port(parts, default_port: int) -> tuple[str, int]:
    host = (parts.hostname or "").strip()
    if not host:
        raise ProxyProfileError("Proxy URI must contain a server address")
    try:
        port = parts.port or default_port
    except ValueError as exc:
        raise ProxyProfileError("Proxy URI contains an invalid port") from exc
    return host, _int(str(port), field="Server port")


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _tls_config(
    *,
    enabled: bool,
    server_name: str,
    insecure: bool,
    alpn: str = "",
    fingerprint: str = "",
    reality_public_key: str = "",
    reality_short_id: str = "",
) -> dict[str, Any] | None:
    if not enabled:
        return None

    tls: dict[str, Any] = {
        "enabled": True,
        "server_name": server_name,
        "insecure": insecure,
    }
    if alpn:
        tls["alpn"] = _split_csv(alpn)
    if fingerprint and fingerprint.lower() not in {"none", "off", "disabled"}:
        # A large number of existing VLESS links still carry fp=chrome.
        # sing-box supports this through the uTLS compatibility block.
        tls["utls"] = {"enabled": True, "fingerprint": fingerprint}
    if reality_public_key:
        tls["reality"] = {
            "enabled": True,
            "public_key": reality_public_key,
            "short_id": reality_short_id,
        }
    return tls


def _parse_http(parts, query: dict[str, list[str]]) -> ProxyProfile:
    scheme = parts.scheme.lower()
    host, port = _host_port(parts, 443 if scheme == "https" else 80)
    outbound: dict[str, Any] = {
        "type": "http",
        "tag": "proxy-out",
        "server": host,
        "server_port": port,
    }
    if parts.username is not None:
        outbound["username"] = unquote(parts.username)
    if parts.password is not None:
        outbound["password"] = unquote(parts.password)

    path = unquote(parts.path or "")
    if path and path != "/":
        outbound["path"] = path

    if scheme == "https":
        sni = _first(query, "sni", "serverName", "server_name", default=host)
        outbound["tls"] = _tls_config(
            enabled=True,
            server_name=sni,
            insecure=_bool(_first(query, "insecure", "allowInsecure")),
            alpn=_first(query, "alpn"),
        )

    return ProxyProfile(scheme=scheme, name=f"HTTP proxy {host}:{port}", outbound=outbound)


def _parse_socks(parts, query: dict[str, list[str]]) -> ProxyProfile:
    scheme = parts.scheme.lower()
    host, port = _host_port(parts, 1080)
    version = {
        "socks4": "4",
        "socks4a": "4a",
    }.get(scheme, "5")
    outbound: dict[str, Any] = {
        "type": "socks",
        "tag": "proxy-out",
        "server": host,
        "server_port": port,
        "version": version,
    }
    if parts.username is not None:
        outbound["username"] = unquote(parts.username)
    if parts.password is not None:
        outbound["password"] = unquote(parts.password)

    network = _first(query, "network")
    if network in {"tcp", "udp"}:
        outbound["network"] = network

    return ProxyProfile(scheme=scheme, name=f"SOCKS{version} proxy {host}:{port}", outbound=outbound)


def _vless_transport(query: dict[str, list[str]]) -> dict[str, Any] | None:
    transport_type = _first(query, "type", "transport").strip().lower()
    if not transport_type or transport_type in {"tcp", "none", "raw"}:
        return None

    path = unquote(_first(query, "path"))
    host = _first(query, "host")

    if transport_type in {"ws", "websocket"}:
        transport: dict[str, Any] = {"type": "ws"}
        if path:
            transport["path"] = path
        if host:
            transport["headers"] = {"Host": host}
        early_data = _first(query, "ed", "max_early_data")
        if early_data:
            transport["max_early_data"] = _int(early_data, field="WebSocket early data", minimum=0, maximum=65535)
        early_header = _first(query, "eh", "early_data_header_name")
        if early_header:
            transport["early_data_header_name"] = early_header
        return transport

    if transport_type == "grpc":
        transport = {"type": "grpc"}
        service = _first(query, "serviceName", "service_name") or path.lstrip("/")
        if service:
            transport["service_name"] = service
        return transport

    if transport_type in {"httpupgrade", "http-upgrade"}:
        transport = {"type": "httpupgrade"}
        if host:
            transport["host"] = host
        if path:
            transport["path"] = path
        return transport

    if transport_type in {"http", "h2"}:
        transport = {"type": "http"}
        if host:
            transport["host"] = _split_csv(host)
        if path:
            transport["path"] = path
        return transport

    if transport_type == "quic":
        return {"type": "quic"}

    raise ProxyProfileError(f"Unsupported VLESS transport: {transport_type}")


def _parse_vless(parts, query: dict[str, list[str]]) -> ProxyProfile:
    host, port = _host_port(parts, 443)
    uuid = unquote(parts.username or "").strip()
    if not uuid:
        raise ProxyProfileError("VLESS URI must contain a UUID before @")

    security = _first(query, "security").strip().lower()
    reality_public_key = _first(query, "pbk", "publicKey", "public_key")
    reality_short_id = _first(query, "sid", "shortId", "short_id")
    tls_enabled = security in {"tls", "reality"} or bool(reality_public_key)
    sni = _first(query, "sni", "serverName", "server_name", default=host)

    outbound: dict[str, Any] = {
        "type": "vless",
        "tag": "proxy-out",
        "server": host,
        "server_port": port,
        "uuid": uuid,
    }

    flow = _first(query, "flow")
    if flow:
        outbound["flow"] = flow

    network = _first(query, "network")
    if network in {"tcp", "udp"}:
        outbound["network"] = network

    tls = _tls_config(
        enabled=tls_enabled,
        server_name=sni,
        insecure=_bool(_first(query, "insecure", "allowInsecure")),
        alpn=_first(query, "alpn"),
        fingerprint=_first(query, "fp", "fingerprint"),
        reality_public_key=reality_public_key,
        reality_short_id=reality_short_id,
    )
    if tls:
        outbound["tls"] = tls

    transport = _vless_transport(query)
    if transport:
        outbound["transport"] = transport

    packet_encoding = _first(query, "packetEncoding", "packet_encoding")
    if packet_encoding in {"xudp", "packetaddr"}:
        outbound["packet_encoding"] = packet_encoding

    return ProxyProfile(scheme="vless", name=f"VLESS {host}:{port}", outbound=outbound)


def _parse_hysteria2(parts, query: dict[str, list[str]]) -> ProxyProfile:
    host, port = _host_port(parts, 443)
    # Common links use hysteria2://PASSWORD@host:port. urlsplit exposes the
    # value as username when no colon is present.
    password = _first(query, "auth", "password")
    if not password:
        if parts.password is not None:
            username = unquote(parts.username or "")
            raw_password = unquote(parts.password)
            password = f"{username}:{raw_password}" if username else raw_password
        else:
            password = unquote(parts.username or "")
    if not password:
        raise ProxyProfileError("Hysteria2 URI must contain an authentication password")

    outbound: dict[str, Any] = {
        "type": "hysteria2",
        "tag": "proxy-out",
        "server": host,
        "server_port": port,
        "password": password,
    }

    server_ports = _first(query, "mport", "ports", "server_ports")
    if server_ports:
        outbound.pop("server_port", None)
        outbound["server_ports"] = _split_csv(server_ports.replace("-", ":"))
        hop_interval = _first(query, "hopInterval", "hop_interval")
        if hop_interval:
            outbound["hop_interval"] = hop_interval

    up = _first(query, "upmbps", "up_mbps", "up")
    down = _first(query, "downmbps", "down_mbps", "down")
    if up:
        outbound["up_mbps"] = _int(up, field="Hysteria2 upload Mbps", minimum=1, maximum=1_000_000)
    if down:
        outbound["down_mbps"] = _int(down, field="Hysteria2 download Mbps", minimum=1, maximum=1_000_000)

    obfs_type = _first(query, "obfs").strip().lower()
    obfs_password = _first(query, "obfs-password", "obfs_password", "obfsParam")
    if obfs_type:
        if obfs_type not in {"salamander", "gecko"}:
            raise ProxyProfileError(f"Unsupported Hysteria2 obfuscation: {obfs_type}")
        outbound["obfs"] = {"type": obfs_type, "password": obfs_password}

    sni = _first(query, "sni", "serverName", "server_name", default=host)
    outbound["tls"] = _tls_config(
        enabled=True,
        server_name=sni,
        insecure=_bool(_first(query, "insecure", "allowInsecure")),
        alpn=_first(query, "alpn"),
    )

    return ProxyProfile(scheme="hysteria2", name=f"Hysteria2 {host}:{port}", outbound=outbound)


def parse_proxy_uri(uri: str) -> ProxyProfile:
    value = uri.strip()
    if not value:
        raise ProxyProfileError("Enter an upstream proxy URI")

    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    if scheme not in SUPPORTED_SCHEMES:
        allowed = ", ".join(sorted(SUPPORTED_SCHEMES))
        raise ProxyProfileError(f"Unsupported proxy URI scheme: {scheme or '(missing)'}. Supported: {allowed}")

    query = parse_qs(parts.query, keep_blank_values=True)
    if scheme in {"http", "https"}:
        return _parse_http(parts, query)
    if scheme in {"socks", "socks4", "socks4a", "socks5", "socks5h"}:
        return _parse_socks(parts, query)
    if scheme == "vless":
        return _parse_vless(parts, query)
    return _parse_hysteria2(parts, query)


def build_singbox_config(
    uri: str,
    *,
    listen_host: str,
    listen_port: int,
    local_username: str = "",
    local_password: str = "",
    log_level: str = "info",
) -> tuple[ProxyProfile, dict[str, Any]]:
    profile = parse_proxy_uri(uri)
    inbound: dict[str, Any] = {
        "type": "mixed",
        "tag": "mixed-in",
        "listen": listen_host,
        "listen_port": listen_port,
    }
    if local_username or local_password:
        if not local_username or not local_password:
            raise ProxyProfileError("Local proxy username and password must be set together")
        inbound["users"] = [{"username": local_username, "password": local_password}]

    config: dict[str, Any] = {
        "log": {"level": log_level, "timestamp": True},
        "inbounds": [inbound],
        "outbounds": [profile.outbound],
        "route": {"final": "proxy-out", "auto_detect_interface": True},
    }
    return profile, config


def write_singbox_config(path: Path, config: dict[str, Any]) -> Path:
    """Write a sing-box config atomically and return its absolute path."""
    path = path.expanduser().absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    payload = json.dumps(config, indent=2, ensure_ascii=False) + "\n"

    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass

    resolved = path.resolve(strict=True)
    if resolved.stat().st_size == 0:
        raise OSError(f"sing-box config was written as an empty file: {resolved}")

    if os.name != "nt":
        try:
            resolved.chmod(0o600)
        except OSError:
            pass
    return resolved


def write_singbox_runtime_config(
    config: dict[str, Any],
    directory: Path | None = None,
) -> Path:
    """Create a unique runtime config in the user's temporary directory.

    Keeping the runtime file out of roaming AppData avoids a Windows issue where
    an external sing-box process can occasionally fail to see a newly-created
    file there, even though TunnelGram itself has just written it.
    """
    runtime_dir = (directory or (Path(tempfile.gettempdir()) / "tunnelgram")).expanduser().absolute()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    fd, raw_path = tempfile.mkstemp(prefix="sing-box-", suffix=".json", dir=str(runtime_dir))
    os.close(fd)
    path = Path(raw_path)
    try:
        return write_singbox_config(path, config)
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _binary_names() -> tuple[str, ...]:
    return ("sing-box.exe", "sing-box") if os.name == "nt" else ("sing-box",)


def find_sing_box_binary(explicit_path: str = "") -> Path:
    candidates: list[Path] = []
    if explicit_path.strip():
        candidates.append(Path(explicit_path.strip()).expanduser())

    env_path = os.getenv("TUNNELGRAM_SING_BOX", "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())

    executable = Path(sys.executable).resolve()
    module_root = Path(__file__).resolve().parents[1]
    roots = [module_root, executable.parent, Path.cwd()]
    if getattr(sys, "_MEIPASS", None):
        roots.insert(0, Path(getattr(sys, "_MEIPASS")))
    if sys.platform == "darwin":
        # Frozen .app: Contents/MacOS/tunnelgram -> Contents/Resources/sing-box.
        roots.append(executable.parent.parent / "Resources")
        try:
            roots.append(executable.parents[3])
        except IndexError:
            pass

    for root in roots:
        for name in _binary_names():
            candidates.extend((root / name, root / "core" / name, root / "bin" / name))

    which = shutil_which("sing-box")
    if which:
        candidates.append(Path(which))

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            return candidate.resolve()

    raise FileNotFoundError(
        "sing-box core was not found. Put sing-box next to tunnelgram, install it in PATH, "
        "or select the binary in settings."
    )


def shutil_which(command: str) -> str | None:
    # Local helper keeps this module import-light for frozen builds.
    from shutil import which

    return which(command)


def telegram_socks_link(host: str, port: int, username: str = "", password: str = "") -> str:
    params = {"server": host, "port": str(port)}
    if username:
        params["user"] = username
    if password:
        params["pass"] = password
    return "tg://socks?" + urlencode(params, quote_via=quote)


def redact_proxy_uri(uri: str) -> str:
    """Return a display-safe URI that does not expose passwords or UUIDs."""
    try:
        parts = urlsplit(uri.strip())
    except Exception:
        return ""
    if not parts.scheme:
        return ""
    host = parts.hostname or "?"
    try:
        parsed_port = parts.port
    except ValueError:
        parsed_port = None
    port = f":{parsed_port}" if parsed_port else ""
    return f"{parts.scheme.lower()}://***@{host}{port}"
