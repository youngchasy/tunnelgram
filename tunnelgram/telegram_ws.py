from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import socket
import ssl
from dataclasses import dataclass
from typing import Optional

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_HTTP_HEADER = 64 * 1024

def connection_family_for_host(host: str) -> int:
    mode = os.environ.get("TUNNELGRAM_IP_FAMILY", "ipv4").strip().lower()

    if mode == "auto":
        return socket.AF_UNSPEC

    if mode == "ipv6":
        return socket.AF_INET6

    return socket.AF_INET

class TelegramWebSocketError(Exception):

    def __init__(self, message: str, *, status_code: Optional[int] = None, location: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.location = location

    @property
    def is_redirect(self) -> bool:
        return self.status_code in {301, 302, 303, 307, 308}


@dataclass(frozen=True)
class WsEndpoint:
    dc_id: int
    domain: str
    connect_host: str
    port: int = 443
    path: str = "/apiws"

    @property
    def url(self) -> str:
        return f"wss://{self.domain}{self.path}"


DC_NAME_DOMAINS = {
    1: "pluto",
    2: "venus",
    3: "aurora",
    4: "vesta",
    5: "flora",
}


def normalize_ws_dc(dc_id: int) -> int:
    return 2 if int(dc_id) == 203 else int(dc_id)


def official_kws_domains(dc_id: int, is_media: bool) -> list[str]:
    dc = normalize_ws_dc(dc_id)
    primary = f"kws{dc}.web.telegram.org"
    alt = f"kws{dc}-1.web.telegram.org"
    return [alt, primary] if is_media else [primary, alt]


def official_named_domains(dc_id: int, is_media: bool) -> list[str]:
    dc = normalize_ws_dc(dc_id)
    name = DC_NAME_DOMAINS.get(dc, f"kws{dc}")
    primary = f"{name}.web.telegram.org"
    alt = f"{name}-1.web.telegram.org"
    return [alt, primary] if is_media else [primary, alt]


def cloudflare_kws_domains(dc_id: int, is_media: bool, suffix: str) -> list[str]:
    suffix = suffix.strip().lower().lstrip(".")
    if not suffix or "." not in suffix:
        raise ValueError("Cloudflare domain suffix must look like example.com")
    dc = normalize_ws_dc(dc_id)
    primary = f"kws{dc}.{suffix}"
    alt = f"kws{dc}-1.{suffix}"
    return [alt, primary] if is_media else [primary, alt]


class RawTelegramWebSocket:

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, endpoint: WsEndpoint):
        self.reader = reader
        self.writer = writer
        self.endpoint = endpoint
        self._closed = False
        self._continuation = bytearray()

    @classmethod
    async def connect(cls, endpoint: WsEndpoint, *, timeout: float = 12.0) -> "RawTelegramWebSocket":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                endpoint.connect_host,
                endpoint.port,
                ssl=ctx,
                server_hostname=endpoint.domain,
                family=connection_family_for_host(endpoint.connect_host),
            ),
            timeout=timeout,
        )

        sock = writer.get_extra_info("socket")
        if sock is not None:
            try:
                import socket

                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {endpoint.path} HTTP/1.1\r\n"
            f"Host: {endpoint.domain}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "Sec-WebSocket-Protocol: binary\r\n"
            "\r\n"
        ).encode("ascii")
        writer.write(request)
        await writer.drain()

        response = await cls._read_http_response(reader)
        status_line, headers = cls._parse_http_response(response)
        parts = status_line.split()
        status_code = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
        if status_code != 101:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            raise TelegramWebSocketError(
                f"WebSocket handshake failed: {status_line}",
                status_code=status_code,
                location=headers.get("location", ""),
            )

        expected_accept = base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")
        actual_accept = headers.get("sec-websocket-accept", "")
        if actual_accept != expected_accept:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            raise TelegramWebSocketError("WebSocket handshake failed: bad Sec-WebSocket-Accept")

        subprotocol = headers.get("sec-websocket-protocol", "").lower()
        if subprotocol and subprotocol != "binary":
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            raise TelegramWebSocketError(f"Unexpected WebSocket subprotocol: {subprotocol!r}")

        return cls(reader, writer, endpoint)

    @staticmethod
    async def _read_http_response(reader: asyncio.StreamReader) -> bytes:
        data = bytearray()
        while b"\r\n\r\n" not in data:
            chunk = await reader.read(1024)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_HTTP_HEADER:
                raise TelegramWebSocketError("WebSocket handshake response too large")
        if b"\r\n\r\n" not in data:
            raise TelegramWebSocketError("Incomplete WebSocket handshake response")
        return bytes(data.split(b"\r\n\r\n", 1)[0])

    @staticmethod
    def _parse_http_response(data: bytes) -> tuple[str, dict[str, str]]:
        text = data.decode("iso-8859-1", errors="replace")
        lines = text.split("\r\n")
        status_line = lines[0] if lines else ""
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
        return status_line, headers

    async def send(self, data: bytes) -> None:
        if self._closed:
            raise TelegramWebSocketError("WebSocket is closed")
        await self._send_frame(data, opcode=0x2)

    async def recv(self) -> bytes:
        while True:
            fin, opcode, payload = await self._read_frame()
            if opcode == 0x8:  # close
                self._closed = True
                try:
                    await self._send_frame(payload[:2] or b"", opcode=0x8)
                except Exception:
                    pass
                raise EOFError("WebSocket closed")
            if opcode == 0x9:
                await self._send_frame(payload, opcode=0xA)
                continue
            if opcode == 0xA:
                continue
            if opcode in (0x1, 0x2):
                if fin:
                    return payload
                self._continuation = bytearray(payload)
                continue
            if opcode == 0x0:
                self._continuation.extend(payload)
                if fin:
                    out = bytes(self._continuation)
                    self._continuation.clear()
                    return out

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        try:
            return await self.recv()
        except EOFError:
            raise StopAsyncIteration

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._send_frame(b"", opcode=0x8)
        except Exception:
            pass
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass

    async def _send_frame(self, payload: bytes, *, opcode: int) -> None:
        payload = bytes(payload)
        header = bytearray()
        header.append(0x80 | (opcode & 0x0F))
        mask_bit = 0x80
        n = len(payload)
        if n < 126:
            header.append(mask_bit | n)
        elif n < (1 << 16):
            header.append(mask_bit | 126)
            header.extend(n.to_bytes(2, "big"))
        else:
            header.append(mask_bit | 127)
            header.extend(n.to_bytes(8, "big"))
        mask = os.urandom(4)
        masked = bytes(payload[i] ^ mask[i % 4] for i in range(n))
        self.writer.write(bytes(header) + mask + masked)
        await self.writer.drain()

    async def _read_frame(self) -> tuple[bool, int, bytes]:
        head = await self.reader.readexactly(2)
        b1, b2 = head[0], head[1]
        fin = bool(b1 & 0x80)
        opcode = b1 & 0x0F
        masked = bool(b2 & 0x80)
        n = b2 & 0x7F
        if n == 126:
            n = int.from_bytes(await self.reader.readexactly(2), "big")
        elif n == 127:
            n = int.from_bytes(await self.reader.readexactly(8), "big")
        mask = await self.reader.readexactly(4) if masked else b""
        payload = await self.reader.readexactly(n) if n else b""
        if masked:
            payload = bytes(payload[i] ^ mask[i % 4] for i in range(n))
        return fin, opcode, payload
