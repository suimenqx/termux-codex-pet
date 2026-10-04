"""Codex hook and legacy application IPC normalization; no images or native UI."""
from __future__ import annotations
import os
import time
import hashlib
import json
import math
import uuid
from pathlib import Path
from typing import Any

try:
    BOOT_ID = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
except OSError:
    BOOT_ID = ''

# User-facing activity states follow the four states documented for Codex Pets.
# ``idle`` means there is no active Pet activity; ``end`` is an internal event.
HOOK_STATES = {
    "SessionStart": "idle",
    "UserPromptSubmit": "running",
    "PermissionRequest": "needs_input",
    "PostToolUse": "running",
    "Stop": "ready",
    "Interrupt": "idle",
    "SessionEnd": "end",
}
STATES = {"idle", "running", "needs_input", "ready", "blocked", "end"}

HOOK_KINDS = {"SessionStart": "session_start", "UserPromptSubmit": "turn_start",
              "PermissionRequest": "approval_request", "PostToolUse": "tool_finished",
              "Stop": "turn_end", "Interrupt": "turn_end", "SessionEnd": "session_end"}
KIND_STATES = {"session_start": {"idle"}, "turn_start": {"running"},
               "approval_request": {"needs_input"}, "tool_finished": {"running"},
               "activity": {"running", "needs_input"}, "turn_end": {"ready", "idle"},
               "session_end": {"end"}, "instance_end": {"end"}, "manual": STATES}


def clean_text(value: Any, limit: int = 160) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _delivery_fields(raw: dict[str, Any]) -> dict[str, Any]:
    stamp = raw.get('timestamp')
    try:
        stamp = float(stamp) if isinstance(stamp, (float, int)) and not isinstance(stamp, bool) else 0
    except OverflowError:
        stamp = 0
    if not math.isfinite(stamp) or stamp <= 0 or stamp > time.time() + 60:
        stamp = time.time()
    monotonic = raw.get('emitted_monotonic_ns')
    if type(monotonic) is not int or not 0 <= monotonic <= 2**63 - 1:
        monotonic = time.monotonic_ns()
    return {'event_id': clean_text(raw.get('event_id'), 80) or uuid.uuid4().hex,
            'timestamp': stamp, 'emitted_monotonic_ns': monotonic,
            'boot_id': clean_text(raw.get('boot_id'), 80) or BOOT_ID}


def _instance_fields(raw: dict[str, Any]) -> dict[str, Any]:
    pid, ticks = raw.get('producer_pid'), raw.get('producer_start_ticks')
    return {'instance_id': clean_text(raw.get('instance_id'), 80),
            'producer_pid': pid if type(pid) is int and 0 < pid < 2**31 else 0,
            'producer_start_ticks': ticks if type(ticks) is int and 0 < ticks < 2**63 else 0,
            'producer_boot_id': clean_text(raw.get('producer_boot_id'), 80),
            'instance_tracking': 'orphan' if raw.get('instance_tracking') == 'orphan' else ''}


def _tool_key(raw: dict[str, Any]) -> str:
    name = clean_text(raw.get('tool_name'), 120)
    if not name:
        return ''
    value = raw.get('tool_input')
    if isinstance(value, dict):
        value = {key: val for key, val in value.items() if key != 'description'}
    # Correlate the actual input, never persist commands or tool secrets.
    encoded = json.dumps([name, value], sort_keys=True, ensure_ascii=False,
                         separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def event_from_hook(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    name = raw.get("hook_event_name")
    if not isinstance(name, str):
        return None
    state = HOOK_STATES.get(name)
    if state is None:
        return None
    # Compaction is an in-turn lifecycle event. It must not make a live thread
    # look idle while Codex prepares the continuation request.
    if name == "SessionStart" and raw.get("source") == "compact":
        return None
    value = raw.get("cwd")
    cwd = value if isinstance(value, str) else ""
    project = (os.path.basename(os.path.normpath(cwd)) or "Codex") if cwd else "Codex"
    if state == "ready":
        message = clean_text(raw.get("last_assistant_message"), 140)
    elif state == "needs_input":
        tool_input = raw.get("tool_input")
        message = clean_text(tool_input.get("description") if isinstance(tool_input, dict) else None, 120)
    else:
        message = ""
    return {
        "state": state,
        "kind": HOOK_KINDS[name],
        "source": "codex",
        "session_id": clean_text(raw.get("session_id"), 120) or "default",
        "turn_id": clean_text(raw.get("turn_id"), 120),
        "cwd": cwd[:500],
        "project": project[:60],
        "message": message,
        "starts_turn": name == "UserPromptSubmit",
        "hook_event_name": name,
        "tool_key": _tool_key(raw),
        "tool_use_id": clean_text(raw.get('tool_use_id'), 120),
        **_instance_fields(raw),
        **_delivery_fields(raw),
    }


def direct_event(raw: Any) -> dict[str, Any] | None:
    if (not isinstance(raw, dict) or not isinstance(raw.get("state"), str)
            or raw["state"] not in STATES):
        return None
    value = raw.get("cwd")
    cwd = value if isinstance(value, str) else ""
    hook_name = clean_text(raw.get("hook_event_name"), 40)
    if HOOK_STATES.get(hook_name) != raw["state"]:
        hook_name = ""
    kind = raw.get("kind")
    if kind is None:
        kind = HOOK_KINDS.get(hook_name, "turn_start" if raw.get("starts_turn") is True else "manual")
    if not isinstance(kind, str) or kind not in KIND_STATES or raw["state"] not in KIND_STATES[kind]:
        return None
    return {
        "state": raw["state"],
        "kind": kind,
        "source": clean_text(raw.get("source"), 40) or ("codex" if hook_name else "manual"),
        "session_id": clean_text(raw.get("session_id"), 120) or "default",
        "turn_id": clean_text(raw.get("turn_id"), 120),
        "cwd": cwd[:500],
        "project": clean_text(raw.get("project"), 60)
        or ((os.path.basename(os.path.normpath(cwd)) or "Codex") if cwd else "Codex"),
        "message": clean_text(raw.get("message"), 140),
        "starts_turn": kind == "turn_start",
        "hook_event_name": hook_name,
        "tool_key": clean_text(raw.get('tool_key'), 64),
        "tool_use_id": clean_text(raw.get('tool_use_id'), 120),
        **_instance_fields(raw),
        **_delivery_fields(raw),
    }
