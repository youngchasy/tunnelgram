# Cloudflare DNS proxy domain mode

This optional mode does not use Cloudflare Tunnel and does not require a VPS.

The idea is to publish Cloudflare-proxied hostnames that look like this:

```text
kws1.example.com
kws1-1.example.com
kws2.example.com
kws2-1.example.com
...
```

TunnelGram Direct then connects to:

```text
wss://kws2.example.com/apiws
```

Cloudflare forwards the WebSocket request to the A-record target.

## High-level steps

1. Add your domain to Cloudflare.
2. Create proxied A records for `kws1`, `kws1-1`, `kws2`, `kws2-1`, etc.
3. Point the records at Telegram DC IPs you want to use.
4. In the GUI choose `Cloudflare DNS proxy domain`.
5. Put only the suffix, for example `example.com`.

This is an advanced mode. For the first test, use the default `Telegram Direct WSS` mode instead.
