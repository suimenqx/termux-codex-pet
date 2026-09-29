"""Normalize Codex lifecycle signals into the Pet's small session state model."""

from __future__ import annotations

from dataclasses import dataclass
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
PRIORITY = {"needs_input": 5, "blocked": 4, "ready": 3, "running": 2, "idle": 1}


def clean_text(value: Any, limit: int = 160) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def event_from_hook(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    name = raw.get("hook_event_name")
    state = HOOK_STATES.get(name)
    if state is None:
        return None
    # Compaction is an in-turn lifecycle event. It must not make a live thread
    # look idle while Codex prepares the continuation request.
    if name == "SessionStart" and raw.get("source") == "compact":
        return None
    cwd = raw.get("cwd") if isinstance(raw.get("cwd"), str) else ""
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
        "session_id": clean_text(raw.get("session_id"), 120) or "default",
        "turn_id": clean_text(raw.get("turn_id"), 120),
        "cwd": cwd[:500],
        "project": project[:60],
        "message": message,
        "starts_turn": name == "UserPromptSubmit",
        "timestamp": time.time(),
    }


def direct_event(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or raw.get("state") not in STATES:
        return None
    cwd = raw.get("cwd") if isinstance(raw.get("cwd"), str) else ""
    return {
        "state": raw["state"],
        "session_id": clean_text(raw.get("session_id"), 120) or "default",
        "turn_id": clean_text(raw.get("turn_id"), 120),
        "cwd": cwd[:500],
        "project": clean_text(raw.get("project"), 60)
        or ((os.path.basename(os.path.normpath(cwd)) or "Codex") if cwd else "Codex"),
        "message": clean_text(raw.get("message"), 140),
        "starts_turn": raw.get("starts_turn") is True,
        "timestamp": time.time(),
    }


@dataclass
class Session:
    state: str
    project: str
    message: str
    turn_id: str
    changed_at: float
    started_at: float


class SessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}

    def apply(self, event: dict[str, Any]) -> bool:
        """Apply an event, ignoring late events from a superseded turn."""
        sid = event["session_id"]
        state = event["state"]
        if state == "end":
            self.sessions.pop(sid, None)
            return True

        now = time.monotonic()
        previous = self.sessions.get(sid)
        turn_id = event["turn_id"]
        turn_changed = bool(previous and turn_id and previous.turn_id != turn_id)
        if turn_changed and not event.get("starts_turn"):
            return False

        new_turn = turn_changed
        started = now if state == "running" and (
            previous is None or previous.state != "running" or new_turn
        ) else (previous.started_at if previous else now)
        self.sessions[sid] = Session(
            state=state,
            project=event["project"],
            message=event["message"],
            turn_id=turn_id or (previous.turn_id if previous else ""),
            changed_at=now,
            started_at=started,
        )
        return True

    def mark_ready_read(self, session_id: str | None = None) -> bool:
        """Acknowledge the visible Ready session when its detail card is opened."""
        if session_id is None:
            current = self.snapshot()
            session_id = current.get("session_id")
        session = self.sessions.get(session_id) if session_id else None
        if session is None or session.state != "ready":
            return False
        session.state = "idle"
        session.message = ""
        session.changed_at = time.monotonic()
        return True

    def snapshot(self) -> dict[str, Any]:
        if not self.sessions:
            return {"state": "idle", "project": "Codex", "message": "", "elapsed": 0,
                    "running_count": 0, "session_count": 0, "session_id": None}
        selected_id, selected = max(
            self.sessions.items(), key=lambda item: (PRIORITY[item[1].state], item[1].changed_at)
        )
        return {
            "state": selected.state,
            "project": selected.project,
            "message": selected.message,
            "elapsed": max(0, int(time.monotonic() - selected.started_at))
            if selected.state == "running" else 0,
            "running_count": sum(s.state == "running" for s in self.sessions.values()),
            "session_count": len(self.sessions),
            "session_id": selected_id,
        }
