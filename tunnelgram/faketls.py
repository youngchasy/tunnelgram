from __future__ import annotations

import asyncio
import hmac
import os
import struct
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Optional

TLS_RECORD_HANDSHAKE = 0x16
TLS_RECORD_CHANGE_CIPHER_SPEC = 0x14
TLS_RECORD_APPLICATION_DATA = 0x17
TLS_RECORD_ALERT = 0x15
TLS_VERSION_12 = b"\x03\x03"
TLS_RECORD_VERSION = b"\x03\x01"
TLS_MAX_RECORD_PAYLOAD = 16_384
TLS_DIGEST_POS = 11
TLS_DIGEST_LEN = 32
TLS_HANDSHAKE_CLIENT_HELLO = 0x01
TLS_HANDSHAKE_SERVER_HELLO = 0x02
TLS_CLIENT_RANDOM_OFFSET_IN_HANDSHAKE = 6
TLS_SERVER_RANDOM_OFFSET_IN_PACKET = 11
TLS_CHANGE_CIPHER_SPEC_VALUE = 0x01

_FLOWSEAL_CCS_FRAME = b"\x14\x03\x03\x00\x01\x01"
_FLOWSEAL_SERVER_HELLO_TEMPLATE = bytearray(
    b"\x16\x03\x03\x00\x7a"
    b"\x02\x00\x00\x76"
    b"\x03\x03" + b"\x00" * 32 + b"\x20" + b"\x00" * 32 + b"\x13\x01\x00"
    + b"\x00\x2e"
    + b"\x00\x33\x00\x24\x00\x1d\x00\x20" + b"\x00" * 32
    + b"\x00\x2b\x00\x02\x03\x04"
)
_FLOWSEAL_SH_RANDOM_OFF = 11
_FLOWSEAL_SH_SESSID_OFF = 44
_FLOWSEAL_SH_PUBKEY_OFF = 89


@dataclass(frozen=True)
class FakeTlsClientHello:
    random: bytes
    session_id: bytes
    cipher_suite: bytes
    hostname: Optional[str]
    timestamp: Optional[int] = None


class FakeTlsError(Exception):
    pass


def hostname_to_hex(hostname: str) -> str:
    host = hostname.strip().lower()
    if not host:
        raise ValueError("Fake TLS domain is empty")
    try:
        host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("Fake TLS domain must be a valid domain name") from exc
    ascii_host = host.encode("idna").decode("ascii")
    if len(ascii_host) > 253 or "." not in ascii_host:
        raise ValueError("Fake TLS domain should look like example.com")
    return ascii_host.encode("ascii").hex()


def decode_hostname_hex(domain_hex: str) -> str:
    if len(domain_hex) % 2 != 0:
        raise ValueError("Fake TLS domain hex has odd length")
    try:
        raw = bytes.fromhex(domain_hex)
        return raw.decode("ascii").strip().lower()
    except Exception as exc:
        raise ValueError("Fake TLS domain hex is invalid") from exc


def build_faketls_secret_hex(secret_hex: str, hostname: str) -> str:
    from .mtproto import validate_secret_hex

    return "ee" + validate_secret_hex(secret_hex) + hostname_to_hex(hostname)


def _push_tls_record(out: bytearray, record_type: int, payload: bytes) -> None:
    out.append(record_type)
    out.extend(TLS_VERSION_12)
    out.extend(len(payload).to_bytes(2, "big"))
    out.extend(payload)


def _parse_sni_extension(extensions: bytes) -> Optional[str]:
    p = 0
    while p + 4 <= len(extensions):
        ext_type = int.from_bytes(extensions[p : p + 2], "big")
        ext_len = int.from_bytes(extensions[p + 2 : p + 4], "big")
        p += 4
        if p + ext_len > len(extensions):
            return None
        ext = extensions[p : p + ext_len]
        p += ext_len
        if ext_type != 0x0000:
            continue
        if len(ext) < 5:
            return None
        list_len = int.from_bytes(ext[0:2], "big")
        if len(ext) < 2 + list_len or list_len < 3 or ext[2] != 0:
            return None
        host_len = int.from_bytes(ext[3:5], "big")
        if len(ext) < 5 + host_len:
            return None
        try:
            return ext[5 : 5 + host_len].decode("ascii").lower()
        except UnicodeDecodeError:
            return None
    return None


