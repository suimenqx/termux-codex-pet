"""Normalize Codex lifecycle signals into the Pet's small session state model."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

PRIORITY = {"needs_input": 5, "blocked": 4, "ready": 3, "running": 2, "idle": 1}


@dataclass
class Session:
    state: str
    project: str
    message: str
    turn_id: str
    changed_at: float
    started_at: float
    turn_finished: bool = False


class SessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}

    def apply(self, event: dict[str, Any]) -> bool:
        """Apply observed lifecycle evidence without reopening a finished turn."""
        sid = event["session_id"]
        state = event["state"]
        if state == "end":
            self.sessions.pop(sid, None)
            return True

        now = time.monotonic()
        previous = self.sessions.get(sid)
        turn_id = event["turn_id"]
        # An unknown ID is not evidence of a different turn (for example after
        # a manual state restore). Adopt the first observed ID, including Stop.
        turn_changed = bool(previous and previous.turn_id and turn_id
                            and previous.turn_id != turn_id)
        if turn_changed and event["kind"] != "turn_start":
            return False

        if (previous and previous.turn_finished and event["kind"] != "turn_start"
                and event["kind"] == "activity"):
            return False

        new_turn = turn_changed or event["kind"] == "turn_start"
        started = now if state == "running" and (
            previous is None or previous.state != "running" or new_turn
        ) else (previous.started_at if previous else now)
        self.sessions[sid] = Session(
            state=state,
            project=event["project"],
            message=event["message"],
            turn_id=turn_id if new_turn else turn_id or (previous.turn_id if previous else ""),
            changed_at=now,
            started_at=started,
            turn_finished=event["kind"] == "turn_end",
        )
        return True

    def snapshot(self) -> dict[str, Any]:
        if not self.sessions:
            return {"state": "idle", "project": "Codex", "message": "", "elapsed": 0,
                    "running_count": 0, "session_count": 0, "session_id": None,
                    "turn_id": ""}
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
            "turn_id": selected.turn_id,
        }
