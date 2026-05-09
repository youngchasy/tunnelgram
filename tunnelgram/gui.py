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
from pathlib import Path
import tkinter as tk
from tkinter import END, BooleanVar, StringVar, Toplevel, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText

from .faketls import build_faketls_secret_hex, hostname_to_hex
from .mtproto import generate_secret_hex, telegram_link, validate_secret_hex

APP_NAME = "tunnelgram"
VERSION = "0.1.0"
PROJECT_ROOT = Path(__file__).resolve().parents[1]

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

try:  # optional tray dependencies
    import pystray  # type: ignore
    from PIL import Image, ImageDraw  # type: ignore
except Exception:  # pragma: no cover
    pystray = None
    Image = None
    ImageDraw = None


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


def app_dir() -> Path:
    if os.name == "nt" and os.getenv("APPDATA"):
        return Path(os.getenv("APPDATA", "")) / "TunnelGram"
    return Path.home() / ".tunnelgram"


CONFIG_PATH = app_dir() / "config.json"

# Read old config once so users do not lose working settings after the rename.
def old_config_path() -> Path:
    if os.name == "nt" and os.getenv("APPDATA"):
        return Path(os.getenv("APPDATA", "")) / "TunnelGramDirect" / "config.json"
    return Path.home() / ".tunnelgram-direct" / "config.json"


DEFAULT_CONFIG = {
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
    "theme": "dark",
    "autostart": False,
}


def fmt_bool(value: bool) -> str:
    return "вкл" if value else "выкл"

def setup_windows_app_id() -> None:
    if os.name != "nt":
        return

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except Exception:
        pass

