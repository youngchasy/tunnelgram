# Changelog

## 2.0

- Public 2.0 release of the proxy-mode redesign.
- Includes the Windows runtime-config path fix from the 0.2.1 development build.
- Cleans ANSI colour sequences from live sing-box logs.
- Decodes sing-box output as UTF-8 on Windows, fixing garbled interface names.
- Supports MTProto forwarding and local HTTP/SOCKS5 mode through HTTP, SOCKS, VLESS, or Hysteria2 profiles.
- Includes cross-platform GitHub Actions builds for Windows, Linux, macOS ARM64, and macOS Intel.

## 0.2.1

- Исправлена проверка профиля на Windows: временная конфигурация sing-box теперь создаётся в локальном каталоге `%TEMP%`, записывается атомарно и проверяется перед запуском.
- Удаляются ANSI-коды цвета из сообщений об ошибках sing-box.
- Временный файл с секретами удаляется после проверки или остановки прокси.

## 0.2.0

- Added selectable legacy MTProto/WSS and local proxy modes.
- Added local mixed HTTP/SOCKS4/SOCKS5 inbound powered by sing-box.
- Added HTTP, HTTPS, SOCKS, VLESS and Hysteria2 URI parsing.
- Added VLESS TLS, Reality and common transport parameters.
- Added Hysteria2 TLS, obfuscation, bandwidth and port-hopping parameters.
- Added local proxy authentication and Telegram SOCKS deep links.
- Added configuration validation with `sing-box check`.
- Added Windows x64, Linux x64, macOS arm64 and macOS x64 release builds.
- Fixed autostart commands for frozen Windows, Linux and macOS builds.
- Added bundled sing-box license/source notices and proxy-profile tests.
