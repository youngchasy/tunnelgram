#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

APP_NAME="tunnelgram"
VENV_DIR=".venv"
VENV_PY="$VENV_DIR/bin/python"
LOG_DIR="$HOME/.tunnelgram"
LOG_FILE="$LOG_DIR/autostart.log"

mkdir -p "$LOG_DIR"

exec >>"$LOG_FILE" 2>&1

echo "=================================================="
echo "$(date '+%Y-%m-%d %H:%M:%S') - starting $APP_NAME autostart"
echo "=================================================="

detect_os() {
  case "$(uname -s)" in
    Linux*)  echo "linux" ;;
    Darwin*) echo "macos" ;;
    *)       echo "unknown" ;;
  esac
}

OS_NAME="$(detect_os)"

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

check_tkinter() {
  "$1" - <<'PY'
import tkinter
PY
}

PYTHON_CMD="$(find_python)"

if [ -z "$PYTHON_CMD" ]; then
  echo "ERROR: Python 3 was not found."
  exit 1
fi

echo "Found Python:"
"$PYTHON_CMD" --version

if [ "$OS_NAME" = "linux" ]; then
  if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    echo "WARNING: no DISPLAY or WAYLAND_DISPLAY detected."
  fi
fi

if ! check_tkinter "$PYTHON_CMD"; then
  echo "ERROR: tkinter is missing in system Python."
  exit 1
fi

if [ ! -f "$VENV_PY" ]; then
  echo "Creating virtual environment..."
  "$PYTHON_CMD" -m venv "$VENV_DIR"
fi

if ! check_tkinter "$VENV_PY"; then
  echo "ERROR: tkinter is missing in virtual environment."
  exit 1
fi

echo "Installing/updating dependencies..."
"$VENV_PY" -m pip install --upgrade pip >/dev/null 2>&1
"$VENV_PY" -m pip install -r requirements.txt >/dev/null 2>&1

echo "Checking Python files..."
"$VENV_PY" -m compileall tunnelgram >/dev/null
if [ -f "tunnelgram_app.py" ]; then
  "$VENV_PY" -m py_compile tunnelgram_app.py
fi

echo "Launching $APP_NAME..."
"$VENV_PY" -m tunnelgram.gui

echo "$(date '+%Y-%m-%d %H:%M:%S') - $APP_NAME closed"