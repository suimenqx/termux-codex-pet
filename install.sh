#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd -P)"

if ! command -v python >/dev/null 2>&1; then
  pkg install -y python
fi
if ! PYTHONPATH="$PROJECT_DIR" python -c 'from codex_pet.image_codec import check_capability; check_capability()' >/dev/null 2>&1; then
  pkg install -y python-pillow
fi
PYTHONPATH="$PROJECT_DIR" python -c 'from codex_pet.image_codec import check_capability; check_capability()'
if ! python -c 'import termuxgui' >/dev/null 2>&1; then
  python -m pip install termuxgui
fi

PYTHONPATH="$PROJECT_DIR" python -m codex_pet.deployment install \
  --source "$PROJECT_DIR" --home "$HOME" --prefix "$PREFIX"
