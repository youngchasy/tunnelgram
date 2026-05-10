from __future__ import annotations

import argparse
import asyncio
import logging
import socket
import ssl
import time
from dataclasses import dataclass

from .mtproto import FLOWSEAL_WS_PIN_IP
from .telegram_ws import (
    RawTelegramWebSocket,
    WsEndpoint,
    cloudflare_kws_domains,
    official_kws_domains,
    official_named_domains,
)


LANGUAGES = {"ru", "en"}

TEXT = {
    "ru": {
        "title": "TunnelGram WSS diagnostics",
        "config": "Настройки",
        "route_mode": "route_mode",
        "domain_style": "domain_style",
        "pin": "pin",
        "dc": "DC",
        "yes": "да",
        "no": "нет",
        "domain": "Домен",
        "dns_ipv4": "DNS IPv4",
        "dns_ipv6": "DNS IPv6",
        "none": "нет",
        "target": "Цель",
        "tcp": "TCP",
        "tls": "TLS",
        "wss": "WSS",
        "ok": "OK",
        "fail": "FAIL",
        "skip": "SKIP",
        "connected": "connected",
        "tls_ok": "TLS connected",
        "wss_ok": "HTTP 101 Switching Protocols",
        "skip_tcp": "пропущено, потому что TCP не подключился",
        "skip_tls": "пропущено, потому что TCP/TLS не подключились",
        "timeout": "timeout",
        "dns_failed": "DNS lookup failed",
        "target_dns": "DNS IPv4 {ip}",
        "target_pinned": "pinned Telegram IP {ip}",
        "target_cf": "Cloudflare/DNS IPv4 {ip}",
        "summary": "Итог",
        "summary_ok": "Найден рабочий WSS endpoint.",
        "summary_fail": "Рабочий WSS endpoint не найден.",
        "recommendation": "Рекомендация",
        "recommend_pin": "DNS endpoint не работает, но pinned Telegram IP работает. Включи Pin Telegram IP в настройках.",
        "recommend_keep_pin": "Pinned Telegram IP работает. Текущая настройка Pin Telegram IP выглядит правильной.",
        "recommend_dns_ok": "Обычный DNS endpoint работает. Pin Telegram IP можно не включать.",
        "recommend_no_ipv4": "DNS не вернул IPv4-адреса. Проверь DNS, сеть или попробуй Pin Telegram IP.",
        "recommend_network": "TCP до Telegram WSS не проходит. Проверь сеть, VPN, firewall, DNS или попробуй другую сеть.",
        "recommend_cloudflare": "Cloudflare/DNS endpoint не работает. Проверь домен, DNS proxy и SSL/TLS настройки Cloudflare.",
        "note_404": "Если curl показывает HTTP 404 для /apiws — это нормально. Для WSS нужен WebSocket Upgrade.",
    },
    "en": {
        "title": "TunnelGram WSS diagnostics",
        "config": "Config",
        "route_mode": "route_mode",
        "domain_style": "domain_style",
        "pin": "pin",
        "dc": "DC",
        "yes": "yes",
        "no": "no",
        "domain": "Domain",
        "dns_ipv4": "DNS IPv4",
        "dns_ipv6": "DNS IPv6",
        "none": "none",
        "target": "Target",
        "tcp": "TCP",
        "tls": "TLS",
        "wss": "WSS",
        "ok": "OK",
        "fail": "FAIL",
        "skip": "SKIP",
        "connected": "connected",
        "tls_ok": "TLS connected",
        "wss_ok": "HTTP 101 Switching Protocols",
        "skip_tcp": "skipped because TCP did not connect",
        "skip_tls": "skipped because TCP/TLS did not connect",
        "timeout": "timeout",
        "dns_failed": "DNS lookup failed",
        "target_dns": "DNS IPv4 {ip}",
        "target_pinned": "pinned Telegram IP {ip}",
        "target_cf": "Cloudflare/DNS IPv4 {ip}",
        "summary": "Summary",
        "summary_ok": "At least one WSS endpoint works.",
        "summary_fail": "No working WSS endpoint found.",
        "recommendation": "Recommendation",
        "recommend_pin": "DNS endpoint failed, but pinned Telegram IP works. Enable Pin Telegram IP in settings.",
        "recommend_keep_pin": "Pinned Telegram IP works. The current Pin Telegram IP setting looks correct.",
        "recommend_dns_ok": "The normal DNS endpoint works. Pin Telegram IP is not required.",
        "recommend_no_ipv4": "DNS returned no IPv4 addresses. Check DNS/network or try Pin Telegram IP.",
        "recommend_network": "TCP to Telegram WSS does not pass. Check network, VPN, firewall, DNS, or try another network.",
        "recommend_cloudflare": "Cloudflare/DNS endpoint failed. Check your domain, DNS proxy, and Cloudflare SSL/TLS settings.",
        "note_404": "If curl shows HTTP 404 for /apiws, that is normal. WSS requires a WebSocket Upgrade.",
    },
}


