from pathlib import Path

import pytest

from tunnelgram.proxy_profiles import (
    ProxyProfileError,
    build_singbox_config,
    parse_proxy_uri,
    redact_proxy_uri,
    telegram_socks_link,
    write_singbox_config,
    write_singbox_runtime_config,
)


def test_http_profile_with_auth() -> None:
    profile = parse_proxy_uri("https://alice:secret@proxy.example:8443?allowInsecure=1")
    assert profile.outbound["type"] == "http"
    assert profile.outbound["username"] == "alice"
    assert profile.outbound["password"] == "secret"
    assert profile.outbound["tls"]["enabled"] is True
    assert profile.outbound["tls"]["insecure"] is True


def test_socks_profile() -> None:
    profile = parse_proxy_uri("socks5://u:p@127.0.0.1:1080")
    assert profile.outbound == {
        "type": "socks",
        "tag": "proxy-out",
        "server": "127.0.0.1",
        "server_port": 1080,
        "version": "5",
        "username": "u",
        "password": "p",
    }


def test_vless_reality_websocket_profile() -> None:
    profile = parse_proxy_uri(
        "vless://11111111-1111-1111-1111-111111111111@example.com:443"
        "?security=reality&sni=cdn.example.com&fp=chrome&pbk=public-key&sid=abcd"
        "&type=ws&path=%2Ftelegram&host=cdn.example.com"
    )
    outbound = profile.outbound
    assert outbound["type"] == "vless"
    assert outbound["tls"]["reality"]["public_key"] == "public-key"
    assert outbound["transport"]["type"] == "ws"
    assert outbound["transport"]["path"] == "/telegram"


def test_hysteria2_profile_and_port_hopping() -> None:
    profile = parse_proxy_uri(
        "hysteria2://user:pass@example.com:443?sni=cdn.example.com&obfs=salamander"
        "&obfs-password=mask&mport=20000-20010,30000"
    )
    outbound = profile.outbound
    assert outbound["password"] == "user:pass"
    assert outbound["server_ports"] == ["20000:20010", "30000"]
    assert "server_port" not in outbound
    assert outbound["obfs"] == {"type": "salamander", "password": "mask"}


def test_mixed_inbound_auth_and_route() -> None:
    profile, config = build_singbox_config(
        "socks5://upstream.example:1080",
        listen_host="127.0.0.1",
        listen_port=9443,
        local_username="local",
        local_password="password",
    )
    assert profile.scheme == "socks5"
    assert config["inbounds"][0]["type"] == "mixed"
    assert config["inbounds"][0]["users"] == [{"username": "local", "password": "password"}]
    assert config["route"]["final"] == "proxy-out"


def test_local_auth_requires_pair() -> None:
    with pytest.raises(ProxyProfileError):
        build_singbox_config(
            "http://proxy.example:8080",
            listen_host="127.0.0.1",
            listen_port=8080,
            local_username="only-user",
        )


def test_write_config_is_json(tmp_path: Path) -> None:
    _, config = build_singbox_config(
        "http://proxy.example:8080",
        listen_host="127.0.0.1",
        listen_port=1080,
    )
    path = write_singbox_config(tmp_path / "sing-box.json", config)
    assert '"type": "mixed"' in path.read_text(encoding="utf-8")


def test_telegram_link_and_redaction() -> None:
    link = telegram_socks_link("127.0.0.1", 1080, "alice", "hello world")
    assert link.startswith("tg://socks?")
    assert "hello%20world" in link
    assert redact_proxy_uri("vless://uuid@example.com:443?security=tls") == "vless://***@example.com:443"


def test_write_runtime_config_uses_existing_absolute_file(tmp_path: Path) -> None:
    _, config = build_singbox_config(
        "http://proxy.example:8080",
        listen_host="127.0.0.1",
        listen_port=1080,
    )
    path = write_singbox_runtime_config(config, tmp_path / "runtime")
    try:
        assert path.is_absolute()
        assert path.is_file()
        assert path.parent == (tmp_path / "runtime").resolve()
        assert path.stat().st_size > 0
    finally:
        path.unlink(missing_ok=True)
