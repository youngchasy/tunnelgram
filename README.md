# tunnelgram 2.0

`tunnelgram` — локальное приложение для подключения Telegram Desktop. В версии 2.0 доступны два независимых режима работы:

1. **MTProto → Telegram WSS** — прежняя локальная переадресация MTProto-трафика в официальные WSS endpoint’ы Telegram.
2. **Локальная HTTP/SOCKS5-прокси** — приложение поднимает на компьютере один локальный порт, который одновременно принимает HTTP CONNECT и SOCKS4/4a/5. Внешним подключением может быть HTTP, SOCKS5, VLESS или Hysteria2.

```text
Режим MTProto
Telegram Desktop → 127.0.0.1:9443 → tunnelgram → Telegram WSS

Режим локальной прокси
Telegram Desktop → SOCKS5 127.0.0.1:9443 → tunnelgram/sing-box → внешний профиль → интернет
Другое приложение → HTTP 127.0.0.1:9443 ────────────────┘
```

## Что нового в 2.0

- переключатель режима программы;
- входящие локальные HTTP и SOCKS5 на одном порту;
- внешние профили `http://`, `https://`, `socks5://`, `vless://`, `hysteria2://` и `hy2://`;
- VLESS с TLS/Reality и распространёнными транспортами WebSocket, gRPC, HTTPUpgrade, HTTP и QUIC;
- Hysteria2 с TLS, bandwidth-параметрами, obfs и port hopping;
- необязательная авторизация на локальной прокси;
- автоматический поиск `sing-box` и возможность выбрать исполняемый файл вручную;
- проверка создаваемой конфигурации командой `sing-box check` до запуска;
- сборки Windows x64, Linux x64, macOS Apple Silicon и macOS Intel;
- автоматическое добавление `sing-box` в каждый архив релиза;
- unit-тесты для парсинга профилей и генерации конфигурации.

## Быстрый запуск готовой сборки

Скачайте архив своей системы со страницы **Releases**, распакуйте его полностью и запускайте `tunnelgram`:

- Windows: `tunnelgram.exe`;
- Linux: `./tunnelgram`;
- macOS: `tunnelgram.app`.

Не отделяйте `sing-box` от приложения. В Windows и Linux он лежит рядом с `tunnelgram`; в macOS он встроен в ресурсы `.app`.

Сборки macOS подписываются локальной ad-hoc подписью, но не нотарифицируются Apple. При первом запуске может понадобиться открыть приложение через контекстное меню **Open / Открыть**.

## Запуск из исходников

Требуется Python 3.11+; в GitHub Actions используется Python 3.12.

### Windows

```bat
run_windows.bat
```

Для запуска без консольного окна после первой установки:

```text
run_hidden.vbs
```

### Linux / macOS

```bash
chmod +x run_unix.sh
./run_unix.sh
```

На Debian/Ubuntu при необходимости:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip python3-tk
```

### sing-box при запуске из исходников

Для нового режима нужен CLI core `sing-box`. Готовые GitHub-сборки уже содержат его. При запуске из исходников используйте один из вариантов:

- положите `sing-box` или `sing-box.exe` в корень проекта;
- установите его в `PATH`;
- выберите файл в настройках tunnelgram;
- задайте переменную окружения `TUNNELGRAM_SING_BOX`.

В автоматических сборках закреплена версия `sing-box 1.13.14`.

## Режим 1: MTProto → Telegram WSS

1. Откройте **Настройки → Основное**.
2. Выберите **MTProto → Telegram WSS**.
3. Укажите локальный адрес и порт. Для обычного использования оставьте `127.0.0.1:9443`.
4. Настройте secret, Fake TLS/SNI и маршрут.
5. Нажмите **Включить**.
6. Нажмите **Telegram**, чтобы открыть ссылку добавления локального MTProto-прокси.

При ручной настройке Telegram:

```text
Type: MTProto
Host: 127.0.0.1
Port: 9443
Secret: значение из tunnelgram
```

## Режим 2: локальная HTTP/SOCKS5-прокси

1. Откройте **Настройки → Основное**.
2. Выберите **Локальный HTTP/SOCKS5 через внешний профиль**.
3. Оставьте адрес `127.0.0.1` или `localhost`. Из соображений безопасности программа не разрешает слушать внешний сетевой интерфейс в этом режиме.
4. Укажите свободный локальный порт, например `9443` или `1080`.
5. Вставьте внешнюю ссылку подключения.
6. При необходимости задайте локальный логин и пароль — обязательно оба поля вместе.
7. Нажмите **Проверить соединение**, затем **Включить**.
8. Нажмите **Telegram**. Будет открыта SOCKS5-ссылка на локальный порт.

На одном локальном порту работают оба протокола:

```text
SOCKS5: 127.0.0.1:<порт>
HTTP:   127.0.0.1:<порт>
```

Для Telegram рекомендуется выбирать **SOCKS5**. HTTP-вход можно использовать в других программах и в клиентах, где доступен тип HTTP Proxy.

### Примеры внешних профилей

Замените значения на свои. Не публикуйте рабочие ссылки в issues или логах.

```text
http://user:password@proxy.example:8080
https://user:password@proxy.example:443?sni=proxy.example
socks5://user:password@proxy.example:1080
vless://UUID@server.example:443?security=tls&sni=cdn.example&type=ws&path=%2Fws&host=cdn.example
vless://UUID@server.example:443?security=reality&sni=example.com&fp=chrome&pbk=PUBLIC_KEY&sid=SHORT_ID&flow=xtls-rprx-vision
hysteria2://password@server.example:443?sni=cdn.example&obfs=salamander&obfs-password=MASK
```

Поддерживаемые схемы:

```text
http, https, socks, socks4, socks4a, socks5, socks5h, vless, hysteria2, hy2
```

## Где хранятся настройки

Windows:

```text
%APPDATA%\tunnelgram\config.json
%TEMP%\tunnelgram\sing-box-<случайный-id>.json
```

Linux/macOS:

```text
~/.tunnelgram/config.json
${TMPDIR:-/tmp}/tunnelgram/sing-box-<случайный-id>.json
```

В профиле могут находиться пароль, UUID и другие секреты. На Unix-файлы создаются с правами `0600`, однако доступ к учётной записи пользователя всё равно означает доступ к этим данным.

В интерфейсе внешняя ссылка показывается в скрытом виде. Не отправляйте исходный `config.json`, временный `sing-box-*.json` или полную ссылку третьим лицам.

## Проверка проекта локально

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m compileall tunnelgram
python -m py_compile tunnelgram_app.py
python -m pytest -q
```

