#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
LOCAL_BIN="$HOME/.local/bin"
PATH_BIN="$PREFIX/bin"
APP_DIR="$HOME/.local/share/codex-pet"

is_managed_entrypoint() {
  local name="$1"
  local target="$LOCAL_BIN/$name"
  if [ -f "$target" ] && grep -Fqx "# CODEX_PET_MANAGED_ENTRYPOINT=$name" "$target"; then
    return 0
  fi
  [ -L "$target" ] && [ "$(readlink -f "$target" 2>/dev/null || true)" = "$PROJECT_DIR/bin/$name" ]
}

if is_managed_entrypoint codex-pet; then
  "$LOCAL_BIN/codex-pet" stop
fi
if [ -f "$APP_DIR/current/codex_pet/hooks_config.py" ]; then
  PYTHONPATH="$(readlink -f "$APP_DIR/current")" python -m codex_pet.hooks_config uninstall
else
  PYTHONPATH="$PROJECT_DIR" python -m codex_pet.hooks_config uninstall
fi

for name in codex-pet codex-pet-event; do
  path_target="$PATH_BIN/$name"
  if [ -L "$path_target" ] && [ "$(readlink "$path_target")" = "$LOCAL_BIN/$name" ]; then
    unlink "$path_target"
    path_backup="$HOME/.config/codex-pet/cli-backups/prefix-$name"
    if [ -e "$path_backup" ] || [ -L "$path_backup" ]; then
      mv "$path_backup" "$path_target"
    fi
  fi
done
PYTHONPATH="$PROJECT_DIR" python -m codex_pet.deployment remove --source "$PROJECT_DIR" --home "$HOME"
python - <<'PY'
from pathlib import Path
base = Path.home() / '.cache' / 'codex-pet'
for name in ('pet.sock', 'pet.log', 'pet.log.1', 'pet.log.2', 'start.lock', 'daemon.lock'):
    (base / name).unlink(missing_ok=True)
try:
    base.rmdir()
except OSError:
    pass
PY
echo 'Codex Pet uninstalled. Python dependencies and saved position were kept.'