class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self._instance_socket: socket.socket | None = None

        if not self.acquire_single_instance_lock():
            self.withdraw()
            messagebox.showinfo(
                APP_NAME,
                "tunnelgram уже запущен.\n\n"
                "Чтобы открыть окно, найди иконку приложения в трее.",
            )
            self.destroy()
            raise SystemExit(0)

        self.title(f"{APP_NAME} {VERSION}")
        self.geometry("900x640")
        self.minsize(900, 640)
        self.setup_window_icon()

        self.proc: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.tray_icon = None
        self.tray_thread: threading.Thread | None = None
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

        cfg = self.load_config()
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
        self.theme_name = StringVar(value=cfg.get("theme", DEFAULT_CONFIG["theme"]) if cfg.get("theme", "") in THEMES else "dark")
        self.autostart_windows = BooleanVar(
            value=bool(cfg.get("autostart_windows", DEFAULT_CONFIG["autostart_windows"]))
        )

        self.status = StringVar(value="Остановлен")
        self.telegram_status = StringVar(value="Ждёт запуска")
        self.active_status = StringVar(value="0")
        self.traffic_status = StringVar(value="↑ 0B   ↓ 0B")
        self.errors_status = StringVar(value="0")
        self.quick_settings = StringVar(value="")
        self.full_secret = StringVar(value="")
        self.toggle_text = StringVar(value="Включить")

        self.theme = THEMES.get(self.theme_name.get(), THEMES["dark"])

        self.create_widgets()
        self.apply_theme()
        self.refresh_summary()
        self.setup_tray_icon()
        self.after(150, self.drain_logs)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        for var in (
            self.listen_host, self.listen_port, self.secret, self.secret_mode,
            self.fake_tls_domain, self.route_mode, self.cf_domain, self.domain_style,
        ):
            var.trace_add("write", lambda *_: self.refresh_summary())
        self.pin_telegram_ip.trace_add("write", lambda *_: self.refresh_summary())
        self.direct_fallback.trace_add("write", lambda *_: self.refresh_summary())

    def acquire_single_instance_lock(self) -> bool:
        """
        Не даёт запустить вторую копию tunnelgram.

        Работает через локальный lock-сокет:
        первая копия занимает 127.0.0.1:48173,
        вторая копия не может занять этот же порт и закрывается.
        """
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
        """
        Создаёт run_unix_autostart.sh, если его нет.
        Используется для Linux/macOS автозапуска.
        """
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
        script = self.ensure_unix_autostart_script()

        if enabled:
            LINUX_AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)

            content = f"""[Desktop Entry]
    Type=Application
    Name=tunnelgram
    Comment=Start tunnelgram on login
    Exec={script}
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
        script = self.ensure_unix_autostart_script()

        if enabled:
            MACOS_LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)

            plist_data = {
                "Label": "com.tunnelgram.app",
                "ProgramArguments": [
                    "/bin/bash",
                    str(script),
                ],
                "RunAtLoad": True,
                "WorkingDirectory": str(PROJECT_ROOT),
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
            "theme": self.theme_name.get(),
            "autostart_windows": bool(self.autostart_windows.get()),
        }

    def save_config(self, silent: bool = False) -> None:
        self.validate_fields()
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

        cfg = self.current_config()
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        self._current_cfg = cfg

        self.sync_system_autostart()

        self.refresh_summary()
        if not silent:
            self.log("Настройки сохранены.", "ok")
            if os.name == "nt":
                self.log(
                    "Автозапуск Windows: " + ("включён" if self.autostart_windows.get() else "выключен"),
                    "ok" if self.autostart_windows.get() else "muted",
                )

    def ensure_hidden_launcher(self) -> Path:
        """
        Создаёт run_hidden.vbs, если его нет.
        Этот файл запускает GUI через pythonw.exe без консоли.
        """
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
        """
        Команда, которую Windows будет запускать при входе пользователя.
        """
        launcher = self.ensure_hidden_launcher()
        return f'wscript.exe //B //Nologo "{launcher}"'


    def set_windows_autostart(self, enabled: bool) -> None:
        """
        Включает/выключает автозапуск через HKCU\\...\\Run.
        Не требует прав администратора.
        """
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
        """
        Проверяет, есть ли запись автозапуска в реестре.
        """
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
        """
        Синхронизирует чекбокс из настроек с реестром Windows.
        """
        if os.name != "nt":
            return

        self.set_windows_autostart(bool(self.autostart_windows.get()))

    def sync_system_autostart(self) -> None:
        enabled = bool(self.autostart_windows.get())

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
        """
        Ставит иконку окна и панели задач.
        На Windows лучше всего работает .ico.
        """
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
                self._window_icon_ref = img  # держим ссылку, чтобы Tkinter не удалил картинку
        except Exception:
            pass

    # ── UI helpers ─────────────────────────────────────────────────────────
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
        return self.watch(label, bg, role)  # type: ignore[return-value]

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
        return self.watch(entry, "entry", "text")  # type: ignore[return-value]
    
    def split_label_hint(self, text: str) -> tuple[str, str]:
        """
        'Secret (рекомендуется изменить)' -> ('Secret', 'рекомендуется изменить')
        'Адрес' -> ('Адрес', '')
        """
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
        self.theme_btn = self.make_button(right, text="Тема", command=self.toggle_theme, kind="secondary", width=10)
        self.theme_btn.pack(anchor="e")

    def create_status_cards(self) -> None:
        area = tk.Frame(self.root_frame, bd=0)
        self.watch(area, "bg")
        area.grid(row=1, column=0, sticky="ew", pady=(30, 14))

        cards = [
            (0, "Прокси", self.status),
            (1, "Telegram", self.telegram_status),
            (2, "Трафик", self.traffic_status),
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
        self.make_button(actions, text="Ссылка", command=self.copy_tg_link, kind="secondary", width=6).grid(row=0, column=1, padx=(0, 10), ipady=2)
        self.make_button(actions, text="Настройки", command=self.open_settings, kind="secondary", width=10).grid(row=0, column=2, ipady=2)

    def create_log_card(self) -> None:
        card = self.make_section(self.root_frame)
        card.grid(row=3, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)

        head = tk.Frame(card, bd=0)
        self.watch(head, "card")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 10))
        head.columnconfigure(1, weight=1)
        self.make_label(head, "Логи", role="text", size=13, weight="bold", bg="card").grid(row=0, column=0, sticky="w")

        buttons = tk.Frame(head, bd=0)
        self.watch(buttons, "card")
        buttons.grid(row=0, column=2, sticky="e")
        if pystray is not None:
            self.make_button(buttons, text="Свернуть в трей", command=self.hide_to_tray, kind="secondary", width=12).pack(side="left", padx=(0, 10))
        self.make_button(buttons, text="Проверить соединение", command=self.check_wss, kind="secondary", width=18).pack(side="left", padx=(0, 10))
        self.make_button(
            buttons,
            text="Экспорт",
            command=self.export_logs,
            kind="secondary",
            width=10,
        ).pack(side="left", padx=(0, 8))
        self.make_button(buttons, text="Очистить логи", command=self.clear_logs, kind="secondary", width=10).pack(side="left")

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
        self.log("Готово. Нажми «Включить», затем «Telegram». (рекомендуется изменить стандартные настройки, в том случае если с первого раза ничего не работает)", "ok")

    def open_settings(self) -> None:
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.lift()
            self._settings_win.focus_force()
            return

        win = Toplevel(self)
        self._settings_win = win
        win.title("Настройки tunnelgram")
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

        self.make_label(frame, "Настройки", role="text", size=20, weight="bold", bg="bg").grid(row=0, column=0, sticky="w")

        body = tk.Frame(frame, bd=0)
        self.watch(body, "bg")
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1, uniform="settings_columns")
        body.columnconfigure(1, weight=1, uniform="settings_columns")

        basic = self.make_section(body)
        basic.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        route = self.make_section(body)
        route.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        body.rowconfigure(0, weight=1)
        basic.grid_propagate(False)
        route.grid_propagate(False)

        body.rowconfigure(0, weight=1)

        for panel in (basic, route):
            panel.columnconfigure(1, weight=1)

        self.make_label(basic, "Основное", role="text", size=13, weight="bold", bg="card").grid(row=0, column=0, columnspan=3, sticky="w", padx=18, pady=(18, 10))
        self.add_entry(basic, 1, "Адрес", self.listen_host)
        self.add_entry(basic, 2, "Порт", self.listen_port)
        self.add_entry_with_button(
            basic,
            3,
            "Secret (рекомендуется изменить)",
            self.secret,
            button_text="↻",
            button_command=self.generate_secret,
            button_kind="secondary",
            button_width=3,
        )

        secret_type_box = tk.Frame(basic, bd=0)
        self.watch(secret_type_box, "card")
        secret_type_box.grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(8, 10),
        )

        self.make_caption(
            secret_type_box,
            "Тип secret (дефолт Fake TLS)",
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

        self.add_entry(basic, 6, "SNI", self.fake_tls_domain)

        autostart_box = tk.Frame(basic, bd=0)
        self.watch(autostart_box, "card")
        autostart_box.grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(8, 10),
        )
        autostart_box.columnconfigure(0, weight=1)

        self.add_check(
            autostart_box,
            "Запускать вместе с системой",
            self.autostart_windows,
        ).grid(row=0, column=0, sticky="w")

        self.make_label(
            autostart_box,
            "по умолчанию выключено",
            role="muted",
            size=8,
            bg="card",
        ).grid(row=1, column=0, sticky="w", padx=(24, 0), pady=(2, 0))

        self.make_label(route, "Маршрут", role="text", size=13, weight="bold", bg="card").grid(row=0, column=0, columnspan=3, sticky="w", padx=18, pady=(18, 10))
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
            "Режим (дефолт Direct WSS)",
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
            "только если есть свой домен в Cloudflare",
            role="muted",
            size=8,
            bg="card",
        ).grid(row=1, column=0, sticky="w", padx=(24, 0), pady=(2, 0))

        self.add_entry(route, 2, "Cloudflare suffix (вводить если выбран режим Cloudflare DNS)", self.cf_domain)
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
            "Домены (дефолт kws)",
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
            "имена DC",
            self.domain_style,
            "names",
        ).grid(row=0, column=1, sticky="w", padx=(18, 0))

        bottom = tk.Frame(frame, bd=0)
        self.watch(bottom, "bg")
        bottom.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        self.make_button(bottom, text="Сохранить", command=lambda: self.save_settings_window(win), kind="primary", width=14).pack(side="right")
        self.make_button(bottom, text="Закрыть", command=win.destroy, kind="secondary", width=12).pack(side="right", padx=(0, 10))

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
        try:
            self.save_config(silent=True)
        except Exception:
            pass

    # ── state/logs ─────────────────────────────────────────────────────────
    def refresh_summary(self) -> None:
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
            f"Pin IP {fmt_bool(self.pin_telegram_ip.get())}  ·  TCP fallback {fmt_bool(self.direct_fallback.get())}"
        )
        running = bool(self.proc and self.proc.poll() is None)
        self.toggle_text.set("Выключить" if running else "Включить")
        if hasattr(self, "toggle_btn"):
            # Blue when idle, red when running.
            kind = "danger" if running else "primary"
            for i, (btn, k) in enumerate(self._buttons):
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
        self.log("Логи очищены.", "muted")

    def prune_logs_if_needed(self, force: bool = False) -> None:
        """
        Держит в GUI только последние self._max_log_lines строк.
        Старые строки удаляются, чтобы ScrolledText не рос бесконечно.
        """
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
        """
        Экспортирует текущие видимые GUI-логи в .txt файл.
        Если включено ограничение размера логов, экспортируются последние строки,
        которые сейчас есть в окне логов.
        """
        try:
            content = self.log_text.get("1.0", "end-1c").strip()
        except Exception:
            content = ""

        if not content:
            messagebox.showinfo(APP_NAME, "Логи пустые, экспортировать нечего.")
            return

        from datetime import datetime

        default_name = f"tunnelgram_logs_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"

        path = filedialog.asksaveasfilename(
            title="Экспорт логов",
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
            messagebox.showerror(APP_NAME, f"Не удалось сохранить логи:\n\n{exc}")
            return

        self.log(f"Логи экспортированы: {path}", "ok")

    def clear_logs_on_exit(self) -> None:
        """
        Очищает GUI-логи при настоящем выходе из приложения.
        Не пишет строку "Логи очищены", потому что окно уже закрывается.
        """
        try:
            # Очищаем очередь логов, чтобы старые строки не успели дорисоваться.
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
        if noisy and self.telegram_status.get() == "Подключён":
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
        """
        Скрывает короткий WSS-шум, но иногда показывает краткую сводку.
        """
        self._suppressed_ws_noise += 1
        now = time.monotonic()

        if self._suppressed_ws_noise >= 25 and now - self._last_ws_noise_report >= 10:
            count = self._suppressed_ws_noise
            self._suppressed_ws_noise = 0
            self._last_ws_noise_report = now
            return True, "muted", f"Скрыто {count} коротких WSS-событий."

        return False, None, ""

    def parse_status_from_log(self, line: str) -> bool:
        stripped = line.strip()
        if stripped == "__STATUS_WSS_OK__":
            self.telegram_status.set("WSS доступен")
            return False
        if stripped == "__STATUS_WSS_DONE__":
            if self.telegram_status.get() == "Проверяю WSS…":
                self.telegram_status.set("WSS не найден")
            return False
        if stripped == "__STATUS_WSS_FAIL__":
            self.telegram_status.set("Ошибка проверки")
            return False

        if "local proxy listening" in line:
            self.status.set("Работает")
            self.telegram_status.set("Жду Telegram")
        if "-> Telegram WSS" in line:
            self.telegram_status.set("Подключён")
            try:
                n = int(self.active_status.get())
                self.active_status.set(str(max(1, n)))
            except ValueError:
                self.active_status.set("1")
        if "rejected:" in line:
            self.telegram_status.set("Secret не принят")
        elif "WSS path failed" in line or "unexpected error" in line or " timeout" in line:
            if self.telegram_status.get() not in {"Подключён", "WSS доступен"}:
                self.telegram_status.set("Проблема сети")
        m = re.search(r"stats: .*active=(\d+).*err=(\d+).*up=([^ ]+) down=([^\s]+)", line)
        if m:
            self.active_status.set(m.group(1))
            self.errors_status.set(m.group(2))
            self.traffic_status.set(f"↑ {m.group(3)}   ↓ {m.group(4)}")
            if int(m.group(1)) > 0:
                self.telegram_status.set("Подключён")
        if "[process exited]" in line:
            self.status.set("Остановлен")
            self.telegram_status.set("Нет подключений")
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
            self.status.set("Остановлен")
            self.refresh_summary()
        self.after(150, self.drain_logs)

    # ── actions ────────────────────────────────────────────────────────────
    def validate_fields(self) -> None:
        validate_secret_hex(self.secret.get())
        try:
            port = int(self.listen_port.get().strip())
        except Exception as exc:
            raise ValueError("Порт должен быть числом") from exc
        if not (1 <= port <= 65535):
            raise ValueError("Порт должен быть от 1 до 65535")
        domain = self.fake_tls_domain.get().strip().lower()
        if domain:
            hostname_to_hex(domain)
        if self.secret_mode.get() == "ee" and not domain:
            raise ValueError("Для Fake TLS нужен SNI-домен, например www.google.com")
        if self.route_mode.get() == "cloudflare":
            cf_domain = self.cf_domain.get().strip().lower()
            if not cf_domain or "." not in cf_domain:
                raise ValueError("Для Cloudflare DNS нужен suffix, например example.com")

    def current_full_secret(self) -> str:
        secret = validate_secret_hex(self.secret.get())
        if self.secret_mode.get() == "ee":
            return build_faketls_secret_hex(secret, self.fake_tls_domain.get().strip().lower())
        return "dd" + secret

    def current_link(self) -> str:
        host = self.listen_host.get().strip() or "127.0.0.1"
        port = int(self.listen_port.get().strip() or "9443")
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
        self.log("Полный secret скопирован.", "ok")

    def copy_tg_link(self) -> None:
        try:
            link = self.current_link()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self.clipboard_clear()
        self.clipboard_append(link)
        self.log("Ссылка tg:// скопирована.", "ok")

    def open_tg_link(self) -> None:
        try:
            link = self.current_link()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        webbrowser.open(link)
        self.log("Открываю Telegram.", "ok")

    def generate_secret(self) -> None:
        self.secret.set(generate_secret_hex())
        self.refresh_summary()
        self.log("Сгенерирован новый base secret.", "ok")

    def toggle_proxy(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.stop_proxy()
        else:
            self.start_proxy()

    def start_proxy(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.log("Прокси уже запущен.", "muted")
            return
        try:
            self.save_config(silent=True)
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return

        self.errors_status.set("0")
        self.telegram_status.set("Жду Telegram")
        self.active_status.set("0")
        self.traffic_status.set("↑ 0B   ↓ 0B")

        cmd = [
            sys.executable,
            "-u",
            "-m",
            "tunnelgram.local_proxy",
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

        try:
            self.proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Не удалось запустить прокси: {exc}")
            return

        threading.Thread(target=self.reader_thread, daemon=True).start()
        self.status.set("Работает")
        self.toggle_text.set("Выключить")
        self.log("Прокси запущен.", "ok")
        self.refresh_summary()

    def reader_thread(self) -> None:
        if not self.proc or not self.proc.stdout:
            return
        for line in self.proc.stdout:
            self.log_queue.put(line)
        self.log_queue.put("[process exited]\n")

    def stop_proxy(self) -> None:
        if not self.proc or self.proc.poll() is not None:
            self.status.set("Остановлен")
            self.telegram_status.set("Нет подключений")
            self.active_status.set("0")
            self.refresh_summary()
            self.log("Прокси не запущен.", "muted")
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.status.set("Остановлен")
        self.telegram_status.set("Нет подключений")
        self.active_status.set("0")
        self.toggle_text.set("Включить")
        self.refresh_summary()
        self.log("Прокси остановлен.", "muted")

    def check_wss(self) -> None:
        cmd = [
            sys.executable,
            "-u",
            "-m",
            "tunnelgram.diagnostics",
            "--domain-style",
            self.domain_style.get().strip() or "kws",
            "--timeout",
            "8",
        ]
        if self.route_mode.get() == "cloudflare":
            cmd.extend(["--route-mode", "cloudflare", "--cf-domain", self.cf_domain.get().strip().lower()])
        else:
            cmd.extend(["--route-mode", "telegram"])
        if self.pin_telegram_ip.get():
            cmd.append("--pin-telegram-ip")

        self.telegram_status.set("Проверяю WSS…")
        self.log("Проверяю WSS endpoint’ы…", "muted")

        def run_diag():
            try:
                proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                ok_seen = False
                if proc.stdout:
                    for line in proc.stdout:
                        if " OK" in line or "WSS OK" in line:
                            ok_seen = True
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
        if pystray is None or Image is None or ImageDraw is None:
            return

        def action(fn):
            return lambda icon=None, item=None: self.after(0, fn)

        menu = pystray.Menu(
            pystray.MenuItem("Показать", action(self.show_from_tray)),
            pystray.MenuItem("Включить/выключить", action(self.toggle_proxy)),
            pystray.MenuItem("Открыть Telegram", action(self.open_tg_link)),
            pystray.MenuItem("Скопировать tg://", action(self.copy_tg_link)),
            pystray.MenuItem("Выход", action(self.quit_app)),
        )
        self.tray_icon = pystray.Icon("tunnelgram", self.make_tray_image(), APP_NAME, menu)
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()

    def hide_to_tray(self) -> None:
        if self.tray_icon is None:
            self.log("Трей недоступен.", "warn")
            return
        self.withdraw()

    def show_from_tray(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def quit_app(self) -> None:
        self._quitting = True
        try:
            if self.proc and self.proc.poll() is None:
                self.stop_proxy()

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