## GitHub Actions

В репозитории находятся три workflow.

### `python-check.yml`

Запускается при push в ветку и при pull request. Он:

- устанавливает зависимости;
- компилирует Python-файлы;
- импортирует основные модули;
- запускает unit-тесты.

### `build-release.yml`

Основной workflow релиза. Он собирает четыре архива:

```text
tunnelgram-windows-x64.zip
tunnelgram-linux-x64.tar.gz
tunnelgram-macos-arm64.zip
tunnelgram-macos-x64.zip
```

Каждая сборка скачивает закреплённый официальный `sing-box`, добавляет его рядом с программой или внутрь `.app`, а также прикладывает лицензию и ссылку на исходный код sing-box.

### `build-macos-only.yml`

Ручная отдельная сборка двух вариантов macOS. Полезна, когда менялась только упаковка macOS или нужно повторно загрузить macOS-архивы в уже существующий Release.

## Как проверить сборки без создания релиза

1. Залейте изменения в ветку `main`.
2. На GitHub откройте вкладку **Actions**.
3. Слева выберите **Build release binaries**.
4. Нажмите **Run workflow**.
5. Оставьте **Upload the archives to a GitHub Release** выключенным.
6. После завершения откройте запуск и скачайте файлы в секции **Artifacts**.

Artifacts хранятся ограниченное время и предназначены для проверки. Пользовательские версии лучше публиковать в **Releases**.

## Как выпустить новую версию через тег

Сначала измените версию в:

```text
tunnelgram/__init__.py
```

Например:

```python
__version__ = "2.0"
```

Затем выполните:

```bash
git add .
git commit -m "Release v2.0"
git push origin main
git tag -a v2.0 -m "tunnelgram 2.0"
git push origin v2.0
```

Push тега `v*` автоматически запускает `build-release.yml`. После успешной сборки workflow:

1. создаст GitHub Release, если его ещё нет;
2. загрузит туда все четыре архива;
3. заменит архивы с теми же именами при повторном запуске.

Не создавайте одновременно Release вручную и тег отдельными действиями с разными версиями. Источником версии должен быть один и тот же тег, например `v2.0`.

## Ручная загрузка в существующий Release

1. Убедитесь, что Release с нужным тегом уже существует.
2. Откройте **Actions → Build release binaries → Run workflow**.
3. Включите **Upload the archives to a GitHub Release**.
4. Введите точный тег, например `v2.0`.
5. Запустите workflow.

Для только macOS используйте **Build macOS only** и те же поля.

## Локальная ручная сборка

Установите PyInstaller:

```bash
python -m pip install -r requirements.txt
python -m pip install "pyinstaller>=6.0"
```

Windows:

```powershell
pyinstaller --noconfirm --clean --onefile --windowed --name tunnelgram --icon assets/tunnelgram.ico --add-data "assets;assets" tunnelgram_app.py
```

Linux:

```bash
pyinstaller --noconfirm --clean --onefile --windowed --name tunnelgram --add-data "assets:assets" tunnelgram_app.py
```

macOS:

```bash
pyinstaller --noconfirm --clean --onedir --windowed --name tunnelgram --add-data "assets:assets" tunnelgram_app.py
```

После локальной сборки вручную положите подходящий `sing-box` рядом с Windows/Linux executable. Для macOS поместите его в:

```text
tunnelgram.app/Contents/Resources/sing-box
```

GitHub Actions делает это автоматически и поэтому является рекомендуемым способом выпуска архивов.

## Ограничения

- tunnelgram не выдаёт и не продаёт VLESS/Hysteria2-профили — пользователь вставляет собственную ссылку;
- поддерживаются распространённые URI-параметры, но редкий или нестандартный формат ссылки провайдера может потребовать адаптации;
- новый режим создаёт локальную прикладную прокси, а не системный VPN/TUN;
- DNS и UDP-возможности зависят от выбранного внешнего протокола и программы-клиента;
- приложение не обходит ограничения macOS Gatekeeper с помощью платной Developer ID подписи или notarization;
- работоспособность конкретного сервера проверяется только реальным подключением: `sing-box check` проверяет структуру конфигурации, а не доступность сервера.

## Лицензии и сторонние компоненты

Сведения о `sing-box`, его GPLv3-лицензии и исходном коде находятся в [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Архивы релиза также содержат полный текст лицензии sing-box.

---

## English summary

`tunnelgram 2.0` supports two modes: the original local MTProto-to-Telegram-WSS bridge and a local mixed HTTP/SOCKS5 proxy routed through an HTTP, SOCKS, VLESS or Hysteria2 URI. Release workflows build Windows x64, Linux x64, macOS arm64 and macOS Intel archives and bundle a pinned sing-box core with its license and source reference.

For a test build, run **Actions → Build release binaries → Run workflow** without release upload. For a public release, update `tunnelgram/__init__.py`, commit, push, create a `v*` tag and push the tag. The workflow creates or updates the matching GitHub Release automatically.
