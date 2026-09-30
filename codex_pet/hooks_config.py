"""Add and remove only Codex Pet hooks without replacing other Codex settings."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import shutil
import sys
import tomllib

from .runtime import HOME
from .state import HOOK_STATES

CODEX = HOME / ".codex"
TOML = CODEX / "config.toml"
HOOKS = CODEX / "hooks.json"
MANIFEST = HOME / ".config" / "codex-pet" / "install.json"
COMMAND = str(HOME / ".local" / "bin" / "codex-pet-event")
BEGIN = "# BEGIN CODEX PET HOOKS (installed by ~/codex-pet/install.sh)"
END = "# END CODEX PET HOOKS"


def _backup(path: Path) -> None:
    if path.exists():
        name = path.with_name(path.name + ".codex-pet-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
        shutil.copy2(path, name)
        print(f"Backup: {name}")


def _write(path: Path, data: str) -> None:
    temp = path.with_name(path.name + ".codex-pet.tmp")
    temp.write_text(data)
    temp.replace(path)


def _has_inline_hooks(config: dict) -> bool:
    hooks = config.get("hooks")
    return isinstance(hooks, dict) and any(isinstance(groups, list) for groups in hooks.values())


def install() -> None:
    CODEX.mkdir(mode=0o700, parents=True, exist_ok=True)
    MANIFEST.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    config = tomllib.loads(TOML.read_text()) if TOML.exists() else {}
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    if _has_inline_hooks(config):
        content = TOML.read_text()
        block = BEGIN + "\n"
        for name in HOOK_STATES:
            block += (f"[[hooks.{name}]]\n"
                      f"[[hooks.{name}.hooks]]\n"
                      "type = \"command\"\n"
                      f"command = {json.dumps(COMMAND)}\n"
                      "timeout = 3\n\n")
        block += END
        if BEGIN in content and END in content:
            before, remainder = content.split(BEGIN, 1)
            _, after = remainder.split(END, 1)
            new_content = before + block + after
        else:
            new_content = content.rstrip() + "\n\n" + block + "\n"
        if new_content != content:
            tomllib.loads(new_content)
            _backup(TOML)
            _write(TOML, new_content)
        manifest["hooks_mode"] = "inline"
    else:
        existed = HOOKS.exists()
        data = json.loads(HOOKS.read_text()) if existed else {"hooks": {}}
        if not isinstance(data, dict) or not isinstance(data.get("hooks"), dict):
            raise ValueError("~/.codex/hooks.json has an unexpected shape")
        changed = False
        installed_events = set(manifest.get("installed_events", []))
        if manifest.get("hooks_mode") == "json" and "installed_events" not in manifest:
            installed_events.update(HOOK_STATES)  # metadata migration from the first release
        for name in HOOK_STATES:
            groups = data["hooks"].setdefault(name, [])
            if not isinstance(groups, list):
                raise ValueError(f"~/.codex/hooks.json: {name} is not a list")
            if not any(
                isinstance(group, dict) and isinstance(group.get("hooks"), list)
                and any(isinstance(h, dict) and h.get("command") == COMMAND for h in group["hooks"])
                for group in groups
            ):
                groups.append({"hooks": [{"type": "command", "command": COMMAND, "timeout": 3}]})
                changed = True
                installed_events.add(name)
        if changed:
            _backup(HOOKS)
            _write(HOOKS, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        manifest["hooks_mode"] = "json"
        manifest["installed_events"] = sorted(installed_events)
        manifest["created_hooks_file"] = manifest.get("created_hooks_file", not existed)
    _write(MANIFEST, json.dumps(manifest, indent=2) + "\n")
    print(f"Codex hooks installed ({manifest['hooks_mode']})")


def uninstall() -> None:
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    mode = manifest.get("hooks_mode")
    if mode == "inline" and TOML.exists():
        content = TOML.read_text()
        if BEGIN in content and END in content:
            before, remainder = content.split(BEGIN, 1)
            _, after = remainder.split(END, 1)
            _backup(TOML)
            _write(TOML, before.rstrip() + "\n" + after.lstrip("\n"))
    elif mode == "json" and HOOKS.exists():
        data = json.loads(HOOKS.read_text())
        groups_by_event = data.get("hooks", {})
        changed = False
        installed_events = set(manifest.get("installed_events", HOOK_STATES))
        if isinstance(groups_by_event, dict):
            for name, groups in list(groups_by_event.items()):
                if name not in installed_events:
                    continue
                if not isinstance(groups, list):
                    continue
                new_groups = []
                for group in groups:
                    if isinstance(group, dict) and isinstance(group.get("hooks"), list):
                        kept = [h for h in group["hooks"] if not (
                            isinstance(h, dict) and h.get("command") == COMMAND)]
                        if len(kept) != len(group["hooks"]):
                            changed = True
                        if kept:
                            new_groups.append({**group, "hooks": kept})
                    else:
                        new_groups.append(group)
                if new_groups:
                    groups_by_event[name] = new_groups
                else:
                    groups_by_event.pop(name, None)
            if changed:
                _backup(HOOKS)
                if manifest.get("created_hooks_file") and not groups_by_event and set(data) == {"hooks"}:
                    HOOKS.unlink()
                else:
                    _write(HOOKS, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    if MANIFEST.exists():
        MANIFEST.unlink()
    print("Codex Pet hooks removed")


if __name__ == "__main__":
    {"install": install, "uninstall": uninstall}[sys.argv[1]]()
