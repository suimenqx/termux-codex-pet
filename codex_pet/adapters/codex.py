"""Codex hook and legacy application IPC normalization; no images or native UI."""
from __future__ import annotations
import os
import time
from typing import Any

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
              "PermissionRequest": "activity", "PostToolUse": "activity",
              "Stop": "turn_end", "Interrupt": "turn_end", "SessionEnd": "session_end"}
KIND_STATES = {"session_start": {"idle"}, "turn_start": {"running"},
               "activity": {"running", "needs_input"}, "turn_end": {"ready", "idle"},
               "session_end": {"end"}, "manual": STATES}


def clean_text(value: Any, limit: int = 160) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


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
        "timestamp": time.time(),
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
        "timestamp": time.time(),
    }

