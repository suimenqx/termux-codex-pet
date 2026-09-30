#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCAL_BIN="$HOME/.local/bin"
PATH_BIN="$PREFIX/bin"
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
chmod +x "$PROJECT_DIR/bin/codex-pet" "$PROJECT_DIR/bin/codex-pet-event"

for name in codex-pet codex-pet-event; do
  target="$LOCAL_BIN/$name"
  backup="$CONFIG_DIR/cli-backups/$name"
  if [ -d "$target" ] && [ ! -L "$target" ]; then
    echo "Cannot install over directory: $target" >&2
    exit 1
  fi
  if [ -e "$target" ] || [ -L "$target" ]; then
    if [ "$(readlink -f "$target")" != "$PROJECT_DIR/bin/$name" ]; then
      mkdir -p "$CONFIG_DIR/cli-backups"
      if [ ! -e "$backup" ] && [ ! -L "$backup" ]; then
        cp -a "$target" "$backup"
      fi
    fi
  fi
  ln -sfn "$PROJECT_DIR/bin/$name" "$target"

  path_target="$PATH_BIN/$name"
  path_backup="$CONFIG_DIR/cli-backups/prefix-$name"
  if [ -d "$path_target" ] && [ ! -L "$path_target" ]; then
    echo "Cannot install over directory: $path_target" >&2
    exit 1
  fi
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

PYTHONPATH="$PROJECT_DIR" python -m codex_pet.hooks_config install
"$LOCAL_BIN/codex-pet" start
"$LOCAL_BIN/codex-pet" status
"$LOCAL_BIN/codex-pet-event" --state idle --session-id install-smoke --project 'Codex Pet'
"$LOCAL_BIN/codex-pet" status
printf '%s\n' '{"hook_event_name":"SessionEnd","session_id":"install-smoke"}' | "$LOCAL_BIN/codex-pet-event"
echo 'Install and IPC smoke test complete. Review/trust hooks with /hooks in a new Codex session.'
