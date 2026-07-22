from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import webbrowser
import time
import socket
import ctypes
import plistlib
import stat
import shutil
import urllib.error
import urllib.request
from pathlib import Path
import tkinter as tk
from tkinter import END, BooleanVar, StringVar, Toplevel, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText

from . import __version__
from .faketls import build_faketls_secret_hex, hostname_to_hex
from .mtproto import generate_secret_hex, telegram_link, validate_secret_hex
from .proxy_profiles import (
    ProxyProfileError,
    build_singbox_config,
    find_sing_box_binary,
    parse_proxy_uri,
    redact_proxy_uri,
    telegram_socks_link,
    write_singbox_runtime_config,
)

APP_NAME = "tunnelgram"
VERSION = __version__
PROJECT_ROOT = Path(__file__).resolve().parents[1]
GITHUB_REPO = "youngchasy/tunnelgram"
GITHUB_LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

GITHUB_REPO_URL = f"https://github.com/{GITHUB_REPO}"
GITHUB_RELEASES_URL = f"{GITHUB_REPO_URL}/releases"
GITHUB_LATEST_RELEASE_URL = f"{GITHUB_REPO_URL}/releases/latest"

AUTOSTART_REG_NAME = "tunnelgram"
AUTOSTART_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

ASSETS_DIR = PROJECT_ROOT / "assets"
ICON_ICO = ASSETS_DIR / "tunnelgram.ico"
ICON_PNG = ASSETS_DIR / "tunnelgram.png"

WINDOWS_APP_ID = "tunnelgram.desktop.app"

INSTANCE_LOCK_HOST = "127.0.0.1"
INSTANCE_LOCK_PORT = 48173

LINUX_AUTOSTART_DIR = Path.home() / ".config" / "autostart"
LINUX_DESKTOP_FILE = LINUX_AUTOSTART_DIR / "tunnelgram.desktop"

MACOS_LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
MACOS_PLIST_FILE = MACOS_LAUNCH_AGENTS_DIR / "com.tunnelgram.app.plist"

UNIX_AUTOSTART_SCRIPT = PROJECT_ROOT / "run_unix_autostart.sh"

try:
    import pystray
    from PIL import Image, ImageDraw
except Exception:
    pystray = None
    Image = None
    ImageDraw = None

if sys.platform == "darwin":
    pystray = None

WORKING_DEFAULT_SECRET = "0a341d255f8ce1d5fcaf894cc2ee523a"

THEMES = {
    "light": {
        "title": "Светлая",
        "bg": "#f5f5f5",
        "surface": "#ffffff",
        "surface2": "#f0f0f0",
        "card": "#ffffff",
        "border": "#d4d4d4",
        "text": "#18181b",
        "muted": "#71717a",
        "soft_text": "#3f3f46",
        "primary": "#2563eb",
        "primary_hover": "#1d4ed8",
        "primary_fg": "#ffffff",
        "secondary": "#e4e4e7",
        "secondary_hover": "#d4d4d8",
        "secondary_fg": "#18181b",
        "danger": "#ef4444",
        "danger_hover": "#dc2626",
        "danger_fg": "#ffffff",
        "good": "#16a34a",
        "warn": "#d97706",
        "bad": "#dc2626",
        "entry": "#ffffff",
        "log_bg": "#111111",
        "log_fg": "#e5e5e5",
    },
    "dark": {
        "title": "Тёмная",
        "bg": "#181818",
        "surface": "#202020",
        "surface2": "#252525",
        "card": "#222222",
        "border": "#333333",
        "text": "#f3f4f6",
        "muted": "#a1a1aa",
        "soft_text": "#d4d4d8",
        "primary": "#3b82f6",
        "primary_hover": "#2563eb",
        "primary_fg": "#ffffff",
        "secondary": "#303030",
        "secondary_hover": "#3a3a3a",
        "secondary_fg": "#f4f4f5",
        "danger": "#ef4444",
        "danger_hover": "#dc2626",
        "danger_fg": "#ffffff",
        "good": "#22c55e",
        "warn": "#f59e0b",
        "bad": "#f87171",
        "entry": "#2a2a2a",
        "log_bg": "#101010",
        "log_fg": "#d6d3d1",
    },
}

LANGUAGES = {"ru", "en"}

TRANSLATIONS = {
    "ru": {
        "already_running_message": "tunnelgram уже запущен.\n\nЧтобы открыть окно, найди иконку приложения в трее.",

        "theme_button": "Тема",
        "language_switched": "Язык переключён на русский.",

        "status_stopped": "Остановлен",
        "status_waiting_start": "Ждёт запуска",
        "status_waiting_telegram": "Жду Telegram",
        "status_running": "Работает",
        "status_connected": "Подключён",
        "status_secret_rejected": "Secret не принят",
        "status_network_problem": "Проблема сети",
        "status_wss_available": "WSS доступен",
        "status_profile_valid": "Профиль корректен",
        "status_checking_profile": "Проверяю профиль…",
        "status_wss_not_found": "WSS не найден",
        "status_check_error": "Ошибка проверки",
        "status_no_connections": "Нет подключений",
        "status_checking_wss": "Проверяю WSS…",

        "toggle_on": "Включить",
        "toggle_off": "Выключить",

        "enabled_short": "вкл",
        "disabled_short": "выкл",
        "enabled": "включён",
        "disabled": "выключен",

        "proxy": "Прокси",
        "telegram": "Telegram",
        "traffic": "Трафик",
        "link": "Ссылка",
        "settings": "Настройки",
        "logs": "Логи",

        "minimize_to_tray": "Свернуть в трей",
        "check_connection": "Проверить соединение",
        "export": "Экспорт логов",
        "clear_logs": "Очистить логи",

        "ready_log": "Готово. Нажми «Включить», затем «Telegram». Рекомендуется изменить стандартные настройки, если с первого раза ничего не работает.",

        "settings_window_title": "Настройки tunnelgram",
        "basic": "Основное",
        "program_mode": "Режим программы",
        "mode_mtproto": "MTProto → Telegram WSS (старый режим)",
        "mode_local_proxy": "Локальный HTTP/SOCKS5 через внешний профиль",
        "upstream_proxy_uri": "Ссылка подключения (HTTP, SOCKS5, VLESS или Hysteria2)",
        "upstream_proxy_hint": "Примеры: socks5://user:pass@host:1080, http://host:8080, vless://..., hysteria2://...",
        "local_proxy_username": "Локальный логин (необязательно)",
        "local_proxy_password": "Локальный пароль (необязательно)",
        "sing_box_path": "Путь к sing-box (обычно определяется автоматически)",
        "browse": "Обзор",
        "sing_box_files": "sing-box executable",
        "profile_required": "Для режима локальной прокси нужна ссылка HTTP/SOCKS5/VLESS/Hysteria2.",
        "local_auth_pair": "Локальный логин и пароль нужно задавать вместе.",
        "sing_box_missing": "Не найден sing-box core. Положи sing-box рядом с tunnelgram или выбери файл в настройках.",
        "profile_valid": "Профиль корректен: {name}",
        "profile_check_failed": "Проверка профиля не пройдена: {error}",
        "local_proxy_ready": "Локальная HTTP/SOCKS5 прокси готова. Добавь в Telegram SOCKS5 {host}:{port}.",
        "proxy_mode_local_only": "В режиме локальной прокси адрес должен быть 127.0.0.1, localhost или ::1.",
        "checking_proxy_profile": "Проверяю профиль через sing-box…",
        "address": "Адрес",
        "port": "Порт",
        "secret_label": "Secret (рекомендуется изменить)",
        "secret_type_label": "Тип secret (дефолт Fake TLS)",
        "sni": "SNI",
        "autostart_label": "Запускать вместе с системой",
        "autostart_hint": "по умолчанию выключено",

        "route": "Маршрут",
        "mode_label": "Режим (дефолт Direct WSS)",
        "cf_hint": "только если есть свой домен в Cloudflare",
        "cf_suffix": "Cloudflare suffix (вводить если выбран режим Cloudflare DNS)",
        "domains_label": "Домены (дефолт kws)",
        "pin_ip_label": "Pin Telegram IP",
        "pin_ip_hint": "может помочь при плохом DNS, но иногда ломает часть DC",
        "direct_fallback_label": "Direct TCP fallback",
        "direct_fallback_hint": "пробовать прямое TCP-подключение к Telegram DC, если WSS не работает",
        "dc_names": "имена DC",

        "save": "Сохранить",
        "close": "Закрыть",

        "settings_saved": "Настройки сохранены.",
        "autostart_system": "Автозапуск системы: {state}",

        "logs_empty": "Логи пустые, экспортировать нечего.",
        "export_logs_title": "Экспорт логов",
        "save_logs_failed": "Не удалось сохранить логи:\n\n{error}",
        "logs_exported": "Логи экспортированы: {path}",
        "logs_cleared": "Логи очищены.",
        "hidden_wss_events": "Скрыто {count} коротких WSS-событий.",

        "port_must_be_number": "Порт должен быть числом",
        "port_range": "Порт должен быть от 1 до 65535",
        "faketls_sni_required": "Для Fake TLS нужен SNI-домен, например www.google.com",
        "cf_suffix_required": "Для Cloudflare DNS нужен suffix, например example.com",

        "full_secret_copied": "Полный secret скопирован.",
        "tg_link_copied": "Ссылка tg:// скопирована.",
        "open_telegram_log": "Открываю Telegram. Если окно не развернулось автоматически, разверни его вручную и согласись на добавление локального прокси.",
        "open_telegram_failed": "Не удалось открыть Telegram автоматически.\n\nСсылка скопирована в буфер обмена — вставь её вручную в Telegram Desktop.",
        "new_secret_generated": "Сгенерирован новый base secret.",

        "proxy_already_started": "Прокси уже запущен.",
        "proxy_started": "Прокси запущен.",
        "proxy_start_failed": "Не удалось запустить прокси: {error}",
        "proxy_not_started": "Прокси не запущен.",
        "proxy_stopped": "Прокси остановлен.",

        "check_wss_log": "Проверяю WSS endpoint’ы…",

        "tray_show_hide": "Показать / скрыть",
        "tray_show_window": "Показать окно",
        "tray_toggle_proxy": "Включить / выключить",
        "tray_open_telegram": "Открыть Telegram",
        "tray_copy_tg": "Скопировать tg://",
        "tray_exit": "Выход",
        "tray_xorg_warn": "Linux tray работает через Xorg backend: меню может быть ограничено, ЛКМ должен возвращать окно.",
        "tray_backend": "Linux tray backend: {backend}; menu={menu}; default={default}",
        "tray_unavailable": "Трей недоступен.",
        "tray_hidden": "Окно свёрнуто в трей. Нажми на иконку tunnelgram, чтобы вернуть окно.",

        "updates": "Обновления",
        "check_updates_label": "Проверять обновления при запуске",
        "check_updates_hint": "использует GitHub Releases",
        "check_updates_now": "Проверить обновления",
        "update_status_idle": "Обновления ещё не проверялись.",
        "update_status_checking": "Проверяю обновления…",
        "update_status_latest": "Установлена последняя версия.",
        "update_status_available": "Доступна новая версия: {version}",
        "update_status_later": "Не удалось проверить обновления. Попробуйте проверить обновления позже.",
        "update_status_not_found": "Релиз не найден. Проверь GitHub repo и опубликованный release.",
        "update_status_bad_response": "GitHub вернул непонятный ответ. Попробуйте позже.",
        "update_open_release_question": "Доступна новая версия tunnelgram: {latest}\n\nТекущая версия: v{current}\n\nОткрыть страницу релиза на GitHub?",

        "about": "О программе",
        "about_title": "О tunnelgram",
        "about_description": "Локальный MTProto/WSS-мост и HTTP/SOCKS5-прокси для Telegram Desktop.",
        "about_version": "Версия: v{version}",
        "about_repo": "GitHub: {repo}",
        "about_license": "tunnelgram: MIT; sing-box: GPLv3+ — см. THIRD_PARTY_NOTICES.md",
        "open_github": "Открыть GitHub",
        "open_releases": "Открыть Releases",
        "open_latest_release": "Открыть последний релиз",
        "copy_version": "Скопировать версию",
        "version_copied": "Версия скопирована.",
        "open_config_folder": "Открыть папку конфига",
        "config_folder_opened": "Папка конфига открыта.",
        "config_folder_open_failed": "Не удалось открыть папку конфига:\n\n{error}",

        "reset_settings": "Сбросить настройки",
        "reset_settings_title": "Сбросить настройки?",
        "reset_settings_message": "Это вернёт настройки подключения к значениям по умолчанию.\n\nЯзык, тема и настройка проверки обновлений будут сохранены.",
        "settings_reset_done": "Настройки сброшены.",

        "text_files": "Text files",
        "log_files": "Log files",
        "all_files": "All files",
    },

    "en": {
        "already_running_message": "tunnelgram is already running.\n\nTo open the window, use the app icon in the system tray.",

        "theme_button": "Theme",
        "language_switched": "Language switched to English.",

        "status_stopped": "Stopped",
        "status_waiting_start": "Waiting to start",
        "status_waiting_telegram": "Waiting for Telegram",
        "status_running": "Running",
        "status_connected": "Connected",
        "status_secret_rejected": "Secret rejected",
        "status_network_problem": "Network problem",
        "status_wss_available": "WSS available",
        "status_profile_valid": "Profile is valid",
        "status_checking_profile": "Checking profile…",
        "status_wss_not_found": "WSS not found",
        "status_check_error": "Check failed",
        "status_no_connections": "No connections",
        "status_checking_wss": "Checking WSS…",

        "toggle_on": "Start",
        "toggle_off": "Stop",

        "enabled_short": "on",
        "disabled_short": "off",
        "enabled": "enabled",
        "disabled": "disabled",

        "proxy": "Proxy",
        "telegram": "Telegram",
        "traffic": "Traffic",
        "link": "Link",
        "settings": "Settings",
        "logs": "Logs",

        "minimize_to_tray": "Minimize to tray",
        "check_connection": "Check connection",
        "export": "Export logs",
        "clear_logs": "Clear logs",

        "ready_log": "Ready. Click “Start”, then “Telegram”. Change the default settings if it does not work on the first try.",

        "settings_window_title": "tunnelgram settings",
        "basic": "Basic",
        "program_mode": "Program mode",
        "mode_mtproto": "MTProto → Telegram WSS (legacy mode)",
        "mode_local_proxy": "Local HTTP/SOCKS5 through an upstream profile",
        "upstream_proxy_uri": "Connection URI (HTTP, SOCKS5, VLESS or Hysteria2)",
        "upstream_proxy_hint": "Examples: socks5://user:pass@host:1080, http://host:8080, vless://..., hysteria2://...",
        "local_proxy_username": "Local username (optional)",
        "local_proxy_password": "Local password (optional)",
        "sing_box_path": "sing-box path (normally detected automatically)",
        "browse": "Browse",
        "sing_box_files": "sing-box executable",
        "profile_required": "Local proxy mode requires an HTTP/SOCKS5/VLESS/Hysteria2 URI.",
        "local_auth_pair": "Local username and password must be set together.",
        "sing_box_missing": "sing-box core was not found. Put sing-box next to tunnelgram or select it in settings.",
        "profile_valid": "Profile is valid: {name}",
        "profile_check_failed": "Profile check failed: {error}",
        "local_proxy_ready": "Local HTTP/SOCKS5 proxy is ready. Add SOCKS5 {host}:{port} in Telegram.",
        "proxy_mode_local_only": "Local proxy mode must listen on 127.0.0.1, localhost or ::1.",
        "checking_proxy_profile": "Checking the profile with sing-box…",
        "address": "Address",
        "port": "Port",
        "secret_label": "Secret (recommended to change)",
        "secret_type_label": "Secret type (default: Fake TLS)",
        "sni": "SNI",
        "autostart_label": "Start with system",
        "autostart_hint": "disabled by default",

        "route": "Route",
        "mode_label": "Mode (default: Direct WSS)",
        "cf_hint": "only if you have your own Cloudflare domain",
        "cf_suffix": "Cloudflare suffix (only for Cloudflare DNS mode)",
        "domains_label": "Domains (default: kws)",
        "pin_ip_label": "Pin Telegram IP",
        "pin_ip_hint": "may help with bad DNS, but can break some DCs",
        "direct_fallback_label": "Direct TCP fallback",
        "direct_fallback_hint": "try direct TCP to Telegram DC if WSS does not work",
        "dc_names": "DC names",

        "save": "Save",
        "close": "Close",

        "settings_saved": "Settings saved.",
        "autostart_system": "System autostart: {state}",

        "logs_empty": "Logs are empty, nothing to export.",
        "export_logs_title": "Export logs",
        "save_logs_failed": "Could not save logs:\n\n{error}",
        "logs_exported": "Logs exported: {path}",
        "logs_cleared": "Logs cleared.",
        "hidden_wss_events": "Hidden {count} short WSS events.",

        "port_must_be_number": "Port must be a number",
        "port_range": "Port must be between 1 and 65535",
        "faketls_sni_required": "Fake TLS requires an SNI domain, for example www.google.com",
        "cf_suffix_required": "Cloudflare DNS requires a suffix, for example example.com",

        "full_secret_copied": "Full secret copied.",
        "tg_link_copied": "tg:// link copied.",
        "open_telegram_log": "Opening Telegram. If the window does not appear automatically, open Telegram manually and accept adding the local proxy.",
        "open_telegram_failed": "Could not open Telegram automatically.\n\nThe link was copied to the clipboard — paste it manually into Telegram Desktop.",
        "new_secret_generated": "Generated a new base secret.",

        "proxy_already_started": "Proxy is already running.",
        "proxy_started": "Proxy started.",
        "proxy_start_failed": "Could not start proxy: {error}",
        "proxy_not_started": "Proxy is not running.",
        "proxy_stopped": "Proxy stopped.",

        "check_wss_log": "Checking WSS endpoints…",

        "tray_show_hide": "Show / hide",
        "tray_show_window": "Show window",
        "tray_toggle_proxy": "Start / stop",
        "tray_open_telegram": "Open Telegram",
        "tray_copy_tg": "Copy tg://",
        "tray_exit": "Exit",
        "tray_xorg_warn": "Linux tray is using the Xorg backend: the menu may be limited, left-click should restore the window.",
        "tray_backend": "Linux tray backend: {backend}; menu={menu}; default={default}",
        "tray_unavailable": "System tray is unavailable.",
        "tray_hidden": "Window minimized to tray. Click the tunnelgram icon to restore it.",

        "updates": "Updates",
        "check_updates_label": "Check for updates on startup",
        "check_updates_hint": "uses GitHub Releases",
        "check_updates_now": "Check updates",
        "update_status_idle": "Updates have not been checked yet.",
        "update_status_checking": "Checking for updates…",
        "update_status_latest": "You are using the latest version.",
        "update_status_available": "New version available: {version}",
        "update_status_later": "Could not check for updates. Try checking again later.",
        "update_status_not_found": "Release not found. Check the GitHub repo and published release.",
        "update_status_bad_response": "GitHub returned an unexpected response. Try again later.",
        "update_open_release_question": "A new tunnelgram version is available: {latest}\n\nCurrent version: v{current}\n\nOpen the GitHub release page?",

        "about": "About",
        "about_title": "About tunnelgram",
        "about_description": "Local MTProto/WSS bridge and HTTP/SOCKS5 proxy for Telegram Desktop.",
        "about_version": "Version: v{version}",
        "about_repo": "GitHub: {repo}",
        "about_license": "tunnelgram: MIT; sing-box: GPLv3+ — see THIRD_PARTY_NOTICES.md",
        "open_github": "Open GitHub",
        "open_releases": "Open Releases",
        "open_latest_release": "Open latest release",
        "copy_version": "Copy version",
        "version_copied": "Version copied.",
        "open_config_folder": "Open config folder",
        "config_folder_opened": "Config folder opened.",
        "config_folder_open_failed": "Could not open config folder:\n\n{error}",

        "reset_settings": "Reset settings",
        "reset_settings_title": "Reset settings?",
        "reset_settings_message": "This will restore connection settings to their defaults.\n\nLanguage, theme, and update-check settings will be kept.",
        "settings_reset_done": "Settings reset.",

        "text_files": "Text files",
        "log_files": "Log files",
        "all_files": "All files",
    },
}


