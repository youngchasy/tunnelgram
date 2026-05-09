#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

APP_NAME="tunnelgram"
VENV_DIR=".venv"

echo "=================================================="
echo "  tunnelgram - setup and run"
echo "=================================================="
echo

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

PYTHON_CMD="$(find_python)"

if [ -z "$PYTHON_CMD" ]; then
  echo "Python 3 was not found."
  echo

  if [ "$OS_NAME" = "linux" ]; then
    echo "Install Python 3 first."
    echo
    echo "Debian/Ubuntu:"
    echo "  sudo apt update"
    echo "  sudo apt install python3 python3-venv python3-pip python3-tk"
    echo
    echo "Fedora:"
    echo "  sudo dnf install python3 python3-pip python3-tkinter"
    echo
    echo "Arch:"
    echo "  sudo pacman -S python tk"
  elif [ "$OS_NAME" = "macos" ]; then
    echo "Install Python 3 first."
    echo
    echo "Recommended:"
    echo "  install Python from https://www.python.org/downloads/macos/"
    echo
    echo "Or with Homebrew:"
    echo "  brew install python"
  else
    echo "Install Python 3 and try again."
  fi

  exit 1
fi

echo "Found Python:"
"$PYTHON_CMD" --version
echo

echo "Checking tkinter..."
if ! "$PYTHON_CMD" - <<'PY'
import tkinter
PY
then
  echo
  echo "tkinter is missing. tunnelgram GUI requires tkinter."
  echo

  if [ "$OS_NAME" = "linux" ]; then
    echo "Install tkinter for your distro:"
    echo
    echo "Debian/Ubuntu:"
    echo "  sudo apt install python3-tk"
    echo
    echo "Fedora:"
    echo "  sudo dnf install python3-tkinter"
    echo
    echo "Arch:"
    echo "  sudo pacman -S tk"
  elif [ "$OS_NAME" = "macos" ]; then
    echo "Install Python from python.org, then try again:"
    echo "  https://www.python.org/downloads/macos/"
  fi

  exit 1
fi

if [ "$OS_NAME" = "linux" ]; then
  if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    echo "Warning: no DISPLAY or WAYLAND_DISPLAY detected."
    echo "The GUI may not open unless you are running inside a desktop session."
    echo
  fi
fi

if [ ! -f "$VENV_DIR/bin/python" ]; then
  echo "Creating virtual environment..."
  "$PYTHON_CMD" -m venv "$VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"

echo "Upgrading pip..."
"$VENV_PY" -m pip install --upgrade pip

echo
echo "Installing dependencies..."
"$VENV_PY" -m pip install -r requirements.txt

echo
echo "Starting tunnelgram..."
"$VENV_PY" -m tunnelgram.gui

echo
echo "tunnelgram closed."