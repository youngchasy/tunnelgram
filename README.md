# tunnelgram

## Русский

`tunnelgram` — это локальный прокси-клиент для Telegram Desktop.

Он принимает локальное подключение Telegram Desktop на `127.0.0.1`, а затем передаёт зашифрованный MTProto-трафик через официальные Telegram WebSocket/WSS endpoint’ы.

```text
Telegram Desktop
→ 127.0.0.1:9443
→ tunnelgram
→ wss://kws*.web.telegram.org/apiws
→ Telegram
```

Главная идея: сторонний VPS или relay-сервер не нужен. Приложение работает локально и подключается напрямую к WebSocket-серверам Telegram.

---

## Возможности

- локальный MTProto-прокси для Telegram Desktop;
- режим Telegram Direct WSS;
- поддержка Classic `dd-secret`;
- поддержка Fake TLS `ee-secret`;
- запуск в трей;
- проверка WSS-соединения;
- экспорт логов;
- скрипт запуска для Windows;
- скрипт запуска для Linux/macOS;
- опциональный автозапуск вместе с системой: Windows, Linux и macOS.

---

## Быстрый запуск на Windows

### Обычный запуск

Откройте папку проекта и запустите:

```bat
run_windows.bat
```

Скрипт создаст виртуальное окружение Python, установит зависимости и запустит приложение.

### Скрытый запуск без консоли

Сначала один раз запустите обычный запуск:

```bat
run_windows.bat
```

После установки можно запускать:

```text
run_hidden.vbs
```

Так приложение откроется без консольного окна.

---

## Быстрый запуск на Linux / macOS

В корне проекта сделайте скрипт исполняемым:

```bash
chmod +x run_unix.sh
```

Запустите:

```bash
./run_unix.sh
```

Скрипт должен:

1. найти `python3` или `python`;
2. проверить наличие `tkinter`;
3. создать `.venv`;
4. обновить `pip`;
5. установить зависимости из `requirements.txt`;
6. запустить GUI.

### Если на Linux нет tkinter

