"""Visible activity to animation/frame requests; no images or native APIs."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .animation import AnimationTimeline, akita_artwork_frame
from .pets import appearance_for


@dataclass(frozen=True)
class PetVisual:
    appearance: str
    state: str
    count: int = 0

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> PetVisual:
        return cls(appearance_for(snapshot.get('appearance')).id,
                   snapshot['state'], snapshot.get('running_count', 0))


@dataclass(frozen=True)
class FrameRequest:
    pack_id: str
    revision: str
    reference: str
    count: int


class PetRuntime:
    def __init__(self, visual: PetVisual, now: float) -> None:
        self.visual = visual
        self.timeline = AnimationTimeline(visual.appearance, visual.state, now, visual.count)

    def sync(self, visual: PetVisual, now: float) -> bool:
        self.visual = visual
        return self.timeline.sync(visual.appearance, visual.state, visual.count, now)

    def tick(self, now: float) -> None:
        self.timeline.advance(now)

    @property
    def deadline(self) -> float | None:
        return self.timeline.deadline

    def timeout(self, now: float) -> float | None:
        return self.timeline.timeout(now)

    def current(self) -> FrameRequest:
        timeline = self.timeline
        if timeline.appearance == 'akita':
            pose, index = akita_artwork_frame(timeline.state, timeline.frame)
            reference = 'ready/blink' if pose == 'blink' else f'{pose}/{index:02}'
        else:
            reference = f'{timeline.state}/{timeline.frame:02}'
        count = max(0, min(self.visual.count, 10)) if timeline.state == 'running' else 0
        return FrameRequest(timeline.appearance, 'legacy-v1', reference, count if count > 1 else 0)
