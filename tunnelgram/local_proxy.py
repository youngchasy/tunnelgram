from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import socket
import time
from dataclasses import dataclass, field
from typing import Optional

from . import faketls
from .mtproto import (
    DEFAULT_DC_IPS,
    FLOWSEAL_WS_PIN_IP,
    HANDSHAKE_LEN,
    build_crypto_context,
    generate_relay_init,
    human_bytes,
    parse_dc_ip_overrides,
    parse_proxy_secret,
    try_parse_client_handshake,
    validate_secret_hex,
)
from .telegram_ws import (
    RawTelegramWebSocket,
    TelegramWebSocketError,
    WsEndpoint,
    cloudflare_kws_domains,
    official_kws_domains,
    official_named_domains,
    normalize_ws_dc,
)

log = logging.getLogger("tunnelgram.local")


@dataclass
class LocalConfig:
    listen_host: str = "127.0.0.1"
    listen_port: int = 9443
    secret_hex: str = ""
    fake_tls_domain: str = ""
    accept_plain_dd: bool = True
    fake_tls_timestamp_window: int = 120
    connect_timeout: float = 12.0
    buffer_size: int = 256 * 1024
    direct_fallback: bool = True
    route_mode: str = "telegram"
    cf_domain: str = ""
    pin_telegram_ip: bool = False
    auto_pin_fallback: bool = True
    auto_pin_fallback_timeout: float = 8.0
    domain_style: str = "kws"
    dc_ips: dict[int, str] = field(default_factory=lambda: dict(DEFAULT_DC_IPS))

    @property
    def secret_bytes(self) -> bytes:
        return bytes.fromhex(validate_secret_hex(self.secret_hex))


@dataclass
class Stats:
    total: int = 0
    active: int = 0
    ws: int = 0
    direct: int = 0
    fake_tls: int = 0
    plain_dd: int = 0
    bad: int = 0
    errors: int = 0
    bytes_up: int = 0
    bytes_down: int = 0

    def summary(self) -> str:
        return (
            f"total={self.total} active={self.active} ws={self.ws} direct={self.direct} "
            f"ee={self.fake_tls} dd={self.plain_dd} bad={self.bad} err={self.errors} "
            f"up={human_bytes(self.bytes_up)} down={human_bytes(self.bytes_down)}"
        )


STATS = Stats()


class ClientIO:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, *, fake_tls: bool, pending: bytes = b""):
        self.reader = reader
        self.writer = writer
        self.fake_tls = fake_tls
        self.pending = bytearray(pending)

    async def read(self, max_bytes: int) -> bytes:
        if self.pending:
            n = min(max_bytes, len(self.pending))
            data = bytes(self.pending[:n])
            del self.pending[:n]
            return data
        if not self.fake_tls:
            return await self.reader.read(max_bytes)
        return await faketls.read_tls_appdata(
            self.reader,
            max_payload_len=max(max_bytes, faketls.TLS_MAX_RECORD_PAYLOAD + 256),
        )

    async def write(self, data: bytes) -> None:
        if not self.fake_tls:
            self.writer.write(data)
            await self.writer.drain()
        else:
            await faketls.write_tls_appdata(self.writer, data)

    async def close(self) -> None:
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass


