"""Codex hook parsing and the small in-memory session state machine."""

from __future__ import annotations

from dataclasses import dataclass
import os
import time
from typing import Any

HOOK_STATES = {
    "SessionStart": "idle",
    "UserPromptSubmit": "working",
    "PermissionRequest": "approval",
    "Stop": "done",
    "Interrupt": "interrupted",
    "SessionEnd": "end",
}
STATES = {"idle", "working", "approval", "done", "interrupted", "error", "end"}
PRIORITY = {"approval": 6, "working": 5, "error": 4, "done": 3, "interrupted": 2, "idle": 1}
HOLD_SECONDS = {"done": 6.0, "interrupted": 4.0}


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
    cwd = raw.get("cwd") if isinstance(raw.get("cwd"), str) else ""
    project = (os.path.basename(os.path.normpath(cwd)) or "Codex") if cwd else "Codex"
    if state == "done":
        message = clean_text(raw.get("last_assistant_message"), 140)
    elif state == "approval":
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
    deadline: float | None = None


class SessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}

    def apply(self, event: dict[str, Any]) -> None:
        sid = event["session_id"]
        state = event["state"]
        if state == "end":
            self.sessions.pop(sid, None)
            return
        now = time.monotonic()
        previous = self.sessions.get(sid)
        started = now if state == "working" and (previous is None or previous.state != "working") else (
            previous.started_at if previous else now
        )
        self.sessions[sid] = Session(
            state=state,
            project=event["project"],
            message=event["message"],
            turn_id=event["turn_id"],
            changed_at=now,
            started_at=started,
            deadline=now + HOLD_SECONDS[state] if state in HOLD_SECONDS else None,
        )

    def expire(self) -> bool:
        now = time.monotonic()
        changed = False
        for session in self.sessions.values():
            if session.deadline is not None and now >= session.deadline:
                session.state = "idle"
                session.message = ""
                session.deadline = None
                changed = True
        return changed

    def next_deadline(self) -> float | None:
        deadlines = [s.deadline for s in self.sessions.values() if s.deadline is not None]
        return min(deadlines) if deadlines else None

    def snapshot(self) -> dict[str, Any]:
        if not self.sessions:
            return {"state": "idle", "project": "Codex", "message": "", "elapsed": 0,
                    "working_count": 0, "session_count": 0}
        selected = max(self.sessions.values(), key=lambda s: (PRIORITY[s.state], s.changed_at))
        return {
            "state": selected.state,
            "project": selected.project,
            "message": selected.message,
            "elapsed": max(0, int(time.monotonic() - selected.started_at)) if selected.state == "working" else 0,
            "working_count": sum(s.state == "working" for s in self.sessions.values()),
            "session_count": len(self.sessions),
        }
