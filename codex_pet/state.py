"""Observed activity, pending approvals, ordering and explicit uncertainty."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import time
from typing import Any
from .adapters.codex import BOOT_ID, SHARED_INSTANCE_PREFIX

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
    session_id: str = ''
    instance_id: str = ''
    producer_pid: int = 0
    producer_start_ticks: int = 0
    producer_boot_id: str = ''
    monitor_error: str = ''

    @property
    def visible_state(self) -> str:
        return self.state if not self.monitor_error and self.confidence in ('observed', 'requested') else 'unknown'


class SessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.ended: dict[str, dict[str, Any]] = {}
        self.closed_instances: dict[str, bool] = {}

    @staticmethod
    def _key(session_id: str, instance_id: str) -> str:
        return json.dumps([session_id, instance_id], separators=(',', ':')) if instance_id else session_id

    def close_instance(self, instance_id: str) -> bool:
        if not instance_id:
            return False
        changed = False
        for key, value in list(self.sessions.items()):
            if value.instance_id == instance_id:
                del self.sessions[key]
                changed = True
        self.closed_instances[instance_id] = True
        if len(self.closed_instances) > 4096:
            self.closed_instances.pop(next(iter(self.closed_instances)))
        return changed

    def apply(self, event: dict[str, Any]) -> bool:
        session_id, state, kind = event['session_id'], event['state'], event['kind']
        instance_id = event.get('instance_id', '')
        if event.get('instance_tracking') == 'orphan':
            return False
        if kind == 'instance_end':
            return self.close_instance(instance_id)
        if instance_id in self.closed_instances:
            return False
        sid = self._key(session_id, instance_id)
        # Missing owner metadata cannot affect another process's qualified row.
        if not instance_id and kind != 'manual' and any(
                value.session_id == session_id and value.instance_id for value in self.sessions.values()):
            return False
        boot_id = event.get('boot_id', '')
        stamp = event['emitted_monotonic_ns'] / 1_000_000_000 if boot_id else event['timestamp']
        legacy = self.sessions.get(session_id) if instance_id else None
        if (legacy and legacy.confidence == 'recovered' and not legacy.instance_id
                and (kind == 'turn_start' or legacy.turn_id == event['turn_id'])):
            if boot_id == legacy.boot_id and stamp <= legacy.timestamp:
                return False
            if boot_id != legacy.boot_id and boot_id != BOOT_ID:
                return False
            # Upgrade an old aggregate checkpoint only with matching fresh
            # evidence from this boot; old-boot approval metadata is obsolete.
            if kind != 'turn_start' and boot_id == legacy.boot_id:
                legacy.instance_id = instance_id
                legacy.session_id = session_id
                self.sessions[sid] = legacy
            del self.sessions[session_id]
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
            boot_id=boot_id, session_id=session_id, instance_id=instance_id,
            producer_pid=event.get('producer_pid', 0) or (previous.producer_pid if previous else 0),
            producer_start_ticks=event.get('producer_start_ticks', 0) or (previous.producer_start_ticks if previous else 0),
            producer_boot_id=event.get('producer_boot_id', '') or (previous.producer_boot_id if previous else ''))
        if boot_id != BOOT_ID:
            self.sessions[sid].confidence = 'recovered'
            self.sessions[sid].reason = 'evidence came from an earlier device boot'
        self.ended.pop(sid, None)
        return True

    def checkpoint(self) -> dict[str, Any]:
        return {'format': 2, 'sessions': {sid: asdict(value) for sid, value in self.sessions.items()},
                'ended': self.ended, 'closed_instances': list(self.closed_instances)}

    @classmethod
    def restore(cls, saved: dict[str, Any] | None) -> SessionStore:
        store = cls()
        if saved is None:
            return store
        if not isinstance(saved, dict) or saved.get('format') not in (1, 2) or not isinstance(saved.get('sessions'), dict):
            raise ValueError('Invalid session checkpoint')
        ended = saved.get('ended', {})
        if not isinstance(ended, dict) or any(not isinstance(value, dict) for value in ended.values()):
            raise ValueError('Invalid ended-session checkpoint')
        store.ended = dict(ended)
        closed = saved.get('closed_instances', [])
        if not isinstance(closed, list) or any(not isinstance(owner, str) for owner in closed):
            raise ValueError('Invalid closed-instance checkpoint')
        store.closed_instances = dict.fromkeys(closed[-4096:], True)
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
            if (not isinstance(value.instance_id, str) or not isinstance(value.session_id, str)
                    or type(value.producer_pid) is not int or not 0 <= value.producer_pid < 2**31
                    or type(value.producer_start_ticks) is not int or not 0 <= value.producer_start_ticks < 2**63
                    or not isinstance(value.producer_boot_id, str) or not isinstance(value.monitor_error, str)):
                raise ValueError('Invalid checkpoint process metadata')
            value.confidence = 'recovered'
            value.reason = 'restored evidence awaits a fresh lifecycle event'
            value.session_id = value.session_id or sid
            store.sessions[sid] = value
        return store

    def snapshot(self) -> dict[str, Any]:
        counts = {name + '_count': sum(value.visible_state == name for value in self.sessions.values())
                  for name in ('running', 'ready', 'needs_input', 'unknown')}
        rows = sorted(self.sessions.items(), key=lambda item: (
            PRIORITY[item[1].visible_state], item[1].changed_at), reverse=True)
        details: list[dict[str, Any]] = []
        budget = 0
        for _, value in rows:
            row = {'session_id': value.session_id, 'instance_id': value.instance_id,
                   'project': value.project, 'turn_id': value.turn_id,
                   'state': value.visible_state, 'producer_pid': value.producer_pid,
                   'confidence': 'uncertain' if value.monitor_error else value.confidence,
                   'state_reason': value.monitor_error or value.reason, 'state_evidence': value.evidence,
                   'pending_approvals': sum(len(times) for times in value.pending_permissions.values()),
                   'process_tracking': 'unavailable' if value.monitor_error else
                   'shared' if value.producer_pid and value.instance_id.startswith(SHARED_INSTANCE_PREFIX) else
                   'identified' if value.producer_pid else 'legacy'}
            size = len(json.dumps(row).encode())
            if len(details) >= 32 or budget + size > 32768:
                break
            details.append(row)
            budget += size
        totals = {'instance_count': len({('process', value.instance_id) if value.instance_id else ('legacy', key)
                                         for key, value in rows}),
                  'session_count': len({value.session_id or key for key, value in rows}),
                  'entry_count': len(rows), 'instances': details, 'instances_truncated': len(details) < len(rows),
                  'pending_approvals': sum(len(times) for _, value in rows for times in value.pending_permissions.values())}
        if not self.sessions:
            return {'state': 'idle', 'project': 'Codex', 'message': '', 'elapsed': 0,
                    **counts, **totals, 'session_id': None, 'instance_id': '', 'turn_id': '',
                    'selected_pending_approvals': 0,
                    'confidence': 'observed', 'state_reason': '', 'state_evidence': 'no sessions'}
        selected_id, selected = rows[0]
        return {'state': selected.visible_state, 'project': selected.project, 'message': selected.message,
                'elapsed': max(0, int(time.monotonic() - selected.started_at)) if selected.state == 'running' else 0,
                **counts, **totals, 'session_id': selected.session_id or selected_id,
                'instance_id': selected.instance_id, 'turn_id': selected.turn_id,
                'confidence': 'uncertain' if selected.monitor_error else selected.confidence,
                'state_reason': selected.monitor_error or selected.reason, 'state_evidence': selected.evidence,
                'selected_pending_approvals': sum(len(value) for value in selected.pending_permissions.values()),
                'outcome': 'unknown'}