async def _read_inbound_init(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    cfg: LocalConfig,
    label: str,
) -> Optional[tuple[bytes, ClientIO]]:
    first5 = await asyncio.wait_for(reader.readexactly(5), timeout=10)
    maybe_tls = (
        bool(cfg.fake_tls_domain)
        and first5[0] == faketls.TLS_RECORD_HANDSHAKE
        and first5[1:3] in (faketls.TLS_RECORD_VERSION, faketls.TLS_VERSION_12)
        and 0 < int.from_bytes(first5[3:5], "big") <= faketls.TLS_MAX_RECORD_PAYLOAD + 256
    )

    if maybe_tls:
        payload_len = int.from_bytes(first5[3:5], "big")
        payload = await reader.readexactly(payload_len)
        record = first5 + payload
        hello = faketls.parse_faketls_client_hello(
            record,
            cfg.secret_bytes,
            timestamp_window=cfg.fake_tls_timestamp_window,
        )
        if hello is None:
            STATS.bad += 1
            log.warning("[%s] rejected: bad FakeTLS ClientHello or wrong ee-secret", label)
            return None
        expected = cfg.fake_tls_domain.strip().lower()
        got = (hello.hostname or "").strip().lower()
        if got != expected:
            STATS.bad += 1
            log.warning("[%s] rejected: FakeTLS SNI mismatch got=%r expected=%r", label, got, expected)
            return None

        writer.write(faketls.build_faketls_server_hello(cfg.secret_bytes, hello))
        await writer.drain()

        init = bytearray()
        pending = bytearray()
        while len(init) < HANDSHAKE_LEN:
            app = await faketls.read_tls_appdata(reader, max_payload_len=cfg.buffer_size)
            if not app:
                return None
            need = HANDSHAKE_LEN - len(init)
            init.extend(app[:need])
            if len(app) > need:
                pending.extend(app[need:])
        STATS.fake_tls += 1
        log.debug("[%s] accepted inbound FakeTLS ee-secret SNI=%s", label, got)
        return bytes(init), ClientIO(reader, writer, fake_tls=True, pending=bytes(pending))

    if not cfg.accept_plain_dd:
        STATS.bad += 1
        log.warning("[%s] rejected: expected FakeTLS, got non-TLS connection", label)
        return None

    rest = await reader.readexactly(HANDSHAKE_LEN - len(first5))
    STATS.plain_dd += 1
    return first5 + rest, ClientIO(reader, writer, fake_tls=False)


def _set_tcp_opts(writer: asyncio.StreamWriter, buffer_size: int) -> None:
    sock = writer.get_extra_info("socket")
    if sock is None:
        return
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, buffer_size)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, buffer_size)
    except OSError:
        pass


def _ws_domains(cfg: LocalConfig, dc_id: int, is_media: bool) -> list[str]:
    if cfg.route_mode == "cloudflare":
        return cloudflare_kws_domains(dc_id, is_media, cfg.cf_domain)

    kws = official_kws_domains(dc_id, is_media)
    names = official_named_domains(dc_id, is_media)

    if cfg.domain_style == "names":
        preferred = names
        fallback = kws
    else:
        preferred = kws
        fallback = names

    result: list[str] = []

    for domain in preferred + fallback:
        if domain not in result:
            result.append(domain)

    return result


def _connect_candidates_for_domain(cfg: LocalConfig, domain: str) -> list[tuple[str, str, float]]:
    if cfg.route_mode != "telegram":
        return [(domain, "dns", cfg.connect_timeout)]

    if cfg.pin_telegram_ip:
        return [(FLOWSEAL_WS_PIN_IP, "pinned", cfg.connect_timeout)]

    if cfg.auto_pin_fallback:
        dns_timeout = min(cfg.connect_timeout, cfg.auto_pin_fallback_timeout)
        return [
            (domain, "dns", dns_timeout),
            (FLOWSEAL_WS_PIN_IP, "auto-pinned", cfg.connect_timeout),
        ]

    return [(domain, "dns", cfg.connect_timeout)]


