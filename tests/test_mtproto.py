import hashlib
import os
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from tunnelgram.mtproto import (
    PROTO_TAG_ABRIDGED,
    RESERVED_CONTINUE,
    RESERVED_FIRST_BYTES,
    RESERVED_STARTS,
    generate_relay_init,
    try_parse_client_handshake,
)


def make_client_handshake(secret: bytes, dc_idx: int = 2) -> bytes:
    while True:
        rnd = bytearray(os.urandom(64))
        if rnd[0] not in RESERVED_FIRST_BYTES and bytes(rnd[:4]) not in RESERVED_STARTS and bytes(rnd[4:8]) != RESERVED_CONTINUE:
            break
    rnd[56:60] = PROTO_TAG_ABRIDGED
    rnd[60:62] = struct.pack("<h", dc_idx)
    raw = bytes(rnd)
    key = hashlib.sha256(raw[8:40] + secret).digest()
    iv = raw[40:56]
    enc = Cipher(algorithms.AES(key), modes.CTR(iv)).encryptor().update(raw)
    return raw[:56] + enc[56:]


def test_parse_client_handshake():
    secret = bytes.fromhex("00112233445566778899aabbccddeeff")
    hs = make_client_handshake(secret, dc_idx=-4)
    info = try_parse_client_handshake(hs, secret)
    assert info is not None
    assert info.dc_id == 4
    assert info.is_media is True


def test_generate_relay_init_len():
    init = generate_relay_init(PROTO_TAG_ABRIDGED, 2)
    assert len(init) == 64

from tunnelgram.faketls import (
    build_faketls_client_hello,
    build_faketls_secret_hex,
    parse_faketls_client_hello,
    sign_faketls_client_hello,
)
from tunnelgram.mtproto import parse_proxy_secret, telegram_link


def test_parse_ee_secret_and_link():
    base = "00112233445566778899aabbccddeeff"
    link = telegram_link("127.0.0.1", 1443, base, mode="ee", fake_tls_domain="www.cloudflare.com")
    assert "secret=ee" in link
    secret = link.split("secret=", 1)[1]
    parsed = parse_proxy_secret(secret)
    assert parsed.mode == "ee"
    assert parsed.key_hex == base
    assert parsed.fake_tls_domain == "www.cloudflare.com"


def test_faketls_client_hello_roundtrip():
    secret = bytes.fromhex("00112233445566778899aabbccddeeff")
    hello = build_faketls_client_hello("www.cloudflare.com")
    signed = sign_faketls_client_hello(hello, secret)
    parsed = parse_faketls_client_hello(signed, secret, timestamp_window=3600)
    assert parsed is not None
    assert parsed.hostname == "www.cloudflare.com"
