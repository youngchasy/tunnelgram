# Tunnelgram Android — этап 1

Это отдельное нативное Android-приложение на Kotlin. Оно поднимает на телефоне локальный `mixed`-вход sing-box:

```text
Telegram Android → SOCKS5 127.0.0.1:9443 → Tunnelgram → внешний профиль
Другое приложение → HTTP 127.0.0.1:9443 ───────────────┘
```

## Возможности первой версии

- один сохранённый профиль;
- `http://` и `https://`;
- `socks://`, `socks4://`, `socks4a://`, `socks5://`, `socks5h://`;
- `vless://`, включая TLS, Reality, WebSocket, gRPC, HTTPUpgrade, HTTP и QUIC;
- `hysteria2://` и `hy2://`, включая TLS, obfs, bandwidth и port hopping;
- локальная HTTP/SOCKS5-прокси только на `127.0.0.1`;
- foreground service с постоянным уведомлением;
- запуск, остановка, проверка URI и журнал;
- кнопка открытия локальной SOCKS5-прокси в Telegram;
- Android 7.0 (API 24) и новее;
- ARM 32-bit (`armeabi-v7a`) и ARM 64-bit (`arm64-v8a`).

VPN/TUN, QR-код, список профилей, автозапуск и MTProto→WSS в этот этап не входят.

## Три APK

Workflow создаёт:

```text
tunnelgram-android-legacy-armeabi-v7a.apk
tunnelgram-android-modern-arm64-v8a.apk
tunnelgram-android-universal.apk
```

- **legacy / armeabi-v7a** — для 32-битной Android-системы. Работает на Android 7.0+.
- **modern / arm64-v8a** — для 64-битной Android-системы. Работает на Android 7.0+.
- **universal** — содержит оба ядра и подходит для обеих архитектур, но занимает больше места.

Версия Android и разрядность — разные характеристики. Телефон с Android 13 может иметь 32-битную пользовательскую систему. Если архитектура неизвестна, устанавливайте universal APK.

## Почему sing-box лежит как `libsingbox.so`

Во время сборки workflow скачивает официальные standalone Android-бинарники sing-box для `armv7` и `arm64`. Они помещаются в ABI-каталоги приложения под именем `libsingbox.so`, чтобы Android установил исполняемый ELF-файл в защищённый `nativeLibraryDir`. Kotlin-служба запускает этот файл как дочерний процесс с локальной конфигурацией.

В Git не нужно добавлять бинарники вручную: каталоги `jniLibs` заполняются workflow.

## Сборка на GitHub без консоли

1. Загрузите каталог `android` и `.github/workflows/build-android.yml` в репозиторий.
2. Откройте **Actions → Build Android APKs → Run workflow**.
3. Для первой проверки оставьте **Upload APKs to a GitHub Release** выключенным.
4. После зелёной сборки скачайте artifact `tunnelgram-android-apks`.
5. Сначала попробуйте universal APK. Если он устанавливается и работает, отдельный APK не обязателен.

## Подпись APK

Если четыре GitHub Secrets не настроены, workflow всё равно создаст устанавливаемые APK, но подпишет их временным debug-ключом. При следующей сборке Android может потребовать удалить старую версию перед установкой.

Для стабильных обновлений добавьте в **Settings → Secrets and variables → Actions**:

```text
ANDROID_KEYSTORE_BASE64
ANDROID_KEYSTORE_PASSWORD
ANDROID_KEY_ALIAS
ANDROID_KEY_PASSWORD
```

`ANDROID_KEYSTORE_BASE64` — содержимое JKS/PKCS12-файла, закодированное Base64 одной строкой. Ключ нельзя добавлять в публичный репозиторий или прикреплять к Release.

## Использование

1. Установите подходящий APK.
2. Разрешите уведомления на Android 13+, чтобы видеть работу foreground service.
3. Вставьте VLESS/Hysteria2/HTTP/SOCKS5-ссылку.
4. Оставьте порт `9443` или выберите свободный.
5. Нажмите **Проверить**, затем **Запустить**.
6. После статуса `Работает: 127.0.0.1:9443` нажмите **Открыть SOCKS5 в Telegram**.
7. Подтвердите добавление прокси в Telegram.

Для ручной настройки Telegram:

```text
Тип: SOCKS5
Сервер: 127.0.0.1
Порт: 9443
Логин: пусто
Пароль: пусто
```

## Ограничения этапа 1

- Android может остановить приложение при агрессивной экономии батареи. Добавьте Tunnelgram в исключения энергосбережения ROM, если служба пропадает.
- Через прокси идёт только приложение, которое явно подключено к `127.0.0.1`. Это не системный VPN.
- Проверка кнопкой **Проверить** проверяет синтаксис URI. Полная проверка конфигурации выполняется встроенным `sing-box check` при запуске.
- Локальный порт доступен только на loopback и не открывается в Wi-Fi-сеть.
- Профиль хранится в приватных SharedPreferences приложения, но пользователь с root-доступом может прочитать его.
