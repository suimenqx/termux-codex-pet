"""Atomic event inbox and daemon checkpoint; no image or native UI imports."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

MAX_CHECKPOINT_BYTES = 8 * 1024 * 1024


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as file:
            json.dump(value, file, ensure_ascii=False, separators=(',', ':'))
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


class EventJournal:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.inbox = root / 'events'
        self.saved = root / 'state.json'

    def _path(self, event: dict[str, Any]) -> Path:
        identity = hashlib.sha256(event['event_id'].encode()).hexdigest()
        boot = hashlib.sha256(event.get('boot_id', '').encode()).hexdigest()
        stamp = event['emitted_monotonic_ns'] if event.get('boot_id') else int(event['timestamp'] * 1_000_000_000)
        return self.inbox / f'{boot}-{stamp:020d}-{identity}.json'

    def publish(self, event: dict[str, Any]) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self._path(event)
        if not path.exists():
            _atomic_json(path, event)

    def pending(self) -> list[dict[str, Any]]:
        events = []
        if self.inbox.exists():
            for path in sorted(self.inbox.glob('*.json'))[:256]:
                if path.stat().st_size > 65536:
                    raise ValueError('Pending event exceeds IPC byte limit')
                events.append(json.loads(path.read_text()))
        return events

    def remove(self, event: dict[str, Any]) -> None:
        self._path(event).unlink(missing_ok=True)

    def load(self) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]]]:
        if not self.saved.exists():
            return None, {}
        if self.saved.stat().st_size > MAX_CHECKPOINT_BYTES:
            raise ValueError('Session checkpoint exceeds byte limit')
        data = json.loads(self.saved.read_text())
        if (not isinstance(data, dict) or not isinstance(data.get('state'), dict)
                or not isinstance(data.get('receipts'), dict)
                or any(not isinstance(value, dict) or type(value.get('applied')) is not bool
                       or type(value.get('revision', 0)) is not int for value in data['receipts'].values())):
            raise ValueError('Invalid delivery checkpoint')
        return data['state'], data['receipts']

    def commit(self, state: dict[str, Any], receipts: dict[str, dict[str, Any]]) -> None:
        recent = dict(list(receipts.items())[-2048:])
        _atomic_json(self.saved, {'state': state, 'receipts': recent})
