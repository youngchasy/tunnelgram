from __future__ import annotations

import hashlib
import os
import struct
from dataclasses import dataclass
from typing import Optional, Tuple

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

ZERO_64 = b"\x00" * 64
HANDSHAKE_LEN = 64
SKIP_LEN = 8
PREKEY_LEN = 32
KEY_LEN = 32
IV_LEN = 16
PROTO_TAG_POS = 56
DC_IDX_POS = 60

PROTO_TAG_ABRIDGED = b"\xef\xef\xef\xef"
PROTO_TAG_INTERMEDIATE = b"\xee\xee\xee\xee"
PROTO_TAG_PADDED_INTERMEDIATE = b"\xdd\xdd\xdd\xdd"

PROTO_ABRIDGED_INT = 0xEFEFEFEF
PROTO_INTERMEDIATE_INT = 0xEEEEEEEE
PROTO_PADDED_INTERMEDIATE_INT = 0xDDDDDDDD

RESERVED_FIRST_BYTES = {0xEF}
RESERVED_STARTS = {
    b"HEAD",
    b"POST",
    b"GET ",
    b"\xee\xee\xee\xee",
    b"\xdd\xdd\xdd\xdd",
    b"\x16\x03\x01\x02",
}
RESERVED_CONTINUE = b"\x00\x00\x00\x00"

DEFAULT_DC_IPS = {
    1: "149.154.175.50",
    2: "149.154.167.50",
    3: "149.154.175.100",
    4: "149.154.167.91",
    5: "91.108.56.130",
    203: "149.154.167.50",
}

FLOWSEAL_WS_PIN_IP = "149.154.167.220"


@dataclass(frozen=True)
class HandshakeInfo:
    dc_id: int
    is_media: bool
    proto_tag: bytes
    client_prekey_iv: bytes


@dataclass(frozen=True)
class ProxySecret:
    mode: str
    key_hex: str
    fake_tls_domain: Optional[str] = None


@dataclass
class CryptoContext:
    client_decryptor: object
    client_encryptor: object
    telegram_encryptor: object
    telegram_decryptor: object


def generate_secret_hex() -> str:
    return os.urandom(16).hex()


def validate_secret_hex(secret_hex: str) -> str:
    secret_hex = secret_hex.strip().lower()
    if secret_hex.startswith("dd") and len(secret_hex) == 34:
        secret_hex = secret_hex[2:]
    if len(secret_hex) != 32:
        raise ValueError("MTProto secret must be exactly 32 hex characters, without the 'dd' prefix.")
    try:
        bytes.fromhex(secret_hex)
    except ValueError as exc:
        raise ValueError("MTProto secret contains non-hex characters.") from exc
    return secret_hex


def parse_proxy_secret(secret: str) -> ProxySecret:
    raw = secret.strip().lower()
    if raw.startswith("ee"):
        if len(raw) < 34 or len(raw) % 2 != 0:
            raise ValueError("Fake TLS secret must be ee + 32 hex chars + hex-encoded domain.")
        key_hex = validate_secret_hex(raw[2:34])
        domain_hex = raw[34:]
        if not domain_hex:
            raise ValueError("Fake TLS ee-secret must include a hex-encoded SNI domain after the key.")
        try:
            domain = bytes.fromhex(domain_hex).decode("ascii").strip().lower()
        except Exception as exc:
            raise ValueError("Fake TLS ee-secret domain part is not valid ASCII hex.") from exc
        return ProxySecret(mode="ee", key_hex=key_hex, fake_tls_domain=domain)
    if raw.startswith("dd") and len(raw) == 34:
        return ProxySecret(mode="dd", key_hex=validate_secret_hex(raw), fake_tls_domain=None)
    return ProxySecret(mode="dd", key_hex=validate_secret_hex(raw), fake_tls_domain=None)


def telegram_link(host: str, port: int, secret_hex: str, *, mode: str = "dd", fake_tls_domain: str | None = None) -> str:
    secret_hex = validate_secret_hex(secret_hex)
    if mode == "ee":
        if not fake_tls_domain:
            raise ValueError("Fake TLS mode requires a domain, for example www.cloudflare.com")
        from .faketls import hostname_to_hex

        secret = "ee" + secret_hex + hostname_to_hex(fake_tls_domain)
    else:
        secret = "dd" + secret_hex
    return f"tg://proxy?server={host}&port={int(port)}&secret={secret}"


def _aes_ctr(key: bytes, iv: bytes):
    return Cipher(algorithms.AES(key), modes.CTR(iv)).encryptor()


