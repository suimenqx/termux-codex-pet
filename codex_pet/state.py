"""Observed activity, pending approvals, ordering and explicit uncertainty."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import time
from typing import Any
from .adapters.codex import BOOT_ID

PRIORITY = {'needs_input': 6, 'blocked': 5, 'unknown': 4,
            'running': 3, 'ready': 2, 'idle': 1}


@dataclass
class Session:
    state: str
    project: str
    message: str
    turn_id: str
    changed_at: float
    started_at: float
    turn_finished: bool = False
    timestamp: float = 0
    confidence: str = 'observed'
    reason: str = ''
    pending_permissions: dict[str, list[float]] = field(default_factory=dict)
    completed_permissions: dict[str, list[float]] = field(default_factory=dict)
    completed_tools: list[str] = field(default_factory=list)
    retired_turns: list[str] = field(default_factory=list)
    evidence: str = ''
    turn_started_timestamp: float = 0
    boot_id: str = ''

    @property
    def visible_state(self) -> str:
        return self.state if self.confidence in ('observed', 'requested') else 'unknown'


class SessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.ended: dict[str, dict[str, Any]] = {}

    def apply(self, event: dict[str, Any]) -> bool:
        sid, state, kind = event['session_id'], event['state'], event['kind']
        boot_id = event.get('boot_id', '')
        stamp = event['emitted_monotonic_ns'] / 1_000_000_000 if boot_id else event['timestamp']
        previous = self.sessions.get(sid)
        manual = kind == 'manual'
        if previous and previous.boot_id != boot_id:
            if boot_id != BOOT_ID:
                return False
            previous = None
        activity = kind in ('approval_request', 'tool_finished')
        cutoff = previous.turn_started_timestamp if previous and activity else previous.timestamp if previous else 0
        ended = self.ended.get(sid, {})
        end_cutoff = ended.get('timestamp', 0) if ended.get('boot_id') == boot_id else 0
        if not manual and stamp < max(end_cutoff, cutoff):
            return False
        if previous and not manual and previous.confidence == 'recovered' and stamp <= previous.timestamp:
            return False
        turn_id = event['turn_id']
        if state == 'end':
            if previous and previous.turn_id and turn_id and previous.turn_id != turn_id:
                return False
            self.sessions.pop(sid, None)
            self.ended[sid] = {'boot_id': boot_id, 'timestamp': stamp}
            if len(self.ended) > 4096:
                self.ended.pop(next(iter(self.ended)))
            return True
        if previous:
            changed = bool(previous.turn_id and turn_id and previous.turn_id != turn_id)
            if changed and kind != 'turn_start':
                return False
        if previous and not manual:
            if kind == 'session_start' and previous.state in ('running', 'needs_input'):
                return False
            if kind == 'turn_start' and turn_id in previous.retired_turns:
                return False
            if previous.turn_finished and kind in ('activity', 'approval_request', 'tool_finished'):
                return False
            if (previous.turn_id and not turn_id
                    and kind in ('turn_end', 'activity', 'approval_request', 'tool_finished')):
                previous.confidence = 'uncertain'
                previous.reason = 'event missing turn_id'
                return False

        now = time.monotonic()
        new_turn = kind == 'turn_start'
        retired = list(previous.retired_turns) if previous else []
        if previous and new_turn and previous.turn_id and previous.turn_id != turn_id:
            retired = (retired + [previous.turn_id])[-64:]
        pending = {key: list(value) for key, value in previous.pending_permissions.items()} if previous and not new_turn else {}
        finished = {key: list(value) for key, value in previous.completed_permissions.items()} if previous and not new_turn else {}
        completed = list(previous.completed_tools) if previous and not new_turn else []
        key, tool_id = event.get('tool_key', ''), event.get('tool_use_id', '')
        if kind == 'approval_request':
            matching = next((value for value in finished.get(key, []) if value >= stamp), None)
            if matching is not None:
                finished[key].remove(matching)
                if not finished[key]:
                    del finished[key]
            else:
                pending.setdefault(key, []).append(stamp)
            state = 'needs_input' if pending else 'running'
        elif kind == 'tool_finished':
            if tool_id and tool_id in completed:
                return False
            if tool_id:
                completed = (completed + [tool_id])[-512:]
            matching = next((value for value in pending.get(key, []) if value <= stamp), None)
            if matching is not None:
                pending[key].remove(matching)
                if not pending[key]:
                    del pending[key]
            else:
                finished.setdefault(key, []).append(stamp)
            state = 'needs_input' if pending else 'running'
        if kind == 'turn_end' or manual:
            pending = {}
            finished = {}
        started = now if state == 'running' and (
            previous is None or previous.state != 'running' or new_turn
        ) else (previous.started_at if previous else now)
        self.sessions[sid] = Session(
            state=state, project=event['project'],
            message=event['message'] or (previous.message if previous and pending else ''),
            turn_id=turn_id if new_turn else turn_id or (previous.turn_id if previous else ''),
            changed_at=now, started_at=started, turn_finished=kind == 'turn_end',
            timestamp=max(stamp, previous.timestamp if previous else 0),
            pending_permissions=pending, completed_permissions=finished, completed_tools=completed, retired_turns=retired,
            confidence='requested' if pending else 'observed',
            reason='approval prompt resolution is not exposed by hooks' if pending else '',
            evidence='PermissionRequest (unresolved)' if pending else event.get('hook_event_name') or kind,
            turn_started_timestamp=stamp if new_turn or previous is None else previous.turn_started_timestamp,
            boot_id=boot_id)
        if boot_id != BOOT_ID:
            self.sessions[sid].confidence = 'recovered'
            self.sessions[sid].reason = 'evidence came from an earlier device boot'
        self.ended.pop(sid, None)
        return True

    def checkpoint(self) -> dict[str, Any]:
        return {'format': 1, 'sessions': {sid: asdict(value) for sid, value in self.sessions.items()},
                'ended': self.ended}

    @classmethod
    def restore(cls, saved: dict[str, Any] | None) -> SessionStore:
        store = cls()
        if saved is None:
            return store
        if not isinstance(saved, dict) or saved.get('format') != 1 or not isinstance(saved.get('sessions'), dict):
            raise ValueError('Invalid session checkpoint')
        ended = saved.get('ended', {})
        if not isinstance(ended, dict) or any(not isinstance(value, dict) for value in ended.values()):
            raise ValueError('Invalid ended-session checkpoint')
        store.ended = dict(ended)
        for sid, data in saved['sessions'].items():
            value = Session(**data)
            if value.state not in PRIORITY or value.confidence not in ('observed', 'requested', 'uncertain', 'recovered'):
                raise ValueError('Invalid checkpoint state')
            if (not isinstance(value.pending_permissions, dict) or not isinstance(value.completed_permissions, dict)
                    or any(not isinstance(times, list) or any(not isinstance(stamp, (int, float)) for stamp in times)
                           for times in [*value.pending_permissions.values(), *value.completed_permissions.values()])
                    or not isinstance(value.retired_turns, list) or not isinstance(value.completed_tools, list)
                    or not isinstance(value.timestamp, (int, float)) or not isinstance(value.boot_id, str)):
                raise ValueError('Invalid checkpoint approval metadata')
            value.confidence = 'recovered'
            value.reason = 'restored evidence awaits a fresh lifecycle event'
            store.sessions[sid] = value
        return store

    def snapshot(self) -> dict[str, Any]:
        counts = {name + '_count': sum(value.visible_state == name for value in self.sessions.values())
                  for name in ('running', 'ready', 'needs_input', 'unknown')}
        if not self.sessions:
            return {'state': 'idle', 'project': 'Codex', 'message': '', 'elapsed': 0,
                    **counts, 'session_count': 0, 'session_id': None, 'turn_id': '',
                    'confidence': 'observed', 'state_reason': '', 'state_evidence': 'no sessions'}
        selected_id, selected = max(self.sessions.items(), key=lambda item: (
            PRIORITY[item[1].visible_state], item[1].changed_at))
        return {'state': selected.visible_state, 'project': selected.project, 'message': selected.message,
                'elapsed': max(0, int(time.monotonic() - selected.started_at)) if selected.state == 'running' else 0,
                **counts, 'session_count': len(self.sessions), 'session_id': selected_id,
                'turn_id': selected.turn_id, 'confidence': selected.confidence,
                'state_reason': selected.reason, 'state_evidence': selected.evidence,
                'pending_approvals': sum(len(value) for value in selected.pending_permissions.values()),
                'outcome': 'unknown'}
