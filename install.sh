#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
LOCAL_BIN="$HOME/.local/bin"
PATH_BIN="$PREFIX/bin"
APP_DIR="$HOME/.local/share/codex-pet"
CONFIG_DIR="$HOME/.config/codex-pet"
RUNTIME_DIR="$HOME/.cache/codex-pet"

if ! command -v python >/dev/null 2>&1; then
  pkg install -y python
fi
if ! python -c 'import ctypes; ctypes.CDLL("libpng16.so")' >/dev/null 2>&1; then
  pkg install -y libpng
fi
if ! python -c 'import termuxgui' >/dev/null 2>&1; then
  python -m pip install termuxgui
fi

mkdir -p "$LOCAL_BIN" "$PATH_BIN" "$CONFIG_DIR" "$RUNTIME_DIR"
chmod 700 "$CONFIG_DIR" "$RUNTIME_DIR"
if [ ! -e "$CONFIG_DIR/config.json" ]; then
  printf '{"position":{"x":700,"y":420}}\n' > "$CONFIG_DIR/config.json"
fi

for name in codex-pet codex-pet-event; do
  path_target="$PATH_BIN/$name"
  if [ -d "$path_target" ] && [ ! -L "$path_target" ]; then
    echo "Cannot install over directory: $path_target" >&2
    exit 1
  fi
done

# Deploy an isolated private copy before changing the active runtime pointer.
PYTHONPATH="$PROJECT_DIR" python -m codex_pet.deployment deploy --source "$PROJECT_DIR"

for name in codex-pet codex-pet-event; do
  path_target="$PATH_BIN/$name"
  path_backup="$CONFIG_DIR/cli-backups/prefix-$name"
  if [ -e "$path_target" ] || [ -L "$path_target" ]; then
    if [ "$(readlink "$path_target" 2>/dev/null || true)" != "$LOCAL_BIN/$name" ]; then
      mkdir -p "$CONFIG_DIR/cli-backups"
      if [ ! -e "$path_backup" ] && [ ! -L "$path_backup" ]; then
        cp -a "$path_target" "$path_backup"
      fi
    fi
  fi
  ln -sfn "$LOCAL_BIN/$name" "$path_target"
done

PYTHONPATH="$(readlink -f "$APP_DIR/current")" python -m codex_pet.hooks_config install
if ! "$LOCAL_BIN/codex-pet" restart; then
  if PYTHONPATH="$PROJECT_DIR" python -m codex_pet.deployment rollback --source "$PROJECT_DIR"; then
    "$LOCAL_BIN/codex-pet" restart || true
  fi
  exit 1
fi
"$LOCAL_BIN/codex-pet" status
"$LOCAL_BIN/codex-pet-event" --state idle --session-id install-smoke --project 'Codex Pet'
"$LOCAL_BIN/codex-pet" status
printf '%s\n' '{"hook_event_name":"SessionEnd","session_id":"install-smoke"}' | "$LOCAL_BIN/codex-pet-event"
echo 'Install and IPC smoke test complete. Review/trust hooks with /hooks in a new Codex session.'
