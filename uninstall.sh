#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCAL_BIN="$HOME/.local/bin"
PATH_BIN="$PREFIX/bin"

"$PROJECT_DIR/bin/codex-pet" stop
PYTHONPATH="$PROJECT_DIR" python -m codex_pet.hooks_config uninstall
for name in codex-pet codex-pet-event; do
  path_target="$PATH_BIN/$name"
  if [ -L "$path_target" ] && [ "$(readlink "$path_target")" = "$LOCAL_BIN/$name" ]; then
    unlink "$path_target"
    path_backup="$HOME/.config/codex-pet/cli-backups/prefix-$name"
    if [ -e "$path_backup" ] || [ -L "$path_backup" ]; then
      mv "$path_backup" "$path_target"
    fi
  fi
  target="$LOCAL_BIN/$name"
  if [ -L "$target" ] && [ "$(readlink -f "$target")" = "$PROJECT_DIR/bin/$name" ]; then
    unlink "$target"
    backup="$HOME/.config/codex-pet/cli-backups/$name"
    if [ -e "$backup" ] || [ -L "$backup" ]; then
      mv "$backup" "$target"
    fi
  fi
done
rmdir "$HOME/.config/codex-pet/cli-backups" 2>/dev/null || true
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