async def _connect_telegram_ws(cfg: LocalConfig, dc_id: int, is_media: bool, relay_init: bytes) -> RawTelegramWebSocket:
    last_exc: Exception | None = None

    for domain in _ws_domains(cfg, dc_id, is_media):
        display_dc = normalize_ws_dc(dc_id)

        for connect_host, connect_mode, timeout in _connect_candidates_for_domain(cfg, domain):
            endpoint = WsEndpoint(dc_id=dc_id, domain=domain, connect_host=connect_host)

            try:
                log.debug(
                    "WSS try DC%d%s: %s via %s [%s]",
                    display_dc,
                    " media" if is_media else "",
                    endpoint.url,
                    connect_host,
                    connect_mode,
                )

                ws = await RawTelegramWebSocket.connect(endpoint, timeout=timeout)
                await ws.send(relay_init)

                if connect_mode == "auto-pinned":
                    log.info(
                        "Automatic Telegram IP fallback active for %s: using %s",
                        domain,
                        connect_host,
                    )

                return ws

            except TelegramWebSocketError as exc:
                last_exc = exc

                if exc.is_redirect:
                    log.warning("WSS redirect from %s: %s", domain, exc.location or exc)
                    break

                log.warning(
                    "WSS handshake failed for %s via %s [%s]: %s",
                    domain,
                    connect_host,
                    connect_mode,
                    exc,
                )

                if connect_mode == "dns" and cfg.route_mode == "telegram" and cfg.auto_pin_fallback and not cfg.pin_telegram_ip:
                    log.warning(
                        "DNS WSS path failed for %s; trying pinned Telegram IP %s",
                        domain,
                        FLOWSEAL_WS_PIN_IP,
                    )
                    continue

            except Exception as exc:
                last_exc = exc

                log.warning(
                    "WSS connect failed for %s via %s [%s]: %r",
                    domain,
                    connect_host,
                    connect_mode,
                    exc,
                )

                if connect_mode == "dns" and cfg.route_mode == "telegram" and cfg.auto_pin_fallback and not cfg.pin_telegram_ip:
                    log.warning(
                        "DNS WSS path failed for %s; trying pinned Telegram IP %s",
                        domain,
                        FLOWSEAL_WS_PIN_IP,
                    )
                    continue

    if last_exc:
        raise last_exc

    raise TelegramWebSocketError("No WSS domains available")

def _connect_host_for_domain(cfg: LocalConfig, dc_id: int, domain: str) -> str:
    if cfg.route_mode == "telegram" and cfg.pin_telegram_ip:
        return FLOWSEAL_WS_PIN_IP

    return domain

