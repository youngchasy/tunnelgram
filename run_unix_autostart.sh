#!/usr/bin/env bash
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