def parse_faketls_client_hello(record: bytes, secret: bytes, *, timestamp_window: Optional[int] = 300) -> Optional[FakeTlsClientHello]:
    if len(record) < 5 + 4 + TLS_CLIENT_RANDOM_OFFSET_IN_HANDSHAKE + TLS_DIGEST_LEN:
        return None
    if record[0] != TLS_RECORD_HANDSHAKE:
        return None
    record_len = int.from_bytes(record[3:5], "big")
    if len(record) != 5 + record_len:
        return None

    handshake = record[5:]
    if len(handshake) < 4 or handshake[0] != TLS_HANDSHAKE_CLIENT_HELLO:
        return None
    handshake_len = (handshake[1] << 16) | (handshake[2] << 8) | handshake[3]
    if len(handshake) != 4 + handshake_len:
        return None

    random_offset = 5 + TLS_CLIENT_RANDOM_OFFSET_IN_HANDSHAKE
    client_random = record[random_offset : random_offset + TLS_DIGEST_LEN]
    signed = bytearray(record)
    signed[random_offset : random_offset + TLS_DIGEST_LEN] = b"\x00" * TLS_DIGEST_LEN
    computed = hmac.new(secret, bytes(signed), sha256).digest()
    xored = bytes(a ^ b for a, b in zip(computed, client_random))
    if any(xored[:28]):
        return None

    timestamp = int.from_bytes(xored[28:32], "little")
    if timestamp_window is not None:
        now = int(time.time())
        if abs(now - timestamp) > int(timestamp_window):
            return None

    body = handshake[4:]
    if len(body) < 2 + 32 + 1:
        return None
    session_id_len = body[34]
    session_start = 35
    session_end = session_start + session_id_len
    if len(body) < session_end + 2:
        return None
    session_id = body[session_start:session_end]
    cipher_suites_len = int.from_bytes(body[session_end : session_end + 2], "big")
    if cipher_suites_len < 2 or len(body) < session_end + 2 + cipher_suites_len + 1:
        return None
    cipher_suite = body[session_end + 2 : session_end + 4]
    p = session_end + 2 + cipher_suites_len
    compression_len = body[p]
    p += 1 + compression_len
    if len(body) < p + 2:
        return None
    extensions_len = int.from_bytes(body[p : p + 2], "big")
    p += 2
    if len(body) < p + extensions_len:
        return None
    hostname = _parse_sni_extension(body[p : p + extensions_len])

    return FakeTlsClientHello(
        random=client_random,
        session_id=session_id,
        cipher_suite=cipher_suite,
        hostname=hostname,
        timestamp=timestamp,
    )


def build_faketls_server_hello(secret: bytes, hello: FakeTlsClientHello) -> bytes:
    sh = bytearray(_FLOWSEAL_SERVER_HELLO_TEMPLATE)
    session = (hello.session_id or b"\x00" * 32)[:32].ljust(32, b"\x00")
    sh[_FLOWSEAL_SH_SESSID_OFF : _FLOWSEAL_SH_SESSID_OFF + 32] = session
    sh[_FLOWSEAL_SH_PUBKEY_OFF : _FLOWSEAL_SH_PUBKEY_OFF + 32] = os.urandom(32)

    encrypted_size = 1900 + (int.from_bytes(os.urandom(2), "big") % 201)
    app_record = b"\x17\x03\x03" + struct.pack(">H", encrypted_size) + os.urandom(encrypted_size)
    response = bytes(sh) + _FLOWSEAL_CCS_FRAME + app_record

    server_random = hmac.new(secret, hello.random + response, sha256).digest()
    final = bytearray(response)
    final[_FLOWSEAL_SH_RANDOM_OFF : _FLOWSEAL_SH_RANDOM_OFF + 32] = server_random
    return bytes(final)