def tr_text(key: str, language: str = "en", **kwargs) -> str:
    lang = language if language in TRANSLATIONS else "en"
    text = TRANSLATIONS.get(lang, {}).get(key) or TRANSLATIONS["en"].get(key) or key

    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text

    return text

def app_dir() -> Path:
    if os.name == "nt" and os.getenv("APPDATA"):
        return Path(os.getenv("APPDATA", "")) / "tunnelgram"
    return Path.home() / ".tunnelgram"


CONFIG_PATH = app_dir() / "config.json"

def old_config_path() -> Path:
    if os.name == "nt" and os.getenv("APPDATA"):
        return Path(os.getenv("APPDATA", "")) / "TunnelGram" / "config.json"
    return Path.home() / ".tunnelgram-direct" / "config.json"


DEFAULT_CONFIG = {
    "app_mode": "mtproto",
    "listen_host": "127.0.0.1",
    "listen_port": "9443",
    "secret": WORKING_DEFAULT_SECRET,
    "secret_mode": "ee",
    "fake_tls_domain": "www.google.com",
    "route_mode": "telegram",
    "cf_domain": "",
    "pin_telegram_ip": False,
    "domain_style": "kws",
    "direct_fallback": False,
    "upstream_proxy_uri": "",
    "local_proxy_username": "",
    "local_proxy_password": "",
    "sing_box_path": "",
    "theme": "dark",
    "language": "ru",
    "check_updates": True,
    "autostart": False,
}

class UpdateCheckNetworkError(Exception):
    pass


class UpdateCheckNotFoundError(Exception):
    pass

def fmt_bool(value: bool, language: str = "en") -> str:
    return tr_text("enabled_short" if value else "disabled_short", language)

def setup_windows_app_id() -> None:
    if os.name != "nt":
        return

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except Exception:
        pass

def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def proxy_command() -> list[str]:
    if is_frozen_app():
        return [sys.executable, "--proxy"]

    return [python_console_executable(), "-u", "-m", "tunnelgram.local_proxy"]

def subprocess_window_kwargs() -> dict:
    if os.name != "nt":
        return {}

    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
    }

def python_console_executable() -> str:
    exe = Path(sys.executable)

    if os.name == "nt" and exe.name.lower() == "pythonw.exe":
        python_exe = exe.with_name("python.exe")
        if python_exe.exists():
            return str(python_exe)

    return sys.executable

def diagnostics_command() -> list[str]:
    if is_frozen_app():
        return [sys.executable, "--diagnostics"]

    return [python_console_executable(), "-u", "-m", "tunnelgram.diagnostics"]

