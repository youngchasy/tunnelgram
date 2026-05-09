from __future__ import annotations

import argparse
import asyncio
import logging
import socket
import ssl
import sys
import time

from .mtproto import FLOWSEAL_WS_PIN_IP
from .telegram_ws import (
    RawTelegramWebSocket,
    WsEndpoint,
    cloudflare_kws_domains,
    official_kws_domains,
    official_named_domains,
)


async def _tcp_probe(host: str, port: int, timeout: float) -> tuple[bool, str, float]:
    start = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True, "ok", time.monotonic() - start
    except Exception as exc:
        return False, repr(exc), time.monotonic() - start


async def _tls_probe(connect_host: str, sni: str, timeout: float) -> tuple[bool, str, float]:
    start = time.monotonic()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(connect_host, 443, ssl=ctx, server_hostname=sni), timeout=timeout
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True, "ok", time.monotonic() - start
    except Exception as exc:
        return False, repr(exc), time.monotonic() - start


async def _ws_probe(domain: str, connect_host: str, timeout: float) -> tuple[bool, str, float]:
    start = time.monotonic()
    try:
        ws = await RawTelegramWebSocket.connect(WsEndpoint(2, domain, connect_host), timeout=timeout)
        await ws.close()
        return True, "HTTP 101 Switching Protocols", time.monotonic() - start
    except Exception as exc:
        return False, repr(exc), time.monotonic() - start


def _domains(args) -> list[str]:
    if args.route_mode == "cloudflare":
        return cloudflare_kws_domains(2, False, args.cf_domain)
    if args.domain_style == "names":
        return official_named_domains(2, False)
    return official_kws_domains(2, False)


async def main_async(args) -> int:
    domains = _domains(args)
    print("TunnelGram WSS diagnostics")
    print(f"route_mode={args.route_mode} domain_style={args.domain_style} pin={args.pin_telegram_ip}")
    if args.pin_telegram_ip:
        print(f"pinned connect_host={FLOWSEAL_WS_PIN_IP}")
    print()

    any_ok = False
    for domain in domains:
        connect_host = FLOWSEAL_WS_PIN_IP if (args.route_mode == "telegram" and args.pin_telegram_ip) else domain
        print(f"== {domain} via {connect_host} ==")

        # Resolve only when using hostname, not pinned IP.
        if connect_host == domain:
            try:
                infos = socket.getaddrinfo(connect_host, 443, type=socket.SOCK_STREAM)
                addrs = sorted({info[4][0] for info in infos})
                print("DNS:", ", ".join(addrs[:8]) or "no addresses")
            except Exception as exc:
                print("DNS: FAIL", repr(exc))

        ok, msg, elapsed = await _tcp_probe(connect_host, 443, args.timeout)
        print(f"TCP : {'OK ' if ok else 'FAIL'} {elapsed:.2f}s {msg}")
        ok, msg, elapsed = await _tls_probe(connect_host, domain, args.timeout)
        print(f"TLS : {'OK ' if ok else 'FAIL'} {elapsed:.2f}s {msg}")
        ok, msg, elapsed = await _ws_probe(domain, connect_host, args.timeout)
        print(f"WSS : {'OK ' if ok else 'FAIL'} {elapsed:.2f}s {msg}")
        print()
        any_ok = any_ok or ok

    if any_ok:
        print("At least one Telegram WSS endpoint accepts WebSocket handshakes.")
        return 0
    print("No WSS endpoint succeeded. Try: disable Pin Telegram IP, switch domain style, or use TCP fallback/Cloudflare DNS proxy.")
    return 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Telegram WSS endpoint connectivity")
    parser.add_argument("--route-mode", choices=["telegram", "cloudflare"], default="telegram")
    parser.add_argument("--domain-style", choices=["kws", "names"], default="kws")
    parser.add_argument("--cf-domain", default="")
    parser.add_argument("--pin-telegram-ip", action="store_true")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--verbose", action="store_true")
    logging.basicConfig(level=logging.DEBUG if parser.parse_known_args()[0].verbose else logging.INFO)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
