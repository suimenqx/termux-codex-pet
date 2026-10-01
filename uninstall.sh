#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
PYTHONPATH="$PROJECT_DIR" python -m codex_pet.deployment uninstall \
  --source "$PROJECT_DIR" --home "$HOME" --prefix "$PREFIX"
