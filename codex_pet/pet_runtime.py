"""Visible activity to compiled frame requests; no images or native APIs."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .pets import appearance_for
from .pet_pack import bundled_pack
from .clip_timeline import ClipTimeline


@dataclass(frozen=True)
class PetVisual:
    appearance: str
    state: str
    count: int = 0
    marker: str = ''

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> PetVisual:
        return cls(appearance_for(snapshot.get('appearance')).id,
                   snapshot['state'], snapshot.get('running_count', 0),
                   '?' if snapshot.get('confidence', 'observed') != 'observed' else '')


@dataclass(frozen=True)
class FrameRequest:
    pack_id: str
    revision: str
    reference: str
    count: int
    marker: str = ''


class PetRuntime:
    def __init__(self, visual: PetVisual, now: float) -> None:
        self.visual = visual
        self.pack = bundled_pack(appearance_for(visual.appearance).id)
        self.timeline = ClipTimeline(self.pack, self.pack.entry(visual.state), now)

    @staticmethod
    def _identity(visual: PetVisual) -> tuple[str, str, int]:
        pack = bundled_pack(appearance_for(visual.appearance).id)
        state = visual.state if visual.state in pack.roles else 'idle'
        return pack.id, state, visual.count if state == 'running' else 0

    def sync(self, visual: PetVisual, now: float) -> bool:
        before, after = self._identity(self.visual), self._identity(visual)
        self.visual = visual
        if before == after:
            return False
        self.pack = bundled_pack(after[0])
        source = before[1] if before[0] == after[0] else None
        self.timeline = ClipTimeline(self.pack, self.pack.entry(after[1], source), now)
        return True

    def tick(self, now: float) -> None:
        self.timeline.advance(now)

    @property
    def deadline(self) -> float | None:
        return self.timeline.deadline

    def timeout(self, now: float) -> float | None:
        return self.timeline.timeout(now)

    def current(self) -> FrameRequest:
        count = max(0, min(self.visual.count, 10)) if self.visual.state == 'running' else 0
        return FrameRequest(self.pack.id, self.pack.revision, self.timeline.reference,
                            count if count > 1 else 0, self.visual.marker or ('?' if self.visual.state == 'unknown' else ''))