def build_faketls_client_hello(hostname: str) -> bytes:
    host_b = hostname.strip().lower().encode("idna")
    exts = bytearray()
    sni_entry_len = 1 + 2 + len(host_b)
    sni_data_len = 2 + sni_entry_len
    exts.extend((0x0000).to_bytes(2, "big"))
    exts.extend(sni_data_len.to_bytes(2, "big"))
    exts.extend(sni_entry_len.to_bytes(2, "big"))
    exts.append(0x00)
    exts.extend(len(host_b).to_bytes(2, "big"))
    exts.extend(host_b)
    exts.extend(bytes.fromhex("00170000"))
    exts.extend(bytes.fromhex("ff01000100"))
    exts.extend(bytes.fromhex("000a000a0008001d001700180019"))
    exts.extend(bytes.fromhex("000b00020100"))
    exts.extend(bytes.fromhex("00230000"))
    exts.extend(bytes.fromhex("000d00140012040308040401050308050501080606010201"))

    cipher_suites = bytes.fromhex(
        "130113021303c02bc02fc02cc030cca9cca8c013c014009c009d002f0035000a"
    )
    hello = bytearray()
    hello.extend(TLS_VERSION_12)
    hello.extend(b"\x00" * TLS_DIGEST_LEN)
    hello.append(0x20)
    hello.extend(os.urandom(32))
    hello.extend(len(cipher_suites).to_bytes(2, "big"))
    hello.extend(cipher_suites)
    hello.extend(b"\x01\x00")
    hello.extend(len(exts).to_bytes(2, "big"))
    hello.extend(exts)

    handshake = bytearray()
    handshake.append(TLS_HANDSHAKE_CLIENT_HELLO)
    handshake.extend(len(hello).to_bytes(3, "big"))
    handshake.extend(hello)

    record = bytearray()
    record.append(TLS_RECORD_HANDSHAKE)
    record.extend(TLS_RECORD_VERSION)
    record.extend(len(handshake).to_bytes(2, "big"))
    record.extend(handshake)
    return bytes(record)


def sign_faketls_client_hello(record: bytes | bytearray, secret: bytes) -> bytes:
    rec = bytearray(record)
    rec[TLS_DIGEST_POS : TLS_DIGEST_POS + TLS_DIGEST_LEN] = b"\x00" * TLS_DIGEST_LEN
    digest = hmac.new(secret, bytes(rec), sha256).digest()
    ts = int(time.time()).to_bytes(4, "little")
    rec[TLS_DIGEST_POS : TLS_DIGEST_POS + 28] = digest[:28]
    rec[TLS_DIGEST_POS + 28 : TLS_DIGEST_POS + 32] = bytes(digest[28 + i] ^ ts[i] for i in range(4))
    return bytes(rec)


async def read_tls_record(reader: asyncio.StreamReader, *, max_payload_len: int = TLS_MAX_RECORD_PAYLOAD + 256) -> Optional[tuple[int, bytes, bytes]]:
    header = await reader.readexactly(5)
    payload_len = int.from_bytes(header[3:5], "big")
    if payload_len > max_payload_len:
        return None
    payload = await reader.readexactly(payload_len)
    return header[0], header[1:3], payload


async def read_tls_appdata(reader: asyncio.StreamReader, *, max_payload_len: int = TLS_MAX_RECORD_PAYLOAD + 256) -> bytes:
    while True:
        rec = await read_tls_record(reader, max_payload_len=max_payload_len)
        if rec is None:
            return b""
        record_type, version, payload = rec
        if version not in (TLS_VERSION_12, TLS_RECORD_VERSION):
            return b""
        if record_type == TLS_RECORD_APPLICATION_DATA:
            return payload
        if record_type == TLS_RECORD_CHANGE_CIPHER_SPEC:
            continue
        return b""


async def write_tls_appdata(writer: asyncio.StreamWriter, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        chunk = data[offset : offset + TLS_MAX_RECORD_PAYLOAD]
        header = bytes([TLS_RECORD_APPLICATION_DATA]) + TLS_VERSION_12 + len(chunk).to_bytes(2, "big")
        writer.write(header + chunk)
        await writer.drain()
        offset += len(chunk)
