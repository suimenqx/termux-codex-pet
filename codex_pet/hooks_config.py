"""Add and remove only Codex Pet hooks without replacing other Codex settings."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import re
import shutil
import sys
import tomllib

from .runtime import HOME
from .adapters.codex import HOOK_STATES

CODEX = HOME / ".codex"
TOML = CODEX / "config.toml"
HOOKS = CODEX / "hooks.json"
MANIFEST = HOME / ".config" / "codex-pet" / "install.json"
COMMAND = str(HOME / ".local" / "bin" / "codex-pet-event")
BEGIN = "# BEGIN CODEX PET HOOKS (installed by ~/codex-pet/install.sh)"
END = "# END CODEX PET HOOKS"


def _locations(home: Path | None) -> tuple[Path, Path, Path, Path, str]:
    if home is None:
        return CODEX, TOML, HOOKS, MANIFEST, COMMAND
    codex = home / ".codex"
    return (codex, codex / "config.toml", codex / "hooks.json",
            home / ".config" / "codex-pet" / "install.json",
            str(home / ".local" / "bin" / "codex-pet-event"))


def _backup(path: Path) -> None:
    if path.exists():
        name = path.with_name(path.name + ".codex-pet-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
        shutil.copy2(path, name)
        print(f"Backup: {name}", flush=True)


def _write(path: Path, data: str) -> None:
    temp = path.with_name(path.name + ".codex-pet.tmp")
    temp.write_text(data)
    temp.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o600)
    temp.replace(path)


def _has_inline_hooks(config: dict) -> bool:
    hooks = config.get("hooks")
    return isinstance(hooks, dict) and any(isinstance(groups, list) for groups in hooks.values())


def _state_ids(groups_by_event: dict, source: Path, command: str | None = None) -> set[str]:
    ids = set()
    for event, groups in groups_by_event.items():
        if not isinstance(groups, list):
            continue
        event_name = re.sub(r"(?<!^)(?=[A-Z])", "_", event).lower()
        for gi, group in enumerate(groups):
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                continue
            for hi, hook in enumerate(group["hooks"]):
                if isinstance(hook, dict) and (command is None or hook.get("command") == command):
                    ids.add(f"{source}:{event_name}:{gi}:{hi}")
    return ids


def _read_json_hooks(path: Path) -> tuple[str | None, dict]:
    content = path.read_text() if path.exists() else None
    data = json.loads(content) if content is not None else {"hooks": {}}
    if not isinstance(data, dict) or not isinstance(data.get("hooks"), dict):
        raise ValueError("~/.codex/hooks.json has an unexpected shape")
    return content, data


def _remove_json_hooks(data: dict, source: Path, command: str) -> set[str]:
    removed = _state_ids(data["hooks"], source, command)
    for event, groups in list(data["hooks"].items()):
        if not isinstance(groups, list):
            continue
        kept_groups = []
        changed = False
        for group in groups:
            if isinstance(group, dict) and isinstance(group.get("hooks"), list):
                kept = [h for h in group["hooks"]
                        if not (isinstance(h, dict) and h.get("command") == command)]
                if len(kept) != len(group["hooks"]):
                    changed = True
                    if kept:
                        kept_groups.append({**group, "hooks": kept})
                    continue
            kept_groups.append(group)
        if changed:
            if kept_groups:
                data["hooks"][event] = kept_groups
            else:
                del data["hooks"][event]
    return removed


def _remove_inline_hooks(content: str, source: Path, command: str) -> tuple[str, set[str]]:
    if BEGIN not in content and END not in content:
        return content, set()
    if content.count(BEGIN) != 1 or content.count(END) != 1 or content.index(END) < content.index(BEGIN):
        raise ValueError("Incomplete or duplicate Codex Pet hook markers in config.toml")
    before, remainder = content.split(BEGIN, 1)
    _, after = remainder.split(END, 1)
    updated = before.rstrip() + "\n" + after.lstrip("\n")
    old_ids = _state_ids(tomllib.loads(content).get("hooks", {}), source, command)
    return updated, old_ids - _state_ids(tomllib.loads(updated).get("hooks", {}), source, command)


def _remove_trust(content: str, ids: set[str]) -> str:
    expected = tomllib.loads(content)
    states = expected.get("hooks", {}).get("state", {})
    removed = set(states) & ids
    if not removed:
        return content
    for key in removed:
        del states[key]
    # Keep comments and unrelated TOML verbatim. Codex writes one table per trust record;
    # also accept the equivalent single-line entries under [hooks.state].
    kept = []
    dropping = False
    in_state = False
    for line in content.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("["):
            try:
                table = tomllib.loads(stripped)
            except tomllib.TOMLDecodeError:
                table = {}
            hook_table = table.get("hooks", {})
            state_table = hook_table.get("state", {}) if isinstance(hook_table, dict) else {}
            dropping = bool(set(state_table) & removed)
            in_state = hook_table == {"state": {}}
        elif in_state and stripped and not stripped.startswith("#"):
            try:
                entry = tomllib.loads(stripped)
            except tomllib.TOMLDecodeError:
                entry = {}
            if set(entry) & removed:
                continue
        if not dropping or stripped.startswith("#"):
            kept.append(line)
    updated = "".join(kept)
    actual = tomllib.loads(updated)
    for config in (actual, expected):
        hooks = config.get("hooks", {})
        if hooks.get("state") == {}:
            del hooks["state"]
        if hooks == {}:
            config.pop("hooks", None)
    if actual != expected:
        raise ValueError("Cannot safely remove Pet hook trust metadata; config.toml was not changed")
    return updated


def _save_toml(path: Path, original: str, updated: str) -> None:
    if updated != original:
        tomllib.loads(updated)
        _backup(path)
        _write(path, updated)


def _save_json_hooks(path: Path, original: str | None, data: dict, *, remove_empty: bool) -> None:
    if remove_empty and data == {"hooks": {}}:
        if original is not None:
            _backup(path)
            path.unlink()
    elif original is None or data != json.loads(original):
        _backup(path)
        _write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def install(home: Path | None = None) -> None:
    codex, toml, hooks, manifest_path, command = _locations(home)
    codex.mkdir(mode=0o700, parents=True, exist_ok=True)
    manifest_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    original_toml = toml.read_text() if toml.exists() else ""
    content = original_toml
    config = tomllib.loads(content)
    _remove_inline_hooks(content, toml, command)
    original_json, data = _read_json_hooks(hooks)
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if _has_inline_hooks(config):
        removed = _remove_json_hooks(data, hooks, command)
        content = _remove_trust(content, removed)
        block = BEGIN + "\n"
        for name in HOOK_STATES:
            block += (f"[[hooks.{name}]]\n"
                      f"[[hooks.{name}.hooks]]\n"
                      "type = \"command\"\n"
                      f"command = {json.dumps(command)}\n"
                      "timeout = 3\n\n")
        block += END
        if BEGIN in content and END in content:
            before, remainder = content.split(BEGIN, 1)
            _, after = remainder.split(END, 1)
            new_content = before + block + after
        else:
            new_content = content.rstrip() + "\n\n" + block + "\n"
        _remove_inline_hooks(new_content, toml, command)  # Validate the managed marker pair.
        _save_toml(toml, original_toml, new_content)
        _save_json_hooks(hooks, original_json, data,
                         remove_empty=manifest.get("created_hooks_file", False) or original_json is None)
        manifest["hooks_mode"] = "inline"
        manifest["hook_state_ids"] = sorted(_state_ids(tomllib.loads(new_content)["hooks"], toml, command))
    else:
        existed = original_json is not None
        installed_events = set(manifest.get("installed_events", []))
        if manifest.get("hooks_mode") == "json" and "installed_events" not in manifest:
            installed_events.update(HOOK_STATES)  # metadata migration from the first release
        for name in HOOK_STATES:
            groups = data["hooks"].setdefault(name, [])
            if not isinstance(groups, list):
                raise ValueError(f"~/.codex/hooks.json: {name} is not a list")
            if not any(
                isinstance(group, dict) and isinstance(group.get("hooks"), list)
                and any(isinstance(h, dict) and h.get("command") == command for h in group["hooks"])
                for group in groups
            ):
                groups.append({"hooks": [{"type": "command", "command": command, "timeout": 3}]})
                installed_events.add(name)
        _save_json_hooks(hooks, original_json, data, remove_empty=False)
        manifest["hooks_mode"] = "json"
        manifest["installed_events"] = sorted(installed_events)
        manifest["created_hooks_file"] = manifest.get("created_hooks_file", not existed)
        manifest["hook_state_ids"] = sorted(_state_ids(data["hooks"], hooks, command))
    _write(manifest_path, json.dumps(manifest, indent=2) + "\n")
    print(f"Codex hooks installed ({manifest['hooks_mode']})", flush=True)


def uninstall(home: Path | None = None) -> None:
    _, toml, hooks, manifest_path, command = _locations(home)
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    original_toml = toml.read_text() if toml.exists() else ""
    content, removed = _remove_inline_hooks(original_toml, toml, command)
    original_json, data = _read_json_hooks(hooks)
    removed.update(_remove_json_hooks(data, hooks, command))
    # The manifest allows cleanup even when the hook source was already removed.
    live_ids = (_state_ids(tomllib.loads(content).get("hooks", {}), toml)
                | _state_ids(data["hooks"], hooks))
    removed.update(set(manifest.get("hook_state_ids", [])) - live_ids)
    content = _remove_trust(content, removed)
    _save_toml(toml, original_toml, content)
    if original_json is not None:
        _save_json_hooks(hooks, original_json, data,
                         remove_empty=manifest.get("created_hooks_file", False))
    if manifest_path.exists():
        manifest_path.unlink()
    print("Codex Pet hooks removed", flush=True)


if __name__ == "__main__":
    {"install": install, "uninstall": uninstall}[sys.argv[1]]()
