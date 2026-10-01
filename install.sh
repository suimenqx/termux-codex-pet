#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd -P)"

if ! command -v python >/dev/null 2>&1; then
  pkg install -y python
fi
if ! python -c 'import ctypes; ctypes.CDLL("libpng16.so")' >/dev/null 2>&1; then
  pkg install -y libpng
fi
if ! python -c 'import termuxgui' >/dev/null 2>&1; then
  python -m pip install termuxgui
fi

PYTHONPATH="$PROJECT_DIR" python -m codex_pet.deployment install \
  --source "$PROJECT_DIR" --home "$HOME" --prefix "$PREFIX"