class App(tk.Tk):
    def __init__(self):
        super().__init__()

        cfg = self.load_config()
        initial_language = cfg.get("language", DEFAULT_CONFIG["language"])
        if initial_language not in LANGUAGES:
            initial_language = DEFAULT_CONFIG["language"]

        self._instance_socket: socket.socket | None = None

        if not self.acquire_single_instance_lock():
            self.withdraw()
            messagebox.showinfo(
                APP_NAME,
                tr_text("already_running_message", initial_language),
            )
            self.destroy()
            raise SystemExit(0)

        self.title(f"{APP_NAME} {VERSION}")
        self.geometry("900x640")
        self.minsize(900, 640)
        self.setup_window_icon()

        self.proc: subprocess.Popen | None = None
        self._proc_uses_sing_box = False
        self._sing_box_runtime_config: Path | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.tray_icon = None
        self.tray_thread: threading.Thread | None = None
        self._hidden_to_tray = False
        self._quitting = False
        self._settings_win: Toplevel | None = None
        self._current_cfg: dict = {}
        self._theme_widgets: list[tuple[tk.Widget, str, str | None]] = []
        self._buttons: list[tuple[tk.Button, str]] = []
        self._cards: list[tk.Frame] = []
        self._suppressed_ws_noise = 0
        self._last_ws_noise_report = 0.0
        self._short_ws_close_seconds = 5.0
        self._max_log_lines = 700
        self._log_prune_every = 25
        self._log_lines_since_prune = 0

        self.app_mode = StringVar(value=cfg.get("app_mode", DEFAULT_CONFIG["app_mode"]))
        self.listen_host = StringVar(value=cfg.get("listen_host", DEFAULT_CONFIG["listen_host"]))
        self.listen_port = StringVar(value=str(cfg.get("listen_port", DEFAULT_CONFIG["listen_port"])))
        self.secret = StringVar(value=cfg.get("secret", DEFAULT_CONFIG["secret"]))
        self.secret_mode = StringVar(value=cfg.get("secret_mode", DEFAULT_CONFIG["secret_mode"]))
        self.fake_tls_domain = StringVar(value=cfg.get("fake_tls_domain", DEFAULT_CONFIG["fake_tls_domain"]))
        self.route_mode = StringVar(value=cfg.get("route_mode", DEFAULT_CONFIG["route_mode"]))
        self.cf_domain = StringVar(value=cfg.get("cf_domain", DEFAULT_CONFIG["cf_domain"]))
        self.pin_telegram_ip = BooleanVar(value=bool(cfg.get("pin_telegram_ip", DEFAULT_CONFIG["pin_telegram_ip"])))
        self.domain_style = StringVar(value=cfg.get("domain_style", DEFAULT_CONFIG["domain_style"]))
        self.direct_fallback = BooleanVar(value=bool(cfg.get("direct_fallback", DEFAULT_CONFIG["direct_fallback"])))
        self.upstream_proxy_uri = StringVar(value=cfg.get("upstream_proxy_uri", DEFAULT_CONFIG["upstream_proxy_uri"]))
        self.local_proxy_username = StringVar(value=cfg.get("local_proxy_username", DEFAULT_CONFIG["local_proxy_username"]))
        self.local_proxy_password = StringVar(value=cfg.get("local_proxy_password", DEFAULT_CONFIG["local_proxy_password"]))
        self.sing_box_path = StringVar(value=cfg.get("sing_box_path", DEFAULT_CONFIG["sing_box_path"]))
        self.check_updates = BooleanVar(value=bool(cfg.get("check_updates", DEFAULT_CONFIG["check_updates"])))
        self.theme_name = StringVar(value=cfg.get("theme", DEFAULT_CONFIG["theme"]) if cfg.get("theme", "") in THEMES else "dark")
        self.autostart = BooleanVar(
            value=bool(cfg.get("autostart", cfg.get("autostart_windows", DEFAULT_CONFIG["autostart"])))
        )

        self.language = StringVar(value=initial_language)
        self.theme_button_text = StringVar()
        self.language_button_text = StringVar()

        self.status = StringVar(value=self.tr("status_stopped"))
        self.telegram_status = StringVar(value=self.tr("status_waiting_start"))
        self.active_status = StringVar(value="0")
        self.traffic_status = StringVar(value="↑ 0B   ↓ 0B")
        self.errors_status = StringVar(value="0")
        self.quick_settings = StringVar(value="")
        self.full_secret = StringVar(value="")
        self.toggle_text = StringVar(value=self.tr("toggle_on"))

        self.update_status = StringVar(value=self.tr("update_status_idle"))
        self._update_status_key = "update_status_idle"
        self._update_status_kwargs: dict = {}
        self._latest_release_url = ""

        self.theme = THEMES.get(self.theme_name.get(), THEMES["dark"])
        self.update_language_controls()

        self.create_widgets()
        self.apply_theme()
        self.refresh_summary()
        self.setup_tray_icon()
        self.after(150, self.drain_logs)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(1500, self.check_updates_on_startup)

        for var in (
            self.app_mode, self.listen_host, self.listen_port, self.secret, self.secret_mode,
            self.fake_tls_domain, self.route_mode, self.cf_domain, self.domain_style,
            self.upstream_proxy_uri, self.local_proxy_username, self.local_proxy_password, self.sing_box_path,
        ):
            var.trace_add("write", lambda *_: self.refresh_summary())
        self.pin_telegram_ip.trace_add("write", lambda *_: self.refresh_summary())
        self.direct_fallback.trace_add("write", lambda *_: self.refresh_summary())
        self.language.trace_add("write", lambda *_: self.update_language_controls())

    def acquire_single_instance_lock(self) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)

            sock.bind((INSTANCE_LOCK_HOST, INSTANCE_LOCK_PORT))
            sock.listen(1)

        except OSError:
            try:
                sock.close()
            except Exception:
                pass
            return False

        self._instance_socket = sock
        return True


    def release_single_instance_lock(self) -> None:
        try:
            if self._instance_socket is not None:
                self._instance_socket.close()
        except Exception:
            pass
        finally:
            self._instance_socket = None

    def ensure_unix_autostart_script(self) -> Path:
        path = UNIX_AUTOSTART_SCRIPT

        if not path.exists():
            content = '''#!/usr/bin/env bash
    set -e

    cd "$(dirname "$0")"

    VENV_DIR=".venv"

    find_python() {
    if command -v python3 >/dev/null 2>&1; then
        echo "python3"
        return
    fi

    if command -v python >/dev/null 2>&1; then
        echo "python"
        return
    fi

    echo ""
    }

    PYTHON_CMD="$(find_python)"

    if [ -z "$PYTHON_CMD" ]; then
    exit 1
    fi

    if [ ! -f "$VENV_DIR/bin/python" ]; then
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    fi

    "$VENV_DIR/bin/python" -m pip install -r requirements.txt >/dev/null 2>&1
    "$VENV_DIR/bin/python" -m tunnelgram.gui
    '''
            path.write_text(content, encoding="utf-8")

        try:
            mode = path.stat().st_mode
            path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception:
            pass

        return path
    
    def set_linux_autostart(self, enabled: bool) -> None:
        if enabled:
            LINUX_AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)

            if is_frozen_app():
                executable = str(Path(sys.executable).resolve())
                escaped = executable.replace("\\", "\\\\").replace('"', '\\"')
                exec_value = f'"{escaped}"'
            else:
                exec_value = str(self.ensure_unix_autostart_script())

            content = f"""[Desktop Entry]
    Type=Application
    Name=tunnelgram
    Comment=Start tunnelgram on login
    Exec={exec_value}
    Terminal=false
    X-GNOME-Autostart-enabled=true
    """
            LINUX_DESKTOP_FILE.write_text(content, encoding="utf-8")
            return

        try:
            LINUX_DESKTOP_FILE.unlink()
        except FileNotFoundError:
            pass


    def is_linux_autostart_enabled(self) -> bool:
        return LINUX_DESKTOP_FILE.exists()
    
    def set_macos_autostart(self, enabled: bool) -> None:
        if enabled:
            MACOS_LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)

            if is_frozen_app():
                executable = Path(sys.executable).resolve()
                program_arguments = [str(executable)]
                working_directory = str(executable.parent)
            else:
                script = self.ensure_unix_autostart_script()
                program_arguments = ["/bin/bash", str(script)]
                working_directory = str(PROJECT_ROOT)

            plist_data = {
                "Label": "com.tunnelgram.app",
                "ProgramArguments": program_arguments,
                "RunAtLoad": True,
                "WorkingDirectory": working_directory,
                "StandardOutPath": "/tmp/tunnelgram.out.log",
                "StandardErrorPath": "/tmp/tunnelgram.err.log",
            }

            with MACOS_PLIST_FILE.open("wb") as f:
                plistlib.dump(plist_data, f)

            return

        try:
            MACOS_PLIST_FILE.unlink()
        except FileNotFoundError:
            pass


    def is_macos_autostart_enabled(self) -> bool:
        return MACOS_PLIST_FILE.exists()

    # ── config ─────────────────────────────────────────────────────────────
    def load_config(self) -> dict:
        paths = [CONFIG_PATH]
        old = old_config_path()
        if old != CONFIG_PATH:
            paths.append(old)
        for path in paths:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {**DEFAULT_CONFIG, **data}
            except Exception:
                pass
        return dict(DEFAULT_CONFIG)

    def current_config(self) -> dict:
        return {
            "app_mode": self.app_mode.get().strip() or "mtproto",
            "listen_host": self.listen_host.get().strip() or DEFAULT_CONFIG["listen_host"],
            "listen_port": self.listen_port.get().strip() or DEFAULT_CONFIG["listen_port"],
            "secret": self.secret.get().strip(),
            "secret_mode": self.secret_mode.get().strip() or "dd",
            "fake_tls_domain": self.fake_tls_domain.get().strip().lower(),
            "route_mode": self.route_mode.get().strip() or "telegram",
            "cf_domain": self.cf_domain.get().strip().lower(),
            "pin_telegram_ip": bool(self.pin_telegram_ip.get()),
            "domain_style": self.domain_style.get().strip() or "kws",
            "direct_fallback": bool(self.direct_fallback.get()),
            "upstream_proxy_uri": self.upstream_proxy_uri.get().strip(),
            "local_proxy_username": self.local_proxy_username.get(),
            "local_proxy_password": self.local_proxy_password.get(),
            "sing_box_path": self.sing_box_path.get().strip(),
            "check_updates": bool(self.check_updates.get()),
            "theme": self.theme_name.get(),
            "language": self.language.get() if self.language.get() in LANGUAGES else DEFAULT_CONFIG["language"],
            "autostart": bool(self.autostart.get()),
        }

    def save_config(self, silent: bool = False) -> None:
        self.validate_fields()
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

        cfg = self.current_config()
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        if os.name != "nt":
            try:
                CONFIG_PATH.chmod(0o600)
            except OSError:
                pass
        self._current_cfg = cfg

        self.sync_system_autostart()

        self.refresh_summary()
        if not silent:
            self.log(self.tr("settings_saved"), "ok")
            self.log(
                self.tr(
                    "autostart_system",
                    state=self.tr("enabled" if self.autostart.get() else "disabled"),
                ),
                "ok" if self.autostart.get() else "muted",
            )

    def ensure_hidden_launcher(self) -> Path:
        path = PROJECT_ROOT / "run_hidden.vbs"

        if path.exists():
            return path

        content = '''Set WshShell = CreateObject("WScript.Shell")
    Set FSO = CreateObject("Scripting.FileSystemObject")
    WshShell.CurrentDirectory = FSO.GetParentFolderName(WScript.ScriptFullName)
    WshShell.Run """.venv\\Scripts\\pythonw.exe"" -m tunnelgram.gui", 0, False
    '''

        path.write_text(content, encoding="utf-8")
        return path


    def windows_autostart_command(self) -> str:
        if is_frozen_app():
            return f'"{Path(sys.executable).resolve()}"'

        launcher = self.ensure_hidden_launcher()
        return f'wscript.exe //B //Nologo "{launcher}"'


    def set_windows_autostart(self, enabled: bool) -> None:
        if os.name != "nt":
            return

        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            AUTOSTART_RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key,
                    AUTOSTART_REG_NAME,
                    0,
                    winreg.REG_SZ,
                    self.windows_autostart_command(),
                )
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_REG_NAME)
                except FileNotFoundError:
                    pass


    def is_windows_autostart_enabled(self) -> bool:
        if os.name != "nt":
            return False

        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                AUTOSTART_RUN_KEY,
                0,
                winreg.KEY_READ,
            ) as key:
                value, _ = winreg.QueryValueEx(key, AUTOSTART_REG_NAME)
                return bool(value)
        except FileNotFoundError:
            return False
        except OSError:
            return False


    def sync_windows_autostart(self) -> None:
        if os.name != "nt":
            return

        self.set_windows_autostart(bool(self.autostart.get()))

    def sync_system_autostart(self) -> None:
        enabled = bool(self.autostart.get())

        if os.name == "nt":
            self.set_windows_autostart(enabled)
            return

        if sys.platform == "darwin":
            self.set_macos_autostart(enabled)
            return

        if sys.platform.startswith("linux"):
            self.set_linux_autostart(enabled)
            return

    def setup_window_icon(self) -> None:
        try:
            if os.name == "nt" and ICON_ICO.exists():
                self.iconbitmap(default=str(ICON_ICO))
                return
        except Exception:
            pass

        try:
            if ICON_PNG.exists():
                img = tk.PhotoImage(file=str(ICON_PNG))
                self.iconphoto(True, img)
                self._window_icon_ref = img
        except Exception:
            pass

    # ── UI helpers ─────────────────────────────────────────────────────────

    # ── i18n ────────────────────────────────────────────────────────────────
    def tr(self, key: str, **kwargs) -> str:
        language = self.language.get() if hasattr(self, "language") else DEFAULT_CONFIG["language"]
        return tr_text(key, language, **kwargs)


    def update_language_controls(self) -> None:
        if hasattr(self, "theme_button_text"):
            self.theme_button_text.set(self.tr("theme_button"))

        if hasattr(self, "language_button_text"):
            self.language_button_text.set("RU" if self.language.get() == "en" else "EN")


    def retranslate_current_state(self) -> None:
        status_keys = [
            "status_stopped",
            "status_waiting_start",
            "status_waiting_telegram",
            "status_running",
            "status_connected",
            "status_secret_rejected",
            "status_network_problem",
            "status_wss_available",
            "status_profile_valid",
            "status_checking_profile",
            "status_wss_not_found",
            "status_check_error",
            "status_no_connections",
            "status_checking_wss",
        ]

        def translate_var(var: StringVar, keys: list[str]) -> None:
            current = var.get()

            for key in keys:
                values = {translations.get(key) for translations in TRANSLATIONS.values()}
                if current in values:
                    var.set(self.tr(key))
                    return

        translate_var(self.status, status_keys)
        translate_var(self.telegram_status, status_keys)
        translate_var(self.toggle_text, ["toggle_on", "toggle_off"])

        if hasattr(self, "_update_status_key"):
            self.set_update_status(self._update_status_key, **self._update_status_kwargs)


    def toggle_language(self) -> None:
        old_log_content = ""

        try:
            if hasattr(self, "log_text") and self.log_text.winfo_exists():
                old_log_content = self.log_text.get("1.0", "end-1c")
        except Exception:
            old_log_content = ""

        self.language.set("ru" if self.language.get() == "en" else "en")
        self.update_language_controls()
        self.retranslate_current_state()
        self.refresh_summary()
        self.set_update_status(self._update_status_key, **self._update_status_kwargs)

        try:
            if self._settings_win and self._settings_win.winfo_exists():
                self._settings_win.destroy()
        except Exception:
            pass

        self._settings_win = None

        try:
            if hasattr(self, "root_frame") and self.root_frame.winfo_exists():
                self.root_frame.destroy()
        except Exception:
            pass

        self._theme_widgets.clear()
        self._buttons.clear()
        self._cards.clear()
        self.status_value_labels = []
        self.status_title_labels = []

        self.create_widgets()
        self.apply_theme()
        self.refresh_summary()

        if old_log_content:
            try:
                self.log_text.delete("1.0", END)
                self.log_text.insert(END, old_log_content.rstrip() + "\n")
                self.log_text.see(END)
            except Exception:
                pass

        self.log(self.tr("language_switched"), "ok")

        try:
            self.save_config(silent=True)
        except Exception:
            pass

    def watch(self, widget: tk.Widget, bg_key: str, fg_key: str | None = None) -> tk.Widget:
        self._theme_widgets.append((widget, bg_key, fg_key))
        return widget

    def make_label(self, parent: tk.Widget, text: str = "", *, textvariable=None, role="text", size=10, weight="normal", bg="bg", **kw) -> tk.Label:
        label = tk.Label(
            parent,
            text=text,
            textvariable=textvariable,
            font=("Segoe UI", size, weight),
            anchor=kw.pop("anchor", "w"),
            justify=kw.pop("justify", "left"),
            **kw,
        )
        return self.watch(label, bg, role)

    def make_button(
        self,
        parent: tk.Widget,
        text: str = "",
        command=None,
        *,
        textvariable=None,
        kind="secondary",
        width=None,
        height=None,
        compact: bool = False,
    ) -> tk.Button:
        btn = tk.Button(
            parent,
            text=text,
            textvariable=textvariable,
            command=command,
            font=("Segoe UI Symbol" if text in {"↻", "⟳", "↺"} else "Segoe UI", 10, "bold" if kind in {"primary", "danger"} else "normal"),
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=10 if compact else 16,
            pady=6 if compact else 9,
            width=width or 0,
            height=height or 0,
            highlightthickness=0,
        )
        self._buttons.append((btn, kind))
        return btn

    def make_entry(self, parent: tk.Widget, variable: StringVar, *, readonly=False) -> tk.Entry:
        entry = tk.Entry(
            parent,
            textvariable=variable,
            relief="flat",
            bd=0,
            font=("Segoe UI", 10),
            insertwidth=1,
            readonlybackground=THEMES[self.theme_name.get()].get("entry", "#ffffff"),
            state="readonly" if readonly else "normal",
        )
        return self.watch(entry, "entry", "text")
    
    def split_label_hint(self, text: str) -> tuple[str, str]:
        m = re.fullmatch(r"\s*(.*?)\s*\((.*?)\)\s*", text)
        if not m:
            return text, ""
        return m.group(1).strip(), m.group(2).strip()


    def make_caption(self, parent: tk.Widget, text: str, *, bg: str = "card") -> tk.Frame:
        main, hint = self.split_label_hint(text)

        box = tk.Frame(parent, bd=0)
        self.watch(box, bg)

        row = tk.Frame(box, bd=0)
        self.watch(row, bg)
        row.pack(anchor="w", fill="x")

        self.make_label(
            row,
            main,
            role="muted",
            size=9,
            weight="bold",
            bg=bg,
        ).pack(side="left", anchor="w")

        if hint:
            self.make_label(
                row,
                f"({hint})",
                role="muted",
                size=8,
                bg=bg,
            ).pack(side="left", anchor="w", padx=(6, 0))

        return box

    def make_section(self, parent: tk.Widget) -> tk.Frame:
        frame = tk.Frame(parent, bd=0, highlightthickness=1)
        self.watch(frame, "card")
        self._cards.append(frame)
        return frame

    # ── UI ─────────────────────────────────────────────────────────────────
    def create_widgets(self) -> None:
        self.root_frame = tk.Frame(self, bd=0)
        self.watch(self.root_frame, "bg")
        self.root_frame.pack(fill="both", expand=True, padx=24, pady=22)
        self.root_frame.columnconfigure(0, weight=1)
        self.root_frame.rowconfigure(3, weight=1)

        self.create_header()
        self.create_status_cards()
        self.create_control_card()
        self.create_log_card()

    def create_header(self) -> None:
        header = tk.Frame(self.root_frame, bd=0)
        self.watch(header, "bg")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        left = tk.Frame(header, bd=0)
        self.watch(left, "bg")
        left.grid(row=0, column=0, sticky="w")
        self.make_label(left, "tunnelgram", role="text", size=28, weight="bold", bg="bg").pack(anchor="w")

        right = tk.Frame(header, bd=0)
        self.watch(right, "bg")
        right.grid(row=0, column=1, sticky="e")
        self.language_btn = self.make_button(
            right,
            textvariable=self.language_button_text,
            command=self.toggle_language,
            kind="secondary",
            width=6,
        )
        self.language_btn.pack(side="right", anchor="e", padx=(10, 0))

        self.theme_btn = self.make_button(
            right,
            textvariable=self.theme_button_text,
            command=self.toggle_theme,
            kind="secondary",
            width=10,
        )
        self.theme_btn.pack(side="right", anchor="e")

    def create_status_cards(self) -> None:
        area = tk.Frame(self.root_frame, bd=0)
        self.watch(area, "bg")
        area.grid(row=1, column=0, sticky="ew", pady=(30, 14))

        cards = [
            (0, self.tr("proxy"), self.status),
            (1, self.tr("telegram"), self.telegram_status),
            (2, self.tr("traffic"), self.traffic_status),
        ]

        for i in range(len(cards)):
            area.columnconfigure(i, weight=1, uniform="status")

        self.status_value_labels: list[tk.Label] = []
        self.status_title_labels: list[tk.Label] = []

        for col, title, var in cards:
            self.make_status_card(area, col, title, var)

    def make_status_card(self, parent: tk.Frame, col: int, title: str, var: StringVar) -> None:
        card = self.make_section(parent)
        card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 10, 0), ipady=2)
        card.columnconfigure(0, weight=1)
        label = self.make_label(card, title, role="muted", size=9, weight="bold", bg="card")
        label.grid(row=0, column=0, sticky="w", padx=18, pady=(14, 2))
        value = self.make_label(card, textvariable=var, role="text", size=15, weight="bold", bg="card")
        value.grid(row=1, column=0, sticky="w", padx=18, pady=(4, 15))
        self.status_title_labels.append(label)
        self.status_value_labels.append(value)

    def create_control_card(self) -> None:
        card = self.make_section(self.root_frame)
        card.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        card.columnconfigure(0, weight=0)
        card.columnconfigure(1, weight=1)
        card.columnconfigure(2, weight=0)

        self.toggle_btn = self.make_button(card, textvariable=self.toggle_text, command=self.toggle_proxy, kind="primary", width=14, height=1)
        self.toggle_btn.grid(row=0, column=0, rowspan=2, sticky="w", padx=18, pady=18)

        actions = tk.Frame(card, bd=0)
        self.watch(actions, "card")
        actions.grid(row=0, column=2, rowspan=2, sticky="e", padx=(0, 18), pady=18)
        for i in range(3):
            actions.columnconfigure(i, weight=1)
        self.make_button(actions, text="Telegram", command=self.open_tg_link, kind="secondary", width=8).grid(row=0, column=0, padx=(0, 10), ipady=2)
        self.make_button(actions, text=self.tr("link"), command=self.copy_tg_link, kind="secondary", width=6).grid(row=0, column=1, padx=(0, 10), ipady=2)
        self.make_button(actions, text=self.tr("settings"), command=self.open_settings, kind="secondary", width=10).grid(row=0, column=2, ipady=2)

    def create_log_card(self) -> None:
        card = self.make_section(self.root_frame)
        card.grid(row=3, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)

        head = tk.Frame(card, bd=0)
        self.watch(head, "card")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 10))
        head.columnconfigure(1, weight=1)
        self.make_label(head, self.tr("logs"), role="text", size=13, weight="bold", bg="card").grid(row=0, column=0, sticky="w")

        buttons = tk.Frame(head, bd=0)
        self.watch(buttons, "card")
        buttons.grid(row=0, column=2, sticky="e")
        if pystray is not None:
            self.make_button(buttons, text=self.tr("minimize_to_tray"), command=self.hide_to_tray, kind="secondary", width=12).pack(side="left", padx=(0, 10))
        self.make_button(buttons, text=self.tr("check_connection"), command=self.check_wss, kind="secondary", width=18).pack(side="left", padx=(0, 10))
        self.make_button(
            buttons,
            text=self.tr("export"),
            command=self.export_logs,
            kind="secondary",
            width=10,
        ).pack(side="left", padx=(0, 8))
        self.make_button(buttons, text=self.tr("clear_logs"), command=self.clear_logs, kind="secondary", width=10).pack(side="left")

        log_wrap = tk.Frame(card, bd=0)
        self.watch(log_wrap, "card")
        log_wrap.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        log_wrap.columnconfigure(0, weight=1)
        log_wrap.rowconfigure(0, weight=1)
        self.log_text = ScrolledText(log_wrap, height=12, wrap="word", borderwidth=0, relief="flat")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.tag_config("ok", foreground="#86efac")
        self.log_text.tag_config("warn", foreground="#fde68a")
        self.log_text.tag_config("err", foreground="#fca5a5")
        self.log_text.tag_config("muted", foreground="#a8a29e")
        self.log(self.tr("ready_log"), "ok")

    def open_settings(self) -> None:
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.lift()
            self._settings_win.focus_force()
            return

        win = Toplevel(self)
        self._settings_win = win
        win.title(self.tr("settings_window_title"))
        win.geometry("860x650")
        win.minsize(860, 650)
        win.transient(self)
        win.columnconfigure(0, weight=1)
        win.rowconfigure(0, weight=1)

        frame = tk.Frame(win, bd=0)
        self.watch(frame, "bg")
        frame.grid(row=0, column=0, sticky="nsew", padx=24, pady=22)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        self.make_label(frame, self.tr("settings"), role="text", size=20, weight="bold", bg="bg").grid(row=0, column=0, sticky="w")

        top_actions = tk.Frame(frame, bd=0)
        self.watch(top_actions, "bg")
        top_actions.grid(row=1, column=0, sticky="ew", pady=(12, 16))

        self.make_button(
            top_actions,
            text=self.tr("about"),
            command=self.open_about_window,
            kind="secondary",
            width=14,
        ).pack(side="left", padx=(0, 10))

        self.make_button(
            top_actions,
            text=self.tr("open_config_folder"),
            command=self.open_config_folder,
            kind="secondary",
            width=18,
        ).pack(side="left", padx=(0, 10))

        self.make_button(
            top_actions,
            text=self.tr("reset_settings"),
            command=self.reset_settings,
            kind="danger",
            width=16,
        ).pack(side="left")

        body = tk.Frame(frame, bd=0)
        self.watch(body, "bg")
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1, uniform="settings_columns")
        body.columnconfigure(1, weight=1, uniform="settings_columns")

        basic_card = self.make_section(body)
        basic_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        basic_card.grid_propagate(False)
        basic_card.configure(height=680)

        basic_card.rowconfigure(0, weight=1)
        basic_card.columnconfigure(0, weight=1)

        basic_canvas = tk.Canvas(
            basic_card,
            bd=0,
            highlightthickness=0,
            relief="flat",
            bg=self.theme["card"],
        )
        basic_scrollbar = tk.Scrollbar(
            basic_card,
            orient="vertical",
            command=basic_canvas.yview,
        )
        basic_canvas.configure(yscrollcommand=basic_scrollbar.set)

        basic_canvas.grid(row=0, column=0, sticky="nsew")
        basic_scrollbar.grid(row=0, column=1, sticky="ns")

        basic = tk.Frame(basic_canvas, bd=0, bg=self.theme["card"])
        basic_window = basic_canvas.create_window((0, 0), window=basic, anchor="nw")

        self.watch(basic, "card")
        self.basic_canvas = basic_canvas

        def _basic_on_frame_configure(event=None):
            basic_canvas.configure(scrollregion=basic_canvas.bbox("all"))

        def _basic_on_canvas_configure(event):
            basic_canvas.itemconfigure(basic_window, width=event.width)

        basic.bind("<Configure>", _basic_on_frame_configure)
        basic_canvas.bind("<Configure>", _basic_on_canvas_configure)

        def _basic_on_mousewheel(event):
            if event.delta:
                basic_canvas.yview_scroll(int(-event.delta / 120), "units")
            elif getattr(event, "num", None) == 4:
                basic_canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                basic_canvas.yview_scroll(1, "units")

        for widget in (basic_canvas, basic):
            widget.bind("<MouseWheel>", _basic_on_mousewheel)
            widget.bind("<Button-4>", _basic_on_mousewheel)
            widget.bind("<Button-5>", _basic_on_mousewheel)

        route_card = self.make_section(body)
        route_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        route_card.grid_propagate(False)
        route_card.configure(height=680)

        route_card.rowconfigure(0, weight=1)
        route_card.columnconfigure(0, weight=1)

        route_canvas = tk.Canvas(
            route_card,
            bd=0,
            highlightthickness=0,
            relief="flat",
            bg=self.theme["card"],
        )
        route_scrollbar = tk.Scrollbar(
            route_card,
            orient="vertical",
            command=route_canvas.yview,
        )
        route_canvas.configure(yscrollcommand=route_scrollbar.set)

        route_canvas.grid(row=0, column=0, sticky="nsew")
        route_scrollbar.grid(row=0, column=1, sticky="ns")

        route = tk.Frame(route_canvas, bd=0, bg=self.theme["card"])
        route_window = route_canvas.create_window((0, 0), window=route, anchor="nw")

        self.watch(route, "card")
        self.route_canvas = route_canvas

        def _route_on_frame_configure(event=None):
            route_canvas.configure(scrollregion=route_canvas.bbox("all"))

        def _route_on_canvas_configure(event):
            route_canvas.itemconfigure(route_window, width=event.width)

        route.bind("<Configure>", _route_on_frame_configure)
        route_canvas.bind("<Configure>", _route_on_canvas_configure)

        def _route_on_mousewheel(event):
            if event.delta:
                route_canvas.yview_scroll(int(-event.delta / 120), "units")
            elif getattr(event, "num", None) == 4:
                route_canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                route_canvas.yview_scroll(1, "units")

        for widget in (route_canvas, route):
            widget.bind("<MouseWheel>", _route_on_mousewheel)
            widget.bind("<Button-4>", _route_on_mousewheel)
            widget.bind("<Button-5>", _route_on_mousewheel)

        def _route_bind_mousewheel(event=None):
            route_canvas.bind_all("<MouseWheel>", _route_on_mousewheel)
            route_canvas.bind_all("<Button-4>", _route_on_mousewheel)
            route_canvas.bind_all("<Button-5>", _route_on_mousewheel)

        def _route_unbind_mousewheel(event=None):
            route_canvas.unbind_all("<MouseWheel>")
            route_canvas.unbind_all("<Button-4>")
            route_canvas.unbind_all("<Button-5>")

        route_card.bind("<Enter>", _route_bind_mousewheel)
        route_card.bind("<Leave>", _route_unbind_mousewheel)

        body.rowconfigure(0, weight=1)

        basic.columnconfigure(0, weight=1)
        basic.columnconfigure(1, weight=1)
        route.columnconfigure(0, weight=1)
        route.columnconfigure(1, weight=1)

        self.make_label(basic, self.tr("basic"), role="text", size=13, weight="bold", bg="card").grid(row=0, column=0, columnspan=3, sticky="w", padx=18, pady=(18, 10))

        app_mode_box = tk.Frame(basic, bd=0)
        self.watch(app_mode_box, "card")
        app_mode_box.grid(row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=(8, 10))
        self.make_caption(app_mode_box, self.tr("program_mode"), bg="card").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.add_radio(app_mode_box, self.tr("mode_mtproto"), self.app_mode, "mtproto").grid(row=1, column=0, sticky="w")
        self.add_radio(app_mode_box, self.tr("mode_local_proxy"), self.app_mode, "proxy").grid(row=2, column=0, sticky="w", pady=(6, 0))

        self.add_entry(basic, 2, self.tr("address"), self.listen_host)
        self.add_entry(basic, 3, self.tr("port"), self.listen_port)
        self.add_entry_with_button(
            basic,
            4,
            self.tr("secret_label"),
            self.secret,
            button_text="↻",
            button_command=self.generate_secret,
            button_kind="secondary",
            button_width=3,
        )

        secret_type_box = tk.Frame(basic, bd=0)
        self.watch(secret_type_box, "card")
        secret_type_box.grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(8, 10),
        )

        self.make_caption(
            secret_type_box,
            self.tr("secret_type_label"),
            bg="card",
        ).grid(
            row=0,
            column=0,
            sticky="w",
            pady=(0, 8),
        )

        mode_box = tk.Frame(secret_type_box, bd=0)
        self.watch(mode_box, "card")
        mode_box.grid(row=1, column=0, sticky="w")

        self.add_radio(mode_box, "Fake TLS", self.secret_mode, "ee").pack(side="left")
        self.add_radio(mode_box, "Classic", self.secret_mode, "dd").pack(side="left", padx=(18, 0))

        self.add_entry(basic, 7, "SNI", self.fake_tls_domain)
        self.add_entry(basic, 8, self.tr("upstream_proxy_uri"), self.upstream_proxy_uri)
        self.add_entry(basic, 9, self.tr("local_proxy_username"), self.local_proxy_username)
        self.add_entry(basic, 10, self.tr("local_proxy_password"), self.local_proxy_password)
        self.add_entry_with_button(
            basic,
            11,
            self.tr("sing_box_path"),
            self.sing_box_path,
            button_text=self.tr("browse"),
            button_command=self.select_sing_box_binary,
            button_kind="secondary",
            button_width=8,
        )
        proxy_hint = tk.Frame(basic, bd=0)
        self.watch(proxy_hint, "card")
        proxy_hint.grid(row=12, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 8))
        self.make_label(
            proxy_hint,
            self.tr("upstream_proxy_hint"),
            role="muted",
            size=8,
            bg="card",
            wraplength=330,
            justify="left",
        ).grid(row=0, column=0, sticky="w")

        autostart_box = tk.Frame(basic, bd=0)
        self.watch(autostart_box, "card")
        autostart_box.grid(
            row=13,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(8, 10),
        )
        autostart_box.columnconfigure(0, weight=1)

        self.add_check(
            autostart_box,
            self.tr("autostart_label"),
            self.autostart,
        ).grid(row=0, column=0, sticky="w")

        self.make_label(
            autostart_box,
            self.tr("autostart_hint"),
            role="muted",
            size=8,
            bg="card",
        ).grid(row=1, column=0, sticky="w", padx=(24, 0), pady=(2, 0))

        updates_box = tk.Frame(basic, bd=0)
        self.watch(updates_box, "card")
        updates_box.grid(
            row=14,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(8, 10),
        )
        updates_box.columnconfigure(0, weight=1)

        self.add_check(
            updates_box,
            self.tr("check_updates_label"),
            self.check_updates,
        ).grid(row=0, column=0, sticky="w")

        self.make_label(
            updates_box,
            self.tr("check_updates_hint"),
            role="muted",
            size=8,
            bg="card",
        ).grid(row=1, column=0, sticky="w", padx=(24, 0), pady=(2, 0))

        self.make_button(
            updates_box,
            text=self.tr("check_updates_now"),
            command=lambda: self.check_updates_now(manual=True),
            kind="secondary",
            width=18,
        ).grid(row=3, column=0, sticky="w", pady=(4, 8))

        self.make_label(
            updates_box,
            textvariable=self.update_status,
            role="muted",
            size=9,
            bg="card",
        ).grid(row=4, column=0, columnspan=2, sticky="w")

        self.make_label(route, self.tr("route"), role="text", size=13, weight="bold", bg="card").grid(row=0, column=0, columnspan=3, sticky="w", padx=18, pady=(18, 10))
        route_mode_box = tk.Frame(route, bd=0)
        self.watch(route_mode_box, "card")
        route_mode_box.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(8, 14),
        )
        route_mode_box.columnconfigure(0, weight=1)

        self.make_caption(
            route_mode_box,
            self.tr("mode_label"),
            bg="card",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        route_choices = tk.Frame(route_mode_box, bd=0)
        self.watch(route_choices, "card")
        route_choices.grid(row=1, column=0, sticky="w")

        self.add_radio(
            route_choices,
            "Direct WSS",
            self.route_mode,
            "telegram",
        ).grid(row=0, column=0, sticky="w")

        cf_box = tk.Frame(route_choices, bd=0)
        self.watch(cf_box, "card")
        cf_box.grid(row=1, column=0, sticky="w", pady=(8, 0))

        self.add_radio(
            cf_box,
            "Cloudflare DNS",
            self.route_mode,
            "cloudflare",
        ).grid(row=0, column=0, sticky="w")

        self.make_label(
            cf_box,
            self.tr("cf_hint"),
            role="muted",
            size=8,
            bg="card",
        ).grid(row=1, column=0, sticky="w", padx=(24, 0), pady=(2, 0))

        self.add_entry(route, 2, self.tr("cf_suffix"), self.cf_domain)
        domain_outer = tk.Frame(route, bd=0)
        self.watch(domain_outer, "card")
        domain_outer.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(8, 10),
        )
        domain_outer.columnconfigure(0, weight=1)

        self.make_caption(
            domain_outer,
            self.tr("domains_label"),
            bg="card",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        domain_box = tk.Frame(domain_outer, bd=0)
        self.watch(domain_box, "card")
        domain_box.grid(row=1, column=0, sticky="w")

        self.add_radio(
            domain_box,
            "kws",
            self.domain_style,
            "kws",
        ).grid(row=0, column=0, sticky="w")

        self.add_radio(
            domain_box,
            self.tr("dc_names"),
            self.domain_style,
            "names",
        ).grid(row=0, column=1, sticky="w", padx=(18, 0))

        advanced_box = tk.Frame(route, bd=0)
        self.watch(advanced_box, "card")
        advanced_box.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(12, 10),
        )
        advanced_box.columnconfigure(0, weight=1)

        self.add_check(
            advanced_box,
            self.tr("pin_ip_label"),
            self.pin_telegram_ip,
        ).grid(row=0, column=0, sticky="w")

        pin_hint_label = self.make_label(
            advanced_box,
            self.tr("pin_ip_hint"),
            role="muted",
            size=8,
            bg="card",
            wraplength=260,
            justify="left",
        )
        pin_hint_label.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(24, 12),
            pady=(2, 10),
        )

        self.add_check(
            advanced_box,
            self.tr("direct_fallback_label"),
            self.direct_fallback,
        ).grid(row=2, column=0, sticky="w")

        direct_hint_label = self.make_label(
            advanced_box,
            self.tr("direct_fallback_hint"),
            role="muted",
            size=8,
            bg="card",
            wraplength=260,
            justify="left",
        )
        direct_hint_label.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=(24, 12),
            pady=(2, 0),
        )

        def _advanced_hints_wrap(event=None):
            try:
                width = max(180, advanced_box.winfo_width() - 56)
                pin_hint_label.configure(wraplength=width)
                direct_hint_label.configure(wraplength=width)
            except Exception:
                pass

        advanced_box.bind("<Configure>", _advanced_hints_wrap)

        bottom = tk.Frame(frame, bd=0)
        self.watch(bottom, "bg")
        bottom.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        self.make_button(bottom, text=self.tr("save"), command=lambda: self.save_settings_window(win), kind="primary", width=14).pack(side="right")
        self.make_button(bottom, text=self.tr("close"), command=win.destroy, kind="secondary", width=12).pack(side="right", padx=(0, 10))

        self.apply_theme()
        self.refresh_summary()

    def add_entry(self, parent: tk.Frame, row: int, label: str, variable: StringVar) -> None:
        box = tk.Frame(parent, bd=0)
        self.watch(box, "card")
        box.grid(row=row, column=0, columnspan=2, sticky="ew", padx=18, pady=(8, 10))
        box.columnconfigure(0, weight=1)

        self.make_caption(box, label, bg="card").grid(
            row=0,
            column=0,
            sticky="w",
            pady=(0, 7),
        )

        entry = self.make_entry(box, variable)
        entry.grid(row=1, column=0, sticky="ew", ipady=8)

    def add_entry_with_button(
        self,
        parent: tk.Frame,
        row: int,
        label: str,
        variable: StringVar,
        *,
        button_text: str,
        button_command,
        button_kind: str = "secondary",
        button_width: int = 3,
    ) -> None:
        box = tk.Frame(parent, bd=0)
        self.watch(box, "card")
        box.grid(row=row, column=0, columnspan=2, sticky="ew", padx=18, pady=(8, 10))
        box.columnconfigure(0, weight=1)

        self.make_caption(box, label, bg="card").grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 7),
        )

        entry = self.make_entry(box, variable)
        entry.grid(row=1, column=0, sticky="ew", ipady=8)

        btn = self.make_button(
            box,
            text=button_text,
            command=button_command,
            kind=button_kind,
            width=button_width,
            compact=True,
        )
        btn.grid(row=1, column=1, sticky="e", padx=(10, 0), ipady=1)

    def add_radio(self, parent: tk.Widget, text: str, variable: StringVar, value: str) -> tk.Radiobutton:
        rb = tk.Radiobutton(
            parent,
            text=text,
            variable=variable,
            value=value,
            font=("Segoe UI", 10),
            bd=0,
            highlightthickness=0,
            activebackground=THEMES[self.theme_name.get()]["card"],
            selectcolor=THEMES[self.theme_name.get()]["surface2"],
            cursor="hand2",
        )
        self.watch(rb, "card", "text")
        return rb

    def add_check(self, parent: tk.Widget, text: str, variable: BooleanVar) -> tk.Checkbutton:
        cb = tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            font=("Segoe UI", 10),
            bd=0,
            highlightthickness=0,
            activebackground=THEMES[self.theme_name.get()]["card"],
            selectcolor=THEMES[self.theme_name.get()]["surface2"],
            cursor="hand2",
        )
        self.watch(cb, "card", "text")
        return cb

    def save_settings_window(self, win: Toplevel) -> None:
        try:
            self.save_config()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=win)
            return
        win.destroy()

    def apply_theme(self) -> None:
        self.theme = THEMES.get(self.theme_name.get(), THEMES["dark"])
        t = self.theme
        self.configure(bg=t["bg"])
        for widget, bg_key, fg_key in list(self._theme_widgets):
            try:
                cfg = {"bg": t[bg_key]}
                if fg_key:
                    cfg["fg"] = t[fg_key]
                if isinstance(widget, (tk.Entry,)):
                    cfg["insertbackground"] = t["text"]
                    cfg["highlightbackground"] = t["border"]
                    cfg["highlightcolor"] = t["primary"]
                    cfg["readonlybackground"] = t["entry"]
                    cfg["disabledforeground"] = t["muted"]
                if isinstance(widget, (tk.Radiobutton, tk.Checkbutton)):
                    cfg["activebackground"] = t[bg_key]
                    cfg["activeforeground"] = t[fg_key or "text"]
                    cfg["selectcolor"] = t["surface2"]
                widget.configure(**cfg)
            except Exception:
                pass
        for frame in self._cards:
            try:
                frame.configure(highlightbackground=t["border"], highlightcolor=t["border"])
            except Exception:
                pass
        for btn, kind in list(self._buttons):
            self.style_button(btn, kind)
        if hasattr(self, "log_text"):
            self.log_text.configure(
                background=t["log_bg"],
                foreground=t["log_fg"],
                insertbackground=t["log_fg"],
                selectbackground=t["primary"],
                font=("Consolas", 10),
                padx=14,
                pady=12,
            )

        for canvas_name in ("basic_canvas", "route_canvas"):
            if hasattr(self, canvas_name):
                try:
                    canvas = getattr(self, canvas_name)
                    if canvas.winfo_exists():
                        canvas.configure(bg=t["card"])
                except Exception:
                    pass

        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.configure(bg=t["bg"])

    def style_button(self, btn: tk.Button, kind: str) -> None:
        t = self.theme
        if kind == "primary":
            bg, fg, active = t["primary"], t["primary_fg"], t["primary_hover"]
        elif kind == "danger":
            bg, fg, active = t["danger"], t["danger_fg"], t["danger_hover"]
        else:
            bg, fg, active = t["secondary"], t["secondary_fg"], t["secondary_hover"]
        try:
            btn.configure(
                bg=bg,
                fg=fg,
                activebackground=active,
                activeforeground=fg,
                disabledforeground=t["muted"],
            )
        except Exception:
            pass

    def toggle_theme(self) -> None:
        self.theme_name.set("light" if self.theme_name.get() == "dark" else "dark")
        self.apply_theme()
        self.update_language_controls()
        try:
            self.save_config(silent=True)
        except Exception:
            pass

    # ── state/logs ─────────────────────────────────────────────────────────
    def refresh_summary(self) -> None:
        if self.app_mode.get() == "proxy":
            self.full_secret.set("")
            profile = redact_proxy_uri(self.upstream_proxy_uri.get()) or self.tr("profile_required")
            self.quick_settings.set(
                f"{self.listen_host.get()}:{self.listen_port.get()}  ·  HTTP/SOCKS5  ·  {profile}"
            )
        else:
            try:
                full = self.current_full_secret()
            except Exception:
                full = ""
            self.full_secret.set(full)

            mode = "Fake TLS" if self.secret_mode.get() == "ee" else "Classic"
            route = "Direct WSS" if self.route_mode.get() == "telegram" else "Cloudflare DNS"
            style = "kws" if self.domain_style.get() == "kws" else "names"
            self.quick_settings.set(
                f"{self.listen_host.get()}:{self.listen_port.get()}  ·  {mode}  ·  {route}/{style}  ·  "
                f"Pin IP {fmt_bool(self.pin_telegram_ip.get(), self.language.get())}  ·  TCP fallback {fmt_bool(self.direct_fallback.get(), self.language.get())}"
            )
        running = bool(self.proc and self.proc.poll() is None)
        self.toggle_text.set(self.tr("toggle_off") if running else self.tr("toggle_on"))
        if hasattr(self, "toggle_btn"):
            # Blue when idle, red when running.
            kind = "danger" if running else "primary"
            for i, (btn, _current_kind) in enumerate(self._buttons):
                if btn is self.toggle_btn:
                    self._buttons[i] = (btn, kind)
                    break
            self.style_button(self.toggle_btn, kind)

    def log(self, text: str, tag: str | None = None) -> None:
        try:
            self.log_text.insert(END, text.rstrip() + "\n", tag or "")
            self.prune_logs_if_needed()
            self.log_text.see(END)
        except Exception:
            pass

    def clear_logs(self) -> None:
        self.log_text.delete("1.0", END)
        self._log_lines_since_prune = 0
        self.log(self.tr("logs_cleared"), "muted")

    def prune_logs_if_needed(self, force: bool = False) -> None:
        if not hasattr(self, "log_text"):
            return

        self._log_lines_since_prune += 1

        if not force and self._log_lines_since_prune < self._log_prune_every:
            return

        self._log_lines_since_prune = 0

        try:
            total_lines = int(self.log_text.index("end-1c").split(".")[0])
        except Exception:
            return

        extra_lines = total_lines - self._max_log_lines

        if extra_lines <= 0:
            return

        try:
            self.log_text.delete("1.0", f"{extra_lines + 1}.0")
        except Exception:
            pass
        
    def export_logs(self) -> None:
        try:
            content = self.log_text.get("1.0", "end-1c").strip()
        except Exception:
            content = ""

        if not content:
            messagebox.showinfo(APP_NAME, self.tr("logs_empty"))
            return

        from datetime import datetime

        default_name = f"tunnelgram_logs_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"

        path = filedialog.asksaveasfilename(
            title=self.tr("export_logs_title"),
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=[
                ("Text files", "*.txt"),
                ("Log files", "*.log"),
                ("All files", "*.*"),
            ],
        )

        if not path:
            return

        try:
            Path(path).write_text(content + "\n", encoding="utf-8")
        except Exception as exc:
            messagebox.showerror(APP_NAME, self.tr("save_logs_failed", error=exc))
            return

        self.log(self.tr("logs_exported", path=path), "ok")

    def clear_logs_on_exit(self) -> None:
        try:
            while True:
                self.log_queue.get_nowait()
        except queue.Empty:
            pass

        try:
            if hasattr(self, "log_text") and self.log_text.winfo_exists():
                self.log_text.delete("1.0", END)
        except Exception:
            pass

    def should_show_log_line(self, line: str) -> tuple[bool, str | None, str]:
        clean = line.rstrip()

        if self.is_wss_try_line(clean):
            return self.suppress_ws_noise()

        if self.is_short_wss_close_line(clean):
            return self.suppress_ws_noise()

        noisy = (
            "WSS connect failed" in clean
            or "WSS handshake failed" in clean
            or "WSS path failed" in clean
        )
        if noisy and self.telegram_status.get() == self.tr("status_connected"):
            return False, None, clean
        tag = None
        if "WARNING" in clean or "failed" in clean or "timeout" in clean.lower():
            tag = "warn"
        if "ERROR" in clean or "unexpected" in clean or "rejected" in clean:
            tag = "err"
        if "-> Telegram WSS" in clean or "listening" in clean or clean.startswith("stats:"):
            tag = "ok"
        return True, tag, clean
    
    def is_wss_try_line(self, line: str) -> bool:
        return "WSS try DC" in line


    def is_short_wss_close_line(self, line: str) -> bool:
        if "WSS closed:" not in line:
            return False

        m = re.search(r"\bin\s+([0-9.]+)s\b", line)
        if not m:
            return False

        try:
            duration = float(m.group(1))
        except ValueError:
            return False

        return duration < self._short_ws_close_seconds


    def suppress_ws_noise(self) -> tuple[bool, str | None, str]:
        self._suppressed_ws_noise += 1
        now = time.monotonic()

        if self._suppressed_ws_noise >= 25 and now - self._last_ws_noise_report >= 10:
            count = self._suppressed_ws_noise
            self._suppressed_ws_noise = 0
            self._last_ws_noise_report = now
            return True, "muted", self.tr("hidden_wss_events", count=count)

        return False, None, ""

    def parse_status_from_log(self, line: str) -> bool:
        stripped = line.strip()
        if stripped == "__STATUS_WSS_OK__":
            self.telegram_status.set(self.tr("status_wss_available"))
            return False
        if stripped == "__STATUS_WSS_DONE__":
            if self.telegram_status.get() == self.tr("status_checking_wss"):
                self.telegram_status.set(self.tr("status_wss_not_found"))
            return False
        if stripped == "__STATUS_WSS_FAIL__":
            self.telegram_status.set(self.tr("status_check_error"))
            return False
        if stripped == "__STATUS_PROXY_PROFILE_OK__":
            self.telegram_status.set(self.tr("status_profile_valid"))
            return False
        if stripped == "__STATUS_PROXY_PROFILE_FAIL__":
            self.telegram_status.set(self.tr("status_check_error"))
            return False

        lower = line.lower()
        if self.app_mode.get() == "proxy":
            if "started" in lower or "inbound/mixed" in lower or "mixed-in" in lower:
                self.status.set(self.tr("status_running"))
            if ("inbound/mixed" in lower or "mixed-in" in lower) and any(
                marker in lower for marker in ("connection", "accepted", "new connection")
            ):
                self.telegram_status.set(self.tr("status_connected"))
                try:
                    n = int(self.active_status.get())
                    self.active_status.set(str(max(1, n)))
                except ValueError:
                    self.active_status.set("1")
            if "error" in lower and "deprecated" not in lower:
                try:
                    self.errors_status.set(str(int(self.errors_status.get()) + 1))
                except ValueError:
                    self.errors_status.set("1")

        if "local proxy listening" in line:
            self.status.set(self.tr("status_running"))
            self.telegram_status.set(self.tr("status_waiting_telegram"))
        if "-> Telegram WSS" in line:
            self.telegram_status.set(self.tr("status_connected"))
            try:
                n = int(self.active_status.get())
                self.active_status.set(str(max(1, n)))
            except ValueError:
                self.active_status.set("1")
        if "rejected:" in line:
            self.telegram_status.set(self.tr("status_secret_rejected"))
        elif "WSS path failed" in line or "unexpected error" in line or " timeout" in line:
            if self.telegram_status.get() not in {self.tr("status_connected"), self.tr("status_wss_available")}:
                self.telegram_status.set(self.tr("status_network_problem"))
        m = re.search(r"stats: .*active=(\d+).*err=(\d+).*up=([^ ]+) down=([^\s]+)", line)
        if m:
            self.active_status.set(m.group(1))
            self.errors_status.set(m.group(2))
            self.traffic_status.set(f"↑ {m.group(3)}   ↓ {m.group(4)}")
            if int(m.group(1)) > 0:
                self.telegram_status.set(self.tr("status_connected"))
        if "[process exited]" in line:
            self.status.set(self.tr("status_stopped"))
            self.telegram_status.set(self.tr("status_no_connections"))
        return True

    def drain_logs(self) -> None:
        try:
            while True:
                line = self.log_queue.get_nowait()
                should_parse = self.parse_status_from_log(line)
                if should_parse:
                    show, tag, clean = self.should_show_log_line(line)
                    if show:
                        self.log(clean, tag)
        except queue.Empty:
            pass
        if self.proc and self.proc.poll() is not None:
            self.status.set(self.tr("status_stopped"))
            self.refresh_summary()
        self.after(150, self.drain_logs)

    # ── app helpers ─────────────────────────────────────────────────────────
    def open_url(self, url: str) -> None:
        try:
            webbrowser.open(url)
        except Exception:
            pass


    def copy_version(self) -> None:
        value = f"{APP_NAME} v{VERSION}"

        try:
            self.clipboard_clear()
            self.clipboard_append(value)
            self.log(self.tr("version_copied"), "ok")
        except Exception:
            pass


    def open_config_folder(self) -> None:
        folder = CONFIG_PATH.parent

        try:
            folder.mkdir(parents=True, exist_ok=True)
            folder = folder.resolve()

            if not folder.exists():
                raise FileNotFoundError(str(folder))

            if not folder.is_dir():
                raise NotADirectoryError(str(folder))

            if os.name == "nt":
                try:
                    subprocess.Popen(
                        ["explorer.exe", str(folder)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    self.log(self.tr("config_folder_opened"), "ok")
                    return
                except Exception:
                    os.startfile(str(folder))  # type: ignore[attr-defined]
                    self.log(self.tr("config_folder_opened"), "ok")
                    return

            if sys.platform == "darwin":
                subprocess.Popen(
                    ["open", str(folder)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.log(self.tr("config_folder_opened"), "ok")
                return

            candidates = []

            if shutil.which("xdg-open"):
                candidates.append(["xdg-open", str(folder)])

            if shutil.which("gio"):
                candidates.append(["gio", "open", str(folder)])

            for cmd in candidates:
                try:
                    subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    self.log(self.tr("config_folder_opened"), "ok")
                    return
                except Exception:
                    continue

            raise RuntimeError("No folder opener found")

        except Exception as exc:
            messagebox.showerror(
                APP_NAME,
                self.tr("config_folder_open_failed", error=exc),
            )

    def open_about_window(self) -> None:
        win = Toplevel(self)
        win.title(self.tr("about_title"))
        win.geometry("450x350")
        win.minsize(450, 350)
        win.resizable(False, False)
        win.transient(self)
        win.configure(bg=self.theme["bg"])
        win.columnconfigure(0, weight=1)
        win.rowconfigure(0, weight=1)

        frame = tk.Frame(win, bd=0, highlightthickness=0)
        self.watch(frame, "bg")
        frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        frame.columnconfigure(0, weight=1)

        self.make_label(
            frame,
            "tunnelgram",
            role="text",
            size=24,
            weight="bold",
            bg="bg",
        ).grid(row=0, column=0, sticky="w")

        self.make_label(
            frame,
            self.tr("about_version", version=VERSION),
            role="muted",
            size=10,
            bg="bg",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.make_label(
            frame,
            self.tr("about_description"),
            role="soft_text",
            size=10,
            bg="bg",
            wraplength=500,
            justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(16, 0))

        buttons = tk.Frame(frame, bd=0)
        self.watch(buttons, "bg")
        buttons.grid(row=4, column=0, sticky="ew", pady=(18, 0))

        buttons.columnconfigure(0, weight=1)

        self.make_button(
            buttons,
            text=self.tr("open_github"),
            command=lambda: self.open_url(GITHUB_REPO_URL),
            kind="secondary",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 10))

        self.make_button(
            buttons,
            text=self.tr("open_releases"),
            command=lambda: self.open_url(GITHUB_RELEASES_URL),
            kind="secondary",
        ).grid(row=1, column=0, sticky="ew", pady=(0, 10))

        bottom = tk.Frame(frame, bd=0)
        self.watch(bottom, "bg")
        bottom.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        bottom.columnconfigure(0, weight=1)

        self.make_button(
            bottom,
            text=self.tr("close"),
            command=win.destroy,
            kind="primary",
        ).grid(row=0, column=0, sticky="ew")

        self.apply_theme()

    def reset_settings(self) -> None:
        try:
            confirmed = messagebox.askyesno(
                self.tr("reset_settings_title"),
                self.tr("reset_settings_message"),
                parent=self._settings_win if self._settings_win and self._settings_win.winfo_exists() else self,
            )
        except Exception:
            confirmed = False

        if not confirmed:
            return

        try:
            if self.proc and self.proc.poll() is None:
                self.stop_proxy()
        except Exception:
            pass

        preserved_language = self.language.get() if hasattr(self, "language") else DEFAULT_CONFIG.get("language", "en")
        preserved_theme = self.theme_name.get() if hasattr(self, "theme_name") else DEFAULT_CONFIG.get("theme", "dark")
        preserved_check_updates = bool(self.check_updates.get()) if hasattr(self, "check_updates") else DEFAULT_CONFIG.get("check_updates", True)

        cfg = dict(DEFAULT_CONFIG)
        cfg["language"] = preserved_language
        cfg["theme"] = preserved_theme
        cfg["check_updates"] = preserved_check_updates
        cfg["autostart"] = False

        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(
                json.dumps(cfg, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            if os.name != "nt":
                try:
                    CONFIG_PATH.chmod(0o600)
                except OSError:
                    pass
        except Exception:
            pass

        self.app_mode.set(str(cfg["app_mode"]))
        self.listen_host.set(str(cfg["listen_host"]))
        self.listen_port.set(str(cfg["listen_port"]))
        self.secret.set(str(cfg["secret"]))
        self.secret_mode.set(str(cfg["secret_mode"]))
        self.fake_tls_domain.set(str(cfg["fake_tls_domain"]))
        self.route_mode.set(str(cfg["route_mode"]))
        self.cf_domain.set(str(cfg["cf_domain"]))
        self.pin_telegram_ip.set(bool(cfg["pin_telegram_ip"]))
        self.domain_style.set(str(cfg["domain_style"]))
        self.direct_fallback.set(bool(cfg["direct_fallback"]))
        self.upstream_proxy_uri.set(str(cfg["upstream_proxy_uri"]))
        self.local_proxy_username.set(str(cfg["local_proxy_username"]))
        self.local_proxy_password.set(str(cfg["local_proxy_password"]))
        self.sing_box_path.set(str(cfg["sing_box_path"]))
        self.autostart.set(bool(cfg["autostart"]))
        self.theme_name.set(str(cfg["theme"]))
        self.language.set(str(cfg["language"]))

        if hasattr(self, "check_updates"):
            self.check_updates.set(bool(cfg["check_updates"]))

        try:
            self.sync_system_autostart()
        except Exception:
            pass

        self.status.set(self.tr("status_stopped"))
        self.telegram_status.set(self.tr("status_no_connections"))
        self.active_status.set("0")
        self.traffic_status.set("↑ 0B   ↓ 0B")
        self.errors_status.set("0")

        self.apply_theme()
        self.update_language_controls()
        self.refresh_summary()

        try:
            if self._settings_win and self._settings_win.winfo_exists():
                self._settings_win.destroy()
                self._settings_win = None
                self.open_settings()
        except Exception:
            pass

        self.log(self.tr("settings_reset_done"), "ok")

    # ── updates ─────────────────────────────────────────────────────────────
    def set_update_status(self, key: str, **kwargs) -> None:
        self._update_status_key = key
        self._update_status_kwargs = dict(kwargs)

        try:
            self.update_status.set(self.tr(key, **kwargs))
        except Exception:
            pass


    def parse_version_tuple(self, value: str) -> tuple[int, ...]:
        value = str(value or "").strip().lower()
        value = value.removeprefix("v")
        value = value.split("-", 1)[0]

        parts = re.findall(r"\d+", value)

        if not parts:
            return (0,)

        return tuple(int(part) for part in parts)


    def is_newer_version(self, remote_version: str, local_version: str) -> bool:
        remote = self.parse_version_tuple(remote_version)
        local = self.parse_version_tuple(local_version)

        max_len = max(len(remote), len(local))
        remote = remote + (0,) * (max_len - len(remote))
        local = local + (0,) * (max_len - len(local))

        return remote > local


    def fetch_latest_release(self) -> dict:
        request = urllib.request.Request(
            GITHUB_LATEST_RELEASE_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"{APP_NAME}/{VERSION}",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                raw = response.read().decode("utf-8", errors="replace")

        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise UpdateCheckNotFoundError("release not found") from exc
            raise UpdateCheckNetworkError(str(exc)) from exc

        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise UpdateCheckNetworkError(str(exc)) from exc

        try:
            data = json.loads(raw)
        except Exception as exc:
            raise ValueError("invalid json") from exc

        if not isinstance(data, dict):
            raise ValueError("invalid response")

        return data


    def check_updates_now(self, *, manual: bool = True) -> None:
        self.set_update_status("update_status_checking")

        threading.Thread(
            target=lambda: self.check_updates_worker(manual=manual),
            daemon=True,
            name="tunnelgram-update-check",
        ).start()


    def check_updates_worker(self, *, manual: bool) -> None:
        try:
            data = self.fetch_latest_release()

            latest_tag = str(data.get("tag_name", "")).strip()
            release_url = str(data.get("html_url", "")).strip()

            if not latest_tag:
                self.after(0, lambda: self.set_update_status("update_status_bad_response"))
                return

            if self.is_newer_version(latest_tag, VERSION):
                self._latest_release_url = release_url

                def show_available() -> None:
                    self.set_update_status("update_status_available", version=latest_tag)

                    if manual:
                        message = self.tr(
                            "update_open_release_question",
                            latest=latest_tag,
                            current=VERSION,
                        )

                        try:
                            open_release = messagebox.askyesno(APP_NAME, message)
                        except Exception:
                            open_release = False

                        if open_release and release_url:
                            try:
                                webbrowser.open(release_url)
                            except Exception:
                                pass

                self.after(0, show_available)
                return

            self._latest_release_url = release_url
            self.after(0, lambda: self.set_update_status("update_status_latest"))

        except UpdateCheckNotFoundError:
            self.after(0, lambda: self.set_update_status("update_status_not_found"))

        except UpdateCheckNetworkError:
            # Не показываем messagebox. Просто тихий понятный статус.
            self.after(0, lambda: self.set_update_status("update_status_later"))

        except Exception:
            self.after(0, lambda: self.set_update_status("update_status_bad_response"))


    def check_updates_on_startup(self) -> None:
        if not bool(self.check_updates.get()):
            return

        self.check_updates_now(manual=False)

    # ── actions ────────────────────────────────────────────────────────────
    def select_sing_box_binary(self) -> None:
        path = filedialog.askopenfilename(
            title=self.tr("sing_box_path"),
            filetypes=[
                (self.tr("sing_box_files"), "sing-box*"),
                (self.tr("all_files"), "*"),
            ],
            parent=self._settings_win if self._settings_win and self._settings_win.winfo_exists() else self,
        )
        if path:
            self.sing_box_path.set(path)

    def validate_fields(self) -> None:
        try:
            port = int(self.listen_port.get().strip())
        except Exception as exc:
            raise ValueError(self.tr("port_must_be_number")) from exc
        if not (1 <= port <= 65535):
            raise ValueError(self.tr("port_range"))

        if self.app_mode.get() == "proxy":
            host = self.listen_host.get().strip().lower()
            if host not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError(self.tr("proxy_mode_local_only"))
            uri = self.upstream_proxy_uri.get().strip()
            if not uri:
                raise ValueError(self.tr("profile_required"))
            try:
                parse_proxy_uri(uri)
            except ProxyProfileError as exc:
                raise ValueError(str(exc)) from exc
            username = self.local_proxy_username.get()
            password = self.local_proxy_password.get()
            if bool(username) != bool(password):
                raise ValueError(self.tr("local_auth_pair"))
            explicit = self.sing_box_path.get().strip()
            if explicit and not Path(explicit).expanduser().is_file():
                raise ValueError(self.tr("sing_box_missing"))
            return

        validate_secret_hex(self.secret.get())
        domain = self.fake_tls_domain.get().strip().lower()
        if domain:
            hostname_to_hex(domain)
        if self.secret_mode.get() == "ee" and not domain:
            raise ValueError(self.tr("faketls_sni_required"))
        if self.route_mode.get() == "cloudflare":
            cf_domain = self.cf_domain.get().strip().lower()
            if not cf_domain or "." not in cf_domain:
                raise ValueError(self.tr("cf_suffix_required"))

    def current_full_secret(self) -> str:
        if self.app_mode.get() == "proxy":
            return ""
        secret = validate_secret_hex(self.secret.get())
        if self.secret_mode.get() == "ee":
            return build_faketls_secret_hex(secret, self.fake_tls_domain.get().strip().lower())
        return "dd" + secret

    def current_link(self) -> str:
        host = self.listen_host.get().strip() or "127.0.0.1"
        port = int(self.listen_port.get().strip() or "9443")
        if self.app_mode.get() == "proxy":
            return telegram_socks_link(
                host,
                port,
                self.local_proxy_username.get(),
                self.local_proxy_password.get(),
            )
        secret = validate_secret_hex(self.secret.get())
        mode = self.secret_mode.get().strip() or "dd"
        domain = self.fake_tls_domain.get().strip().lower()
        return telegram_link(host, port, secret, mode=mode, fake_tls_domain=domain)

    def copy_full_secret(self) -> None:
        try:
            value = self.current_full_secret()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self.clipboard_clear()
        self.clipboard_append(value)
        self.log(self.tr("full_secret_copied"), "ok")

    def copy_tg_link(self) -> None:
        try:
            link = self.current_link()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self.clipboard_clear()
        self.clipboard_append(link)
        self.log(self.tr("tg_link_copied"), "ok")

    def open_tg_link(self) -> None:
        try:
            link = self.current_link()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return

        ok = self.open_external_url(link)

        if ok:
            self.log("Открываю Telegram. (если окно не развернулось автоматически, нужно развернуть его самостоятельно и согласиться на добавление локального прокси)", "ok")
        else:
            self.copy_tg_link()
            messagebox.showwarning(
                APP_NAME,
                "Не удалось открыть Telegram автоматически.\n\n"
                "Ссылка скопирована в буфер обмена — вставь её вручную в Telegram Desktop.",
            )
        
    def open_external_url(self, url: str) -> bool:
        if os.name == "nt":
            return bool(webbrowser.open(url))

        if sys.platform == "darwin":
            try:
                subprocess.Popen(
                    ["open", url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                return bool(webbrowser.open(url))

        candidates = []

        if shutil.which("telegram-desktop"):
            candidates.append(["telegram-desktop", url])

        if shutil.which("Telegram"):
            candidates.append(["Telegram", url])

        if shutil.which("telegram"):
            candidates.append(["telegram", url])

        if shutil.which("flatpak"):
            try:
                result = subprocess.run(
                    ["flatpak", "info", "org.telegram.desktop"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                )
                if result.returncode == 0:
                    candidates.append(["flatpak", "run", "org.telegram.desktop", url])
            except Exception:
                pass

        if shutil.which("xdg-open"):
            candidates.append(["xdg-open", url])

        if shutil.which("gio"):
            candidates.append(["gio", "open", url])

        for cmd in candidates:
            try:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                continue

        return bool(webbrowser.open(url))

    def generate_secret(self) -> None:
        self.secret.set(generate_secret_hex())
        self.refresh_summary()
        self.log(self.tr("new_secret_generated"), "ok")

    def toggle_proxy(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.stop_proxy()
        else:
            self.start_proxy()

    def cleanup_sing_box_runtime_config(self) -> None:
        path = self._sing_box_runtime_config
        self._sing_box_runtime_config = None
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def clean_sing_box_output(value: str) -> str:
        # sing-box enables coloured fatal messages on some Windows builds.
        return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value or "").strip()

    def start_proxy(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.log(self.tr("proxy_already_started"), "muted")
            return
        try:
            self.save_config(silent=True)
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return

        self.errors_status.set("0")
        self.telegram_status.set(self.tr("status_waiting_telegram"))
        self.active_status.set("0")
        self.traffic_status.set("↑ 0B   ↓ 0B")

        if self.app_mode.get() == "proxy":
            try:
                binary = find_sing_box_binary(self.sing_box_path.get())
                profile, config = build_singbox_config(
                    self.upstream_proxy_uri.get(),
                    listen_host=self.listen_host.get().strip(),
                    listen_port=int(self.listen_port.get().strip()),
                    local_username=self.local_proxy_username.get(),
                    local_password=self.local_proxy_password.get(),
                )
                self.cleanup_sing_box_runtime_config()
                config_path = write_singbox_runtime_config(config)
                self._sing_box_runtime_config = config_path
                check = subprocess.run(
                    [str(binary), "check", "-c", str(config_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=20,
                    **subprocess_window_kwargs(),
                )
                if check.returncode != 0:
                    details = self.clean_sing_box_output(check.stdout) or f"exit code {check.returncode}"
                    raise RuntimeError(details)
                cmd = [str(binary), "run", "-c", str(config_path)]
                self.log(self.tr("profile_valid", name=profile.name), "ok")
            except FileNotFoundError:
                self.cleanup_sing_box_runtime_config()
                messagebox.showerror(APP_NAME, self.tr("sing_box_missing"))
                return
            except Exception as exc:
                self.cleanup_sing_box_runtime_config()
                messagebox.showerror(APP_NAME, self.tr("profile_check_failed", error=exc))
                return
        else:
            cmd = proxy_command() + [
                "--listen-host",
                self.listen_host.get().strip(),
                "--listen-port",
                self.listen_port.get().strip(),
                "--secret",
                validate_secret_hex(self.secret.get()),
                "--route-mode",
                self.route_mode.get().strip(),
                "--domain-style",
                self.domain_style.get().strip() or "kws",
            ]
            domain = self.fake_tls_domain.get().strip().lower()
            if domain:
                cmd.extend(["--fake-tls-domain", domain])
            if self.route_mode.get() == "cloudflare":
                cmd.extend(["--cf-domain", self.cf_domain.get().strip().lower()])
            if self.pin_telegram_ip.get():
                cmd.append("--pin-telegram-ip")
            else:
                cmd.append("--no-pin-telegram-ip")
            if not self.direct_fallback.get():
                cmd.append("--no-direct-fallback")

        self._proc_uses_sing_box = self.app_mode.get() == "proxy"

        try:
            process_kwargs = subprocess_window_kwargs()
            if self._proc_uses_sing_box:
                process_kwargs.update({"encoding": "utf-8", "errors": "replace"})

            self.proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT) if not self._proc_uses_sing_box else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                **process_kwargs,
            )
        except Exception as exc:
            if self.app_mode.get() == "proxy":
                self.cleanup_sing_box_runtime_config()
            messagebox.showerror(APP_NAME, self.tr("proxy_start_failed", error=exc))
            return

        threading.Thread(target=self.reader_thread, daemon=True).start()
        self.status.set(self.tr("status_running"))
        self.toggle_text.set(self.tr("toggle_off"))
        self.log(self.tr("proxy_started"), "ok")
        if self.app_mode.get() == "proxy":
            self.log(
                self.tr(
                    "local_proxy_ready",
                    host=self.listen_host.get().strip(),
                    port=self.listen_port.get().strip(),
                ),
                "ok",
            )
        self.refresh_summary()

    def reader_thread(self) -> None:
        if not self.proc or not self.proc.stdout:
            return
        for line in self.proc.stdout:
            if self._proc_uses_sing_box:
                line = self.clean_sing_box_output(line)
                if not line:
                    continue
                line += "\n"
            self.log_queue.put(line)
        self.log_queue.put("[process exited]\n")

    def stop_proxy(self) -> None:
        if not self.proc or self.proc.poll() is not None:
            self.cleanup_sing_box_runtime_config()
            self.status.set(self.tr("status_stopped"))
            self.telegram_status.set(self.tr("status_no_connections"))
            self.active_status.set("0")
            self.refresh_summary()
            self.log(self.tr("proxy_not_started"), "muted")
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.cleanup_sing_box_runtime_config()
        self.status.set(self.tr("status_stopped"))
        self.telegram_status.set(self.tr("status_no_connections"))
        self.active_status.set("0")
        self.toggle_text.set(self.tr("toggle_on"))
        self.refresh_summary()
        self.log(self.tr("proxy_stopped"), "muted")

    def check_wss(self) -> None:
        if self.app_mode.get() == "proxy":
            try:
                self.validate_fields()
            except Exception as exc:
                messagebox.showerror(APP_NAME, str(exc))
                return

            self.telegram_status.set(self.tr("status_checking_profile"))
            self.log(self.tr("checking_proxy_profile"), "muted")

            def run_profile_check() -> None:
                try:
                    binary = find_sing_box_binary(self.sing_box_path.get())
                    profile, config = build_singbox_config(
                        self.upstream_proxy_uri.get(),
                        listen_host=self.listen_host.get().strip(),
                        listen_port=int(self.listen_port.get().strip()),
                        local_username=self.local_proxy_username.get(),
                        local_password=self.local_proxy_password.get(),
                    )
                    config_path = write_singbox_runtime_config(config)
                    try:
                        result = subprocess.run(
                            [str(binary), "check", "-c", str(config_path)],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            timeout=20,
                            **subprocess_window_kwargs(),
                        )
                        if result.returncode != 0:
                            details = self.clean_sing_box_output(result.stdout) or f"exit code {result.returncode}"
                            raise RuntimeError(details)
                        self.log_queue.put(self.tr("profile_valid", name=profile.name) + "\n")
                        self.log_queue.put("__STATUS_PROXY_PROFILE_OK__\n")
                    finally:
                        try:
                            config_path.unlink(missing_ok=True)
                        except OSError:
                            pass
                except Exception as exc:
                    self.log_queue.put(self.tr("profile_check_failed", error=exc) + "\n")
                    self.log_queue.put("__STATUS_PROXY_PROFILE_FAIL__\n")

            threading.Thread(target=run_profile_check, daemon=True).start()
            return

        language = self.language.get() if hasattr(self, "language") else "ru"
        cmd = diagnostics_command() + [
            "--domain-style",
            self.domain_style.get().strip() or "kws",
            "--timeout",
            "8",
            "--language",
            language,
            "--gui-markers",
            "--stop-on-success",
        ]
        if self.route_mode.get() == "cloudflare":
            cmd.extend(["--route-mode", "cloudflare", "--cf-domain", self.cf_domain.get().strip().lower()])
        else:
            cmd.extend(["--route-mode", "telegram"])
        if self.pin_telegram_ip.get():
            cmd.append("--pin-telegram-ip")

        self.telegram_status.set(self.tr("status_checking_wss"))
        self.log(self.tr("check_wss_log"), "muted")

        def run_diag():
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(PROJECT_ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    **subprocess_window_kwargs(),
                )
                ok_seen = False
                if proc.stdout:
                    for line in proc.stdout:
                        stripped = line.strip()
                        if stripped == "__DIAG_WSS_OK__":
                            ok_seen = True
                            continue
                        if stripped == "__DIAG_WSS_FAIL__":
                            continue
                        self.log_queue.put(line)
                proc.wait(timeout=90)
                self.log_queue.put("__STATUS_WSS_OK__\n" if ok_seen else "__STATUS_WSS_DONE__\n")
            except Exception as exc:
                self.log_queue.put(f"[diagnostics failed] {exc}\n")
                self.log_queue.put("__STATUS_WSS_FAIL__\n")

        threading.Thread(target=run_diag, daemon=True).start()

    # ── tray ───────────────────────────────────────────────────────────────
    def make_tray_image(self):
        """
        Иконка для системного трея.
        Сначала пробуем взять assets/tunnelgram.png или .ico.
        Если файлов нет — рисуем простую fallback-иконку.
        """
        if Image is not None:
            try:
                if ICON_PNG.exists():
                    return Image.open(ICON_PNG).convert("RGBA")
                if ICON_ICO.exists():
                    return Image.open(ICON_ICO).convert("RGBA")
            except Exception:
                pass

        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        draw.rounded_rectangle((10, 14, 54, 54), radius=12, fill=(59, 130, 246, 255))
        draw.arc((18, 6, 46, 36), 200, -20, fill=(147, 197, 253, 255), width=6)
        draw.rectangle((29, 32, 35, 45), fill=(255, 255, 255, 255))
        draw.ellipse((25, 27, 39, 41), fill=(255, 255, 255, 255))

        return img

    def setup_tray_icon(self) -> None:
        if sys.platform == "darwin":
            self.tray_icon = None
            return

        if pystray is None or Image is None or ImageDraw is None:
            self.tray_icon = None
            return

        menu = pystray.Menu(
            pystray.MenuItem(
                self.tr("tray_show_window"),
                self.tray_action(self.show_from_tray),
            ),
            pystray.MenuItem(
                self.tr("tray_toggle_proxy"),
                self.tray_action(self.toggle_proxy),
            ),
            pystray.MenuItem(
                self.tr("tray_open_telegram"),
                self.tray_action(self.open_tg_link),
            ),
            pystray.MenuItem(
                self.tr("tray_copy_tg"),
                self.tray_action(self.copy_tg_link),
            ),
            pystray.MenuItem(
                self.tr("tray_exit"),
                self.tray_action(self.quit_app),
            ),
        )

        self.tray_icon = pystray.Icon(
            "tunnelgram",
            self.make_tray_image(),
            APP_NAME,
            menu,
        )

        try:
            if sys.platform.startswith("linux"):
                backend = type(self.tray_icon).__module__
                has_menu = getattr(self.tray_icon, "HAS_MENU", None)
                has_default = getattr(self.tray_icon, "HAS_DEFAULT_ACTION", None)

                if "_xorg" in backend:
                    self.log(
                        self.tr("tray_xorg_warn"),
                        "warn",
                    )
                else:
                    self.log(
                        self.tr("tray_backend", backend=backend, menu=has_menu, default=has_default),
                        "muted",
                    )
        except Exception:
            pass

        self.tray_thread = threading.Thread(
            target=self.tray_icon.run,
            daemon=True,
            name="tunnelgram-tray",
        )
        self.tray_thread.start()

    def hide_to_tray(self) -> None:
        if self.tray_icon is None:
            self.log(self.tr("tray_unavailable"), "warn")
            return

        self._hidden_to_tray = True
        self.withdraw()
        self.log(self.tr("tray_hidden"), "muted")

    def show_from_tray(self) -> None:
        self._hidden_to_tray = False

        try:
            self.deiconify()
            self.state("normal")
            self.lift()
            self.focus_force()

            self.attributes("-topmost", True)
            self.after(250, lambda: self.attributes("-topmost", False))
        except Exception:
            pass
        
    def call_ui(self, fn) -> None:
        try:
            self.after(0, fn)
        except Exception:
            pass


    def tray_action(self, fn):
        return lambda icon=None, item=None: self.call_ui(fn)


    def toggle_tray_window(self) -> None:
        try:
            if self._hidden_to_tray or self.state() == "withdrawn":
                self.show_from_tray()
            else:
                self.hide_to_tray()
        except Exception:
            self.show_from_tray()

    def quit_app(self) -> None:
        self._quitting = True
        try:
            if self.proc and self.proc.poll() is None:
                self.stop_proxy()
            else:
                self.cleanup_sing_box_runtime_config()

            self.clear_logs_on_exit()
        finally:
            try:
                if self.tray_icon is not None:
                    self.tray_icon.stop()
            except Exception:
                pass

            self.release_single_instance_lock()
            self.destroy()

    def on_close(self) -> None:
        if self._quitting:
            self.quit_app()
            return
        if self.tray_icon is not None:
            self.hide_to_tray()
            return
        self.quit_app()


def main() -> None:
    setup_windows_app_id()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