Debian/Ubuntu:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip python3-tk
```

Fedora:

```bash
sudo dnf install python3 python3-pip python3-tkinter
```

Arch:

```bash
sudo pacman -S python tk
```

### Если на macOS нет tkinter

Рекомендуется установить Python с официального сайта:

```text
https://www.python.org/downloads/macos/
```

Или через Homebrew:

```bash
brew install python
```

После этого снова запустите:

```bash
./run_unix.sh
```

### Тихий скрипт для автозапуска

Для автозапуска на Linux/macOS используется отдельный скрипт:

```bash
run_unix_autostart.sh
```

Он запускает приложение тише, без лишнего вывода в терминал, и подходит для запуска при входе в систему.

Обычно создавать его вручную не нужно: приложение может создать его автоматически при включении автозапуска в настройках.

---

## Настройка Telegram Desktop

В приложении нажмите:

```text
Включить
```

Затем нажмите:

```text
Telegram
```

Telegram должен предложить добавить локальный MTProto-прокси.

Если настраиваете вручную:

```text
Host: 127.0.0.1
Port: 9443
Type: MTProto
Secret: возьмите из tunnelgram
```

---

## Рекомендуемые настройки

Рабочие настройки по умолчанию:

```text
Адрес: 127.0.0.1
Порт: 9443
Secret mode: Fake TLS
SNI: www.google.com
Route: Telegram Direct WSS
Domain style: kws
Pin IP: выключено
TCP fallback: выключено
Autostart: по желанию
```

Если Fake TLS не работает в вашей версии Telegram Desktop, попробуйте Classic secret.

---

## Что такое WSS

WSS — это WebSocket поверх TLS, то есть защищённое постоянное соединение, похожее на HTTPS.

Telegram поддерживает WebSocket transport для MTProto. Поэтому `tunnelgram` может не использовать сторонний сервер, а подключаться напрямую к Telegram WSS endpoint’ам:

```text
wss://kws1.web.telegram.org/apiws
wss://kws2.web.telegram.org/apiws
...
```

`tunnelgram` не расшифровывает Telegram-сообщения. Он принимает зашифрованный поток от Telegram Desktop и перекладывает его в WSS-соединение к Telegram.

---

## Безопасность простыми словами

`tunnelgram` не должен видеть ваши сообщения в читаемом виде.

Telegram Desktop передаёт через прокси уже зашифрованный MTProto-трафик. Приложение только перекладывает эти байты из локального подключения в WebSocket-соединение к Telegram.

Приложение может видеть технические данные:

```text
локальный IP и порт
адрес Telegram DC / WSS endpoint
время подключений
размер трафика
количество соединений
ошибки подключения
локальный proxy secret
```

Приложение не должно видеть:

```text
текст сообщений
файлы в читаемом виде
названия чатов
контакты
пароли
коды входа
историю браузера
данные других приложений
```

Важно: это справедливо только для честной версии приложения из открытого исходного кода. Не запускайте неизвестные `.exe` из случайных источников.

---

## Безопасное использование

Рекомендуется:

- запускать приложение только из открытого исходного кода или доверенной сборки;
- слушать только `127.0.0.1`;
- не использовать `0.0.0.0` или LAN-адреса для локального прокси;
- не передавать proxy secret посторонним;
- не скачивать неизвестные `.exe` из случайных источников;
- проверять релизные архивы и контрольные суммы, если они опубликованы;
- держать Python и зависимости обновлёнными.

`tunnelgram` не должен:

- читать переписки Telegram;
- сохранять сообщения;
- отправлять телеметрию;
- отправлять логи разработчику;
- использовать скрытые автообновления;
- открывать универсальный прокси наружу;
- передавать трафик через сторонний сервер без явного выбора пользователя.

---

## Приватность и хранение данных

`tunnelgram` не собирает пользовательские данные и не отправляет телеметрию.

Приложение может обрабатывать:

```text
локальный адрес и порт прокси
proxy secret
SNI-домен для Fake TLS
выбранный маршрут
настройки темы
настройку автозапуска
технические логи подключения
```

Эти данные нужны для работы приложения.

В обычном режиме Telegram Direct WSS трафик идёт так:

```text
Telegram Desktop
→ tunnelgram на локальном компьютере
→ Telegram WSS endpoint
```

`tunnelgram` не отправляет данные разработчику.

---

## Локальное хранение настроек

Настройки сохраняются локально.

На Windows обычно:

```text
%APPDATA%\TunnelGram\config.json
```

На Linux/macOS обычно:

```text
~/.tunnelgram/config.json
```

Файл настроек может содержать proxy secret.

---

## Логи

Логи отображаются в интерфейсе приложения.

По умолчанию они не сохраняются на диск.  
Пользователь может вручную экспортировать логи в файл кнопкой:

```text
Экспорт
```

При выходе из приложения GUI-логи очищаются.

Перед публикацией логов удалите:

```text
proxy secret
локальные пути
IP-адреса, если не хотите их раскрывать
```

---

## Автозапуск

В настройках можно включить:

```text
Запускать вместе с системой
```

По умолчанию автозапуск выключен.

Поддерживаемые варианты автозапуска:

```text
Windows → HKCU\Software\Microsoft\Windows\CurrentVersion\Run
Linux   → ~/.config/autostart/tunnelgram.desktop
macOS   → ~/Library/LaunchAgents/com.tunnelgram.app.plist
```

На Windows автозапуск добавляется только для текущего пользователя и не требует прав администратора.

На Linux используется стандартный desktop-entry автозапуск через `~/.config/autostart`.

На macOS используется пользовательский LaunchAgent через `~/Library/LaunchAgents`.

Для Linux/macOS автозапуска используется скрипт:

```text
run_unix_autostart.sh
```

---

## Сообщение об уязвимости

Если вы нашли проблему безопасности:

1. не публикуйте exploit публично сразу;
2. опишите проблему;
3. приложите шаги воспроизведения;
4. укажите версию приложения;
5. приложите минимальные логи без секретов.

---

## Как удалить данные приложения

Для удаления локальных настроек удалите папку:

```text
%APPDATA%\TunnelGram
```

Также можно удалить запись автозапуска:

```text
Windows → HKCU\Software\Microsoft\Windows\CurrentVersion\Run
Linux   → ~/.config/autostart/tunnelgram.desktop
macOS   → ~/Library/LaunchAgents/com.tunnelgram.app.plist
```

---

## Ограничения

`tunnelgram` — локальный транспортный мост, а не полноценный VPN.

Он не скрывает весь интернет-трафик.  
Он не меняет IP-адрес пользователя.  
Он не является анонимайзером.  
Он работает только с Telegram Desktop, который настроен на локальный MTProto-прокси.

---

# English

`tunnelgram` is a local proxy client for Telegram Desktop.

It accepts a local Telegram Desktop connection on `127.0.0.1`, then forwards encrypted MTProto traffic through official Telegram WebSocket/WSS endpoints.

```text
Telegram Desktop
→ 127.0.0.1:9443
→ tunnelgram
→ wss://kws*.web.telegram.org/apiws
→ Telegram
```

The main idea: no third-party VPS or relay server is required. The app runs locally and connects directly to Telegram WebSocket servers.

---

## Features

- local MTProto proxy for Telegram Desktop;
- Telegram Direct WSS mode;
- Classic `dd-secret` support;
- Fake TLS `ee-secret` support;
- tray mode;
- WSS connectivity check;
- log export;
- Windows launch script;
- Linux/macOS launch script;
- optional system autostart on Windows, Linux, and macOS.

---

## Quick start on Windows

### Normal launch

Open the project folder and run:

```bat
run_windows.bat
```

The script creates a Python virtual environment, installs dependencies, and starts the app.

### Hidden launch without console

First run the normal launcher once:

```bat
run_windows.bat
```

After installation, you can use:

```text
run_hidden.vbs
```

This starts the app without a console window.

---

## Quick start on Linux / macOS

Make the script executable:

```bash
chmod +x run_unix.sh
```

Run:

```bash
./run_unix.sh
```

The script should:

1. find `python3` or `python`;
2. check for `tkinter`;
3. create `.venv`;
4. upgrade `pip`;
5. install dependencies from `requirements.txt`;
6. start the GUI.

### If tkinter is missing on Linux

Debian/Ubuntu:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip python3-tk
```