def tr(args, key: str, **kwargs) -> str:
    language = getattr(args, "language", "en")
    if language not in LANGUAGES:
        language = "en"

    text = TEXT.get(language, {}).get(key) or TEXT["en"].get(key) or key

    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text

    return text


@dataclass
class ProbeResult:
    ok: bool
    message: str
    elapsed: float


@dataclass
class TargetResult:
    label: str
    connect_host: str
    tcp: ProbeResult
    tls: ProbeResult
    wss: ProbeResult


def compact_error(exc: Exception, args) -> str:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return tr(args, "timeout")

    text = repr(exc)

    if not text or text == "TimeoutError()":
        return tr(args, "timeout")

    return text


def resolve_addresses(host: str, family: socket.AddressFamily) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, 443, family=family, type=socket.SOCK_STREAM)
    except Exception:
        return []

    result = []

    for info in infos:
        try:
            ip = info[4][0]
        except Exception:
            continue

        if ip not in result:
            result.append(ip)

    return result


async def tcp_probe(connect_host: str, timeout: float, args) -> ProbeResult:
    start = time.monotonic()

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                connect_host,
                443,
                family=socket.AF_INET,
            ),
            timeout=timeout,
        )

        writer.close()

        try:
            await writer.wait_closed()
        except Exception:
            pass

        return ProbeResult(True, tr(args, "connected"), time.monotonic() - start)

    except Exception as exc:
        return ProbeResult(False, compact_error(exc, args), time.monotonic() - start)


async def tls_probe(connect_host: str, sni: str, timeout: float, args) -> ProbeResult:
    start = time.monotonic()

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                connect_host,
                443,
                ssl=ctx,
                server_hostname=sni,
                family=socket.AF_INET,
            ),
            timeout=timeout,
        )

        ssl_object = writer.get_extra_info("ssl_object")
        version = ssl_object.version() if ssl_object is not None else tr(args, "tls_ok")

        writer.close()

        try:
            await writer.wait_closed()
        except Exception:
            pass

        return ProbeResult(True, str(version), time.monotonic() - start)

    except Exception as exc:
        return ProbeResult(False, compact_error(exc, args), time.monotonic() - start)


async def wss_probe(domain: str, connect_host: str, timeout: float, args) -> ProbeResult:
    start = time.monotonic()

    try:
        ws = await RawTelegramWebSocket.connect(
            WsEndpoint(
                dc_id=args.dc,
                domain=domain,
                connect_host=connect_host,
            ),
            timeout=timeout,
        )

        await ws.close()

        return ProbeResult(True, tr(args, "wss_ok"), time.monotonic() - start)

    except Exception as exc:
        return ProbeResult(False, compact_error(exc, args), time.monotonic() - start)


def format_result(name: str, result: ProbeResult, args) -> str:
    status = tr(args, "ok") if result.ok else tr(args, "fail")
    return f"  {name:<4}: {status:<4} {result.elapsed:.2f}s  {result.message}"


def format_skip(name: str, reason: str, args) -> str:
    return f"  {name:<4}: {tr(args, 'skip'):<4} 0.00s  {reason}"


async def run_target(label: str, domain: str, connect_host: str, args) -> TargetResult:
    print(f"{tr(args, 'target')}: {label}")
    print(f"  connect_host: {connect_host}")
    print(f"  sni/host    : {domain}")

    tcp = await tcp_probe(connect_host, args.timeout, args)
    print(format_result(tr(args, "tcp"), tcp, args))

    if not tcp.ok:
        tls = ProbeResult(False, tr(args, "skip_tcp"), 0.0)
        wss = ProbeResult(False, tr(args, "skip_tls"), 0.0)

        print(format_skip(tr(args, "tls"), tls.message, args))
        print(format_skip(tr(args, "wss"), wss.message, args))
        print()

        return TargetResult(label, connect_host, tcp, tls, wss)

    tls = await tls_probe(connect_host, domain, args.timeout, args)
    print(format_result(tr(args, "tls"), tls, args))

    if not tls.ok:
        wss = ProbeResult(False, tr(args, "skip_tls"), 0.0)

        print(format_skip(tr(args, "wss"), wss.message, args))
        print()

        return TargetResult(label, connect_host, tcp, tls, wss)

    wss = await wss_probe(domain, connect_host, args.timeout, args)
    print(format_result(tr(args, "wss"), wss, args))
    print()

    return TargetResult(label, connect_host, tcp, tls, wss)