def try_parse_client_handshake(handshake: bytes, secret: bytes) -> Optional[HandshakeInfo]:
    if len(handshake) != HANDSHAKE_LEN:
        return None

    prekey_iv = handshake[SKIP_LEN : SKIP_LEN + PREKEY_LEN + IV_LEN]
    prekey = prekey_iv[:PREKEY_LEN]
    iv = prekey_iv[PREKEY_LEN:]
    key = hashlib.sha256(prekey + secret).digest()

    decrypted = _aes_ctr(key, iv).update(handshake)
    proto_tag = decrypted[PROTO_TAG_POS : PROTO_TAG_POS + 4]
    if proto_tag not in (PROTO_TAG_ABRIDGED, PROTO_TAG_INTERMEDIATE, PROTO_TAG_PADDED_INTERMEDIATE):
        return None

    dc_idx = int.from_bytes(decrypted[DC_IDX_POS : DC_IDX_POS + 2], "little", signed=True)
    if dc_idx == 0:
        return None

    return HandshakeInfo(
        dc_id=abs(dc_idx),
        is_media=dc_idx < 0,
        proto_tag=proto_tag,
        client_prekey_iv=prekey_iv,
    )


def generate_relay_init(proto_tag: bytes, dc_idx: int) -> bytes:
    if proto_tag not in (PROTO_TAG_ABRIDGED, PROTO_TAG_INTERMEDIATE, PROTO_TAG_PADDED_INTERMEDIATE):
        raise ValueError("Unsupported MTProto transport tag")

    while True:
        rnd = bytearray(os.urandom(HANDSHAKE_LEN))
        if rnd[0] in RESERVED_FIRST_BYTES:
            continue
        if bytes(rnd[:4]) in RESERVED_STARTS:
            continue
        if bytes(rnd[4:8]) == RESERVED_CONTINUE:
            continue
        break

    rnd[PROTO_TAG_POS : PROTO_TAG_POS + 4] = proto_tag
    rnd[DC_IDX_POS : DC_IDX_POS + 2] = struct.pack("<h", int(dc_idx))

    raw = bytes(rnd)
    key = raw[SKIP_LEN : SKIP_LEN + PREKEY_LEN]
    iv = raw[SKIP_LEN + PREKEY_LEN : SKIP_LEN + PREKEY_LEN + IV_LEN]
    encrypted_stream = _aes_ctr(key, iv).update(raw)
    return raw[:PROTO_TAG_POS] + encrypted_stream[PROTO_TAG_POS:]


def build_crypto_context(client_prekey_iv: bytes, secret: bytes, relay_init: bytes) -> CryptoContext:
    if len(client_prekey_iv) != PREKEY_LEN + IV_LEN:
        raise ValueError("client_prekey_iv must be 48 bytes")
    if len(relay_init) != HANDSHAKE_LEN:
        raise ValueError("relay_init must be 64 bytes")

    client_dec_prekey = client_prekey_iv[:PREKEY_LEN]
    client_dec_iv = client_prekey_iv[PREKEY_LEN:]
    client_dec_key = hashlib.sha256(client_dec_prekey + secret).digest()
    client_decryptor = _aes_ctr(client_dec_key, client_dec_iv)
    client_decryptor.update(ZERO_64)

    client_enc_prekey_iv = client_prekey_iv[::-1]
    client_enc_key = hashlib.sha256(client_enc_prekey_iv[:PREKEY_LEN] + secret).digest()
    client_enc_iv = client_enc_prekey_iv[PREKEY_LEN:]
    client_encryptor = _aes_ctr(client_enc_key, client_enc_iv)

    telegram_enc_key = relay_init[SKIP_LEN : SKIP_LEN + PREKEY_LEN]
    telegram_enc_iv = relay_init[SKIP_LEN + PREKEY_LEN : SKIP_LEN + PREKEY_LEN + IV_LEN]
    telegram_encryptor = _aes_ctr(telegram_enc_key, telegram_enc_iv)
    telegram_encryptor.update(ZERO_64)

    telegram_dec_prekey_iv = relay_init[SKIP_LEN : SKIP_LEN + PREKEY_LEN + IV_LEN][::-1]
    telegram_dec_key = telegram_dec_prekey_iv[:KEY_LEN]
    telegram_dec_iv = telegram_dec_prekey_iv[KEY_LEN:]
    telegram_decryptor = _aes_ctr(telegram_dec_key, telegram_dec_iv)

    return CryptoContext(
        client_decryptor=client_decryptor,
        client_encryptor=client_encryptor,
        telegram_encryptor=telegram_encryptor,
        telegram_decryptor=telegram_decryptor,
    )


def parse_dc_ip_overrides(items: list[str] | None) -> dict[int, str]:
    ips = dict(DEFAULT_DC_IPS)
    if not items:
        return ips
    import ipaddress

    for item in items:
        if ":" not in item:
            raise ValueError(f"Invalid DC mapping {item!r}; expected DC:IP")
        dc_raw, ip_raw = item.split(":", 1)
        dc = int(dc_raw)
        ipaddress.ip_address(ip_raw)
        ips[dc] = ip_raw
    return ips


def human_bytes(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(value) < 1024:
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}TB"
