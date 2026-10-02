"""Offline playback and historical index adapters over compiled pet packs.

Frame references are the production interface. Integer indices remain for old
artwork exports and regression fixtures; they are derived, never another table.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from .pet_pack import PetPack, bundled_pack
from .clip_timeline import schedule
from .pet_runtime import PetRuntime, PetVisual
from .pets import appearance_for

AKITA_STATES = ('idle', 'running', 'needs_input', 'ready', 'blocked')
PREVIEW_FINAL_HOLD_SECONDS = .8


@dataclass(frozen=True)
class _Slot:
    clip: str
    index: int
    reference: str
    duration: float | None


@lru_cache(maxsize=16)
def _slots(appearance: str, state: str) -> tuple[_Slot, ...]:
    pack = bundled_pack(appearance_for(appearance).id)
    state = state if state in pack.roles else 'idle'
    entries = [pack.entry(state)] + [entry for (_, target),
                                     entry in pack.transitions.items() if target == state]
    seen: set[str] = set()
    result: list[_Slot] = []
    for entry in entries:
        clip = pack.clips[entry]
        while clip.name not in seen:
            seen.add(clip.name)
            result.extend(_Slot(clip.name, i, ref, ns/1_000_000_000 if ns is not None else None)
                          for i, (ref, ns) in enumerate(zip(clip.references, clip.durations_ns, strict=True)))
            if clip.mode == 'hold' and clip.durations_ns[-1] is not None:
                result.append(_Slot(clip.name, len(
                    clip.references), clip.references[-1], None))
            if clip.mode != 'next':
                break
            assert clip.next_clip is not None
            clip = pack.clips[clip.next_clip]
    return tuple(result)


def frame_reference(appearance: str, state: str, frame: int = 0) -> str:
    slots = _slots(appearance, state)
    return slots[max(0, min(int(frame), len(slots)-1))].reference


def akita_artwork_frame(state: str, frame: int) -> tuple[str, int]:
    pose, index = frame_reference('akita', state, frame).split('/')
    return ('blink', 0) if index == 'blink' else (pose, int(index))


def animation_interval(appearance: str, state: str, frame: int) -> float | None:
    slots = _slots(appearance, state)
    return slots[max(0, min(int(frame), len(slots)-1))].duration


def advance_animation(appearance: str, state: str, frame: int) -> int:
    slots = _slots(appearance, state)
    slot = slots[max(0, min(int(frame), len(slots)-1))]
    clip = bundled_pack(appearance_for(appearance).id).clips[slot.clip]
    if slot.index+1 < len(clip.references):
        key = clip.name, slot.index+1
    elif clip.mode == 'next':
        assert clip.next_clip is not None
        key = clip.next_clip, 0
    elif clip.mode == 'loop':
        key = clip.name, 0
    else:
        key = clip.name, len(
            clip.references) if clip.durations_ns[-1] is not None else 0
    return next(i for i, row in enumerate(slots) if (row.clip, row.index) == key)


class AnimationTimeline:
    """Compatibility view of PetRuntime for archived artwork tooling."""

    def __init__(self, appearance: str, state: str, now: float, running_count: int = 0):
        self.reset(appearance, state, now, running_count)

    def reset(self, appearance: str, state: str, now: float, running_count: int = 0) -> None:
        self.runtime = PetRuntime(
            PetVisual(appearance, state, running_count), now)

    @property
    def appearance(self) -> str:
        return self.runtime.pack.id

    @property
    def state(self) -> str:
        state = self.runtime.visual.state
        return state if state in self.runtime.pack.roles else 'idle'

    @property
    def frame(self) -> int:
        timeline = self.runtime.timeline
        return next(i for i, row in enumerate(_slots(self.appearance, self.state))
                    if (row.clip, row.index) == (timeline.clip_id, timeline.index))

    @property
    def deadline(self) -> float | None:
        return self.runtime.deadline

    def timeout(self, now: float) -> float | None:
        return self.runtime.timeout(now)

    def due(self, now: float) -> bool:
        return self.deadline is not None and now >= self.deadline

    def sync(self, appearance: str, state: str, running_count: int, now: float) -> bool:
        return self.runtime.sync(PetVisual(appearance, state, running_count), now)

    def advance(self, now: float) -> int:
        self.runtime.tick(now)
        return self.frame


@dataclass(frozen=True)
class PlaybackFrame:
    frame: int
    duration_seconds: float
    reference: str


def playback_frames(appearance: str, state: str, cycles: int = 1, *, from_state: str | None = None) -> tuple[PlaybackFrame, ...]:
    pack = bundled_pack(appearance_for(appearance).id)
    indices = {(row.clip, row.index): i for i,
               row in enumerate(_slots(pack.id, state))}
    return tuple(PlaybackFrame(indices[step.clip, step.index], step.duration_seconds, step.reference)
                 for step in schedule(pack, state, cycles, from_state=from_state))


# Read-only compatibility names for existing artwork checks. No authored
# timings, frame mappings or appearance-specific playback logic live here.
AKITA_FRAME_COUNTS = {state: max(1, sum(row.duration is not None for row in _slots(
    'akita', state))) for state in AKITA_STATES}
AKITA_FRAME_INTERVALS = {state: tuple(row.duration for row in _slots(
    'akita', state) if row.duration is not None) for state in AKITA_STATES}
_ready_slots = _slots('akita', 'ready')
_ready_pack = bundled_pack('akita')
_ready_loop = [i for i, row in enumerate(
    _ready_slots) if _ready_pack.clips[row.clip].mode == 'loop']
AKITA_READY_LOOP_START, AKITA_READY_LOOP_END = _ready_loop[0], _ready_loop[-1]
AKITA_READY_RUNNING_ENTRY_START = next(i for i, row in enumerate(
    _ready_slots) if row.clip == _ready_pack.entry('ready', 'running'))