Fedora:

```bash
sudo dnf install python3 python3-pip python3-tkinter
```

Arch:

```bash
sudo pacman -S python tk
```

### If tkinter is missing on macOS

It is recommended to install Python from the official website:

```text
https://www.python.org/downloads/macos/
```

Or use Homebrew:

```bash
brew install python
```

Then run again:

```bash
./run_unix.sh
```

### Silent autostart script

Linux/macOS autostart uses a separate script:

```bash
run_unix_autostart.sh
```

It starts the app quietly, without extra terminal output, and is suitable for login autostart.

Usually, you do not need to create it manually: the app can create it automatically when autostart is enabled in settings.

---

## Telegram Desktop setup

In the app, click:

```text
Включить
```

Then click:

```text
Telegram
```

Telegram should ask you to add the local MTProto proxy.

Manual setup:

```text
Host: 127.0.0.1
Port: 9443
Type: MTProto
Secret: copy it from tunnelgram
```

---

## Recommended settings

Default working settings:

```text
Host: 127.0.0.1
Port: 9443
Secret mode: Fake TLS
SNI: www.google.com
Route: Telegram Direct WSS
Domain style: kws
Pin IP: disabled
TCP fallback: disabled
Autostart: optional
```

If Fake TLS does not work with your Telegram Desktop version, try Classic secret.

---

## What is WSS

WSS is WebSocket over TLS, a secure persistent connection similar to HTTPS.

Telegram supports WebSocket transport for MTProto. That is why `tunnelgram` does not need a third-party server and can connect directly to Telegram WSS endpoints:

```text
wss://kws1.web.telegram.org/apiws
wss://kws2.web.telegram.org/apiws
...
```

`tunnelgram` does not decrypt Telegram messages. It receives an encrypted stream from Telegram Desktop and moves it into a WSS connection to Telegram.

---

## Security in simple words

`tunnelgram` should not see your messages in readable form.

Telegram Desktop sends already encrypted MTProto traffic through the proxy. The app only moves these bytes from a local connection into a WebSocket connection to Telegram.

The app may see technical metadata:

```text
local IP and port
Telegram DC / WSS endpoint
connection time
traffic volume
number of connections
connection errors
local proxy secret
```

The app should not see:

```text
message text
files in readable form
chat names
contacts
passwords
login codes
browser history
data from other apps
```

This is true only for a trusted build from open source code. Do not run unknown `.exe` files from random sources.

---

## Safe usage

Recommended:

- run the app only from open source code or a trusted build;
- listen only on `127.0.0.1`;
- do not use `0.0.0.0` or LAN addresses for the local proxy;
- do not share your proxy secret;
- do not download unknown `.exe` files from random sources;
- verify release archives and checksums if published;
- keep Python and dependencies updated.

`tunnelgram` should not:

- read Telegram chats;
- store messages;
- send telemetry;
- send logs to the developer;
- use hidden auto-updates;
- expose a universal proxy to the network;
- route traffic through a third-party server without explicit user choice.

---

## Privacy and local data

`tunnelgram` does not collect user data and does not send telemetry.

The app may process:

```text
local proxy address and port
proxy secret
Fake TLS SNI domain
selected route mode
theme settings
autostart setting
technical connection logs
```

These values are required for the app to work.

In the normal Telegram Direct WSS mode, traffic flows as follows:

```text
Telegram Desktop
→ tunnelgram on the local computer
→ Telegram WSS endpoint
```

`tunnelgram` does not send data to the developer.

---

## Local settings storage

Settings are stored locally.

On Windows, usually:

```text
%APPDATA%\TunnelGram\config.json
```

On Linux/macOS, usually:

```text
~/.tunnelgram/config.json
```

The settings file may contain the proxy secret.

---

## Logs

Logs are displayed in the application UI.

By default, logs are not saved to disk.  
The user can manually export logs to a file using:

```text
Export
```

GUI logs are cleared when the app exits.

Before sharing logs, remove:

```text
proxy secret
local paths
IP addresses, if you do not want to disclose them
```

---

## Autostart

Settings can enable:

```text
Start with system
```

Autostart is disabled by default.

Supported autostart methods:

```text
Windows → HKCU\Software\Microsoft\Windows\CurrentVersion\Run
Linux   → ~/.config/autostart/tunnelgram.desktop
macOS   → ~/Library/LaunchAgents/com.tunnelgram.app.plist
```

On Windows, autostart is added only for the current user and does not require administrator rights.

On Linux, autostart uses the standard desktop-entry mechanism through `~/.config/autostart`.

On macOS, autostart uses a user LaunchAgent through `~/Library/LaunchAgents`.

Linux/macOS autostart uses this script:

```text
run_unix_autostart.sh
```

---

## Reporting a vulnerability

If you find a security issue:

1. do not immediately publish an exploit;
2. describe the issue;
3. include reproduction steps;
4. include the app version;
5. include minimal logs without secrets.

---

## How to delete app data

To delete local settings, remove:

```text
%APPDATA%\TunnelGram
```

You can also remove the autostart entry:

```text
Windows → HKCU\Software\Microsoft\Windows\CurrentVersion\Run
Linux   → ~/.config/autostart/tunnelgram.desktop
macOS   → ~/Library/LaunchAgents/com.tunnelgram.app.plist
```

---

## Limitations

`tunnelgram` is a local transport bridge, not a full VPN.

It does not hide all internet traffic.  
It does not change the user’s IP address.  
It is not an anonymizer.  
It works only with Telegram Desktop configured to use the local MTProto proxy.