async def _bridge_ws_reencrypt(
    client: ClientIO,
    ws: RawTelegramWebSocket,
    ctx,
    label: str,
    dc_id: int,
    is_media: bool,
    cfg: LocalConfig,
) -> None:
    started = time.monotonic()
    up = down = 0

    async def client_to_ws() -> None:
        nonlocal up
        while True:
            chunk = await client.read(cfg.buffer_size)
            if not chunk:
                break
            STATS.bytes_up += len(chunk)
            up += len(chunk)
            plain = ctx.client_decryptor.update(chunk)
            outbound = ctx.telegram_encryptor.update(plain)
            await ws.send(outbound)

    async def ws_to_client() -> None:
        nonlocal down
        async for message in ws:
            STATS.bytes_down += len(message)
            down += len(message)
            plain = ctx.telegram_decryptor.update(message)
            inbound = ctx.client_encryptor.update(plain)
            await client.write(inbound)

    tasks = [asyncio.create_task(client_to_ws()), asyncio.create_task(ws_to_client())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except BaseException:
                pass
        try:
            await ws.close()
        except Exception:
            pass
        await client.close()
        duration = time.monotonic() - started
        display_dc = normalize_ws_dc(dc_id)
        log_fn = log.debug if duration < 2.0 and up < 2048 and down < 2048 else log.info
        log_fn(
            "[%s] DC%d%s WSS closed: ^%s v%s in %.1fs",
            label,
            display_dc,
            " media" if is_media else "",
            human_bytes(up),
            human_bytes(down),
            duration,
        )


async def _bridge_tcp_reencrypt(
    client: ClientIO,
    remote_reader: asyncio.StreamReader,
    remote_writer: asyncio.StreamWriter,
    ctx,
    label: str,
    cfg: LocalConfig,
) -> None:
    async def forward_client_to_remote() -> None:
        while True:
            chunk = await client.read(cfg.buffer_size)
            if not chunk:
                break
            STATS.bytes_up += len(chunk)
            plain = ctx.client_decryptor.update(chunk)
            remote_writer.write(ctx.telegram_encryptor.update(plain))
            await remote_writer.drain()

    async def forward_remote_to_client() -> None:
        while True:
            chunk = await remote_reader.read(cfg.buffer_size)
            if not chunk:
                break
            STATS.bytes_down += len(chunk)
            plain = ctx.telegram_decryptor.update(chunk)
            await client.write(ctx.client_encryptor.update(plain))

    tasks = [asyncio.create_task(forward_client_to_remote()), asyncio.create_task(forward_remote_to_client())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except BaseException:
                pass
        await client.close()
        try:
            remote_writer.close()
            await remote_writer.wait_closed()
        except Exception:
            pass
        log.info("[%s] direct TCP fallback closed", label)


async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, cfg: LocalConfig) -> None:
    STATS.total += 1
    STATS.active += 1
    peer = writer.get_extra_info("peername")
    label = f"{peer[0]}:{peer[1]}" if peer else "local"
    _set_tcp_opts(writer, cfg.buffer_size)

    try:
        init_result = await _read_inbound_init(reader, writer, cfg, label)
        if init_result is None:
            return
        handshake, client = init_result

        info = try_parse_client_handshake(handshake, cfg.secret_bytes)
        if info is None:
            STATS.bad += 1
            log.warning("[%s] rejected: bad MTProto handshake or wrong secret", label)
            return

        display_dc = normalize_ws_dc(info.dc_id)
        dc_idx = -info.dc_id if info.is_media else info.dc_id
        relay_init = generate_relay_init(info.proto_tag, dc_idx)
        ctx = build_crypto_context(info.client_prekey_iv, cfg.secret_bytes, relay_init)
        media_tag = " media" if info.is_media else ""

        try:
            ws = await _connect_telegram_ws(cfg, info.dc_id, info.is_media, relay_init)
            STATS.ws += 1
            mode = "ee" if client.fake_tls else "dd"
            log.info("[%s] %s DC%d%s -> Telegram WSS", label, mode, display_dc, media_tag)
            await _bridge_ws_reencrypt(client, ws, ctx, label, info.dc_id, info.is_media, cfg)
            return
        except Exception as exc:
            STATS.errors += 1
            log.warning("[%s] WSS path failed for DC%d%s: %r", label, display_dc, media_tag, exc)
            if not cfg.direct_fallback:
                return

        target_ip = cfg.dc_ips.get(info.dc_id) or cfg.dc_ips.get(display_dc) or cfg.dc_ips.get(2)
        if not target_ip:
            log.warning("[%s] no direct fallback IP for DC%d", label, display_dc)
            return

        remote_reader, remote_writer = await asyncio.wait_for(
            asyncio.open_connection(target_ip, 443), timeout=cfg.connect_timeout
        )
        _set_tcp_opts(remote_writer, cfg.buffer_size)
        remote_writer.write(relay_init)
        await remote_writer.drain()
        STATS.direct += 1
        log.info("[%s] DC%d%s -> direct TCP fallback %s:443", label, display_dc, media_tag, target_ip)
        await _bridge_tcp_reencrypt(client, remote_reader, remote_writer, ctx, label, cfg)

    except asyncio.IncompleteReadError:
        log.debug("[%s] disconnected during init", label)
    except asyncio.TimeoutError:
        STATS.errors += 1
        log.warning("[%s] timeout", label)
    except Exception as exc:
        STATS.errors += 1
        log.exception("[%s] unexpected error: %r", label, exc)
    finally:
        STATS.active -= 1
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def run_proxy(cfg: LocalConfig, stop_event: Optional[asyncio.Event] = None) -> None:
    validate_secret_hex(cfg.secret_hex)
    if cfg.route_mode not in {"telegram", "cloudflare"}:
        raise ValueError("route_mode must be telegram or cloudflare")
    if cfg.route_mode == "cloudflare" and not cfg.cf_domain:
        raise ValueError("cf_domain is required in cloudflare route mode")

    server = await asyncio.start_server(
        lambda r, w: _handle_client(r, w, cfg), cfg.listen_host, cfg.listen_port
    )
    for sock in server.sockets or []:
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass

    log.info("TunnelGram Direct local proxy listening on %s:%d", cfg.listen_host, cfg.listen_port)
    if cfg.route_mode == "cloudflare":
        log.info("Route: Cloudflare DNS proxy domain suffix %s", cfg.cf_domain)
    else:
        log.info(
            "Route: official Telegram WSS domains (%s); pin_ip=%s auto_pin_fallback=%s",
            cfg.domain_style,
            cfg.pin_telegram_ip,
            cfg.auto_pin_fallback,
        )

        if cfg.pin_telegram_ip:
            log.info("Pinned WSS connect_host: %s", FLOWSEAL_WS_PIN_IP)
        elif cfg.auto_pin_fallback:
            log.info("Automatic pinned WSS fallback IP: %s", FLOWSEAL_WS_PIN_IP)
    log.info("Supports dd secret: dd%s", cfg.secret_hex)
    if cfg.fake_tls_domain:
        log.info("Supports ee FakeTLS secret with SNI: %s", cfg.fake_tls_domain)

    async def stats_loop() -> None:
        while True:
            await asyncio.sleep(30)
            log.info("stats: %s", STATS.summary())

    stats_task = asyncio.create_task(stats_loop())
    try:
        async with server:
            if stop_event:
                serve_task = asyncio.create_task(server.serve_forever())
                stop_task = asyncio.create_task(stop_event.wait())
                done, pending = await asyncio.wait({serve_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                if stop_task in done:
                    server.close()
                    await server.wait_closed()
            else:
                await server.serve_forever()
    finally:
        stats_task.cancel()
        try:
            await stats_task
        except BaseException:
            pass


def _build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Local Telegram MTProto proxy over Telegram official WebSocket endpoints")
    ap.add_argument("--listen-host", default="127.0.0.1")
    ap.add_argument("--listen-port", type=int, default=9443)
    ap.add_argument("--secret", required=True, help="32 hex chars, dd+key, or ee+key+domain_hex")
    ap.add_argument("--fake-tls-domain", default="", help="SNI domain for ee FakeTLS links, e.g. www.cloudflare.com")
    ap.add_argument("--fake-tls-only", action="store_true", help="Reject plain dd connections; accept only ee FakeTLS")
    ap.add_argument("--route-mode", choices=["telegram", "cloudflare"], default="telegram")
    ap.add_argument("--cf-domain", default="", help="Domain suffix for Cloudflare DNS proxy mode, e.g. example.com")
    ap.add_argument("--pin-telegram-ip", action="store_true", help="Connect to Flowseal-style pinned Telegram web IP while keeping WSS SNI/Host")
    ap.add_argument("--no-pin-telegram-ip", action="store_true", help="Deprecated; normal DNS is the default")
    ap.add_argument(
        "--no-auto-pin-fallback",
        action="store_true",
        help="Do not automatically fallback to pinned Telegram web IP when normal DNS WSS path fails",
    )
    ap.add_argument("--domain-style", choices=["kws", "names"], default="kws", help="Use kwsN or official pluto/venus names")
    ap.add_argument("--no-direct-fallback", action="store_true", help="Do not fallback to direct Telegram TCP if WSS fails")
    ap.add_argument("--dc-ip", action="append", default=[], metavar="DC:IP", help="Override Telegram DC IP")
    ap.add_argument("--verbose", action="store_true")
    return ap


def main() -> None:
    args = _build_arg_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )
    secret = parse_proxy_secret(args.secret)
    fake_tls_domain = args.fake_tls_domain.strip().lower() or (secret.fake_tls_domain or "")
    cfg = LocalConfig(
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        secret_hex=secret.key_hex,
        fake_tls_domain=fake_tls_domain,
        accept_plain_dd=not args.fake_tls_only,
        route_mode=args.route_mode,
        cf_domain=args.cf_domain.strip().lower(),
        pin_telegram_ip=bool(args.pin_telegram_ip) and not bool(args.no_pin_telegram_ip),
        auto_pin_fallback=not args.no_auto_pin_fallback,
        domain_style=args.domain_style,
        direct_fallback=not args.no_direct_fallback,
        dc_ips=parse_dc_ip_overrides(args.dc_ip),
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    stop = asyncio.Event()

    def _stop(*_):
        stop.set()

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _stop)
            except (NotImplementedError, RuntimeError):
                pass
        loop.run_until_complete(run_proxy(cfg, stop))
    finally:
        loop.close()


if __name__ == "__main__":
    main()