def domains_for_args(args) -> list[str]:
    if args.route_mode == "cloudflare":
        return cloudflare_kws_domains(args.dc, args.media, args.cf_domain)

    if args.domain_style == "names":
        return official_named_domains(args.dc, args.media)

    return official_kws_domains(args.dc, args.media)


def print_dns(domain: str, ipv4: list[str], ipv6: list[str], args) -> None:
    print(f"{tr(args, 'domain')}: {domain}")
    print(f"{tr(args, 'dns_ipv4')}: {', '.join(ipv4) if ipv4 else tr(args, 'none')}")
    print(f"{tr(args, 'dns_ipv6')}: {', '.join(ipv6) if ipv6 else tr(args, 'none')}")


def recommendation_for_results(results: list[TargetResult], ipv4: list[str], args) -> str:
    dns_results = [r for r in results if r.label.startswith("DNS") or r.label.startswith("Cloudflare")]
    pinned_results = [r for r in results if "pinned" in r.label.lower()]

    dns_wss_ok = any(r.wss.ok for r in dns_results)
    pinned_wss_ok = any(r.wss.ok for r in pinned_results)

    if args.route_mode == "cloudflare":
        if dns_wss_ok:
            return tr(args, "recommend_dns_ok")
        return tr(args, "recommend_cloudflare")

    if args.pin_telegram_ip:
        if pinned_wss_ok:
            return tr(args, "recommend_keep_pin")
        return tr(args, "recommend_network")

    if dns_wss_ok:
        return tr(args, "recommend_dns_ok")

    if pinned_wss_ok:
        return tr(args, "recommend_pin")

    if not ipv4:
        return tr(args, "recommend_no_ipv4")

    return tr(args, "recommend_network")


async def main_async(args) -> int:
    print(tr(args, "title"))
    print(
        f"{tr(args, 'config')}: "
        f"{tr(args, 'route_mode')}={args.route_mode} "
        f"{tr(args, 'domain_style')}={args.domain_style} "
        f"{tr(args, 'pin')}={args.pin_telegram_ip} "
        f"{tr(args, 'dc')}={args.dc}"
    )
    print(tr(args, "note_404"))
    print()

    domains = domains_for_args(args)
    all_results: list[TargetResult] = []

    for domain in domains:
        ipv4 = resolve_addresses(domain, socket.AF_INET)
        ipv6 = resolve_addresses(domain, socket.AF_INET6)

        print(f"== {domain} ==")
        print_dns(domain, ipv4, ipv6, args)
        print()

        targets: list[tuple[str, str]] = []

        if args.route_mode == "telegram" and args.pin_telegram_ip:
            targets.append((tr(args, "target_pinned", ip=FLOWSEAL_WS_PIN_IP), FLOWSEAL_WS_PIN_IP))

        elif args.route_mode == "telegram":
            for ip in ipv4[:3]:
                targets.append((tr(args, "target_dns", ip=ip), ip))

            if FLOWSEAL_WS_PIN_IP not in ipv4:
                targets.append((tr(args, "target_pinned", ip=FLOWSEAL_WS_PIN_IP), FLOWSEAL_WS_PIN_IP))

        else:
            for ip in ipv4[:3]:
                targets.append((tr(args, "target_cf", ip=ip), ip))

        if not targets:
            print(f"{tr(args, 'target')}: {tr(args, 'none')}")
            print()

        domain_results: list[TargetResult] = []

        for label, connect_host in targets:
            result = await run_target(label, domain, connect_host, args)
            domain_results.append(result)
            all_results.append(result)

            if result.wss.ok and args.stop_on_success:
                break

        print(f"{tr(args, 'recommendation')}: {recommendation_for_results(domain_results, ipv4, args)}")
        print()

        if any(r.wss.ok for r in domain_results) and args.stop_on_success:
            break

    any_ok = any(r.wss.ok for r in all_results)

    print(f"{tr(args, 'summary')}: {tr(args, 'summary_ok') if any_ok else tr(args, 'summary_fail')}")

    if args.gui_markers:
        print("__DIAG_WSS_OK__" if any_ok else "__DIAG_WSS_FAIL__")

    return 0 if any_ok else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Telegram WSS endpoint connectivity")

    parser.add_argument("--route-mode", choices=["telegram", "cloudflare"], default="telegram")
    parser.add_argument("--domain-style", choices=["kws", "names"], default="kws")
    parser.add_argument("--cf-domain", default="")
    parser.add_argument("--pin-telegram-ip", action="store_true")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--dc", type=int, default=2)
    parser.add_argument("--media", action="store_true")
    parser.add_argument("--language", choices=["ru", "en"], default="en")
    parser.add_argument("--stop-on-success", action="store_true")
    parser.add_argument("--gui-markers", action="store_true")
    parser.add_argument("--verbose", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.CRITICAL,
        format="%(levelname)s %(name)s: %(message)s",
    )

    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()