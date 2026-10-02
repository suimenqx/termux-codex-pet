"""Deadline-driven playback of validated clips using integer nanoseconds."""
from bisect import bisect_right
from dataclasses import dataclass
from .pet_pack import PetPack


class ClipTimeline:
    def __init__(self, pack: PetPack, entry: str, now: float):
        self.pack, self.entry = pack, entry
        self.started_ns = round(now * 1_000_000_000)
        self.deadline_ns: int | None = None
        self.advance(now)

    def advance(self, now: float) -> str:
        elapsed = max(0, round(now * 1_000_000_000) - self.started_ns)
        start, clip = self.started_ns, self.pack.clips[self.entry]
        # Compilation proves this chain is finite. No work is proportional to
        # elapsed time or the number of frames skipped while Android slept.
        while clip.mode == 'next' and elapsed >= clip.duration_ns:
            elapsed -= clip.duration_ns
            start += clip.duration_ns
            assert clip.next_clip is not None
            clip = self.pack.clips[clip.next_clip]
        if clip.mode == 'loop':
            cycles, elapsed = divmod(elapsed, clip.duration_ns)
            start += cycles * clip.duration_ns
        index = bisect_right(clip.ends_ns, elapsed)
        if index == len(clip.references):
            self.reference = clip.references[-1]
            self.deadline_ns = None
        else:
            self.reference = clip.references[index]
            self.deadline_ns = start + clip.ends_ns[index]
        return self.reference

    @property
    def deadline(self) -> float | None:
        return self.deadline_ns / 1_000_000_000 if self.deadline_ns is not None else None

    def timeout(self, now: float) -> float | None:
        return max(0, self.deadline - now) if self.deadline is not None else None


@dataclass(frozen=True)
class Exposure:
    reference: str
    duration_ms: int

    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000


def schedule(pack: PetPack, state: str, cycles: int = 1, *,
             from_state: str | None = None) -> tuple[Exposure, ...]:
    """Finite export: next prefixes once, requested loops, 800 ms final hold."""
    if type(cycles) is not int or cycles < 1:
        raise ValueError('cycles must be at least 1')
    clip = pack.clips[pack.entry(state, from_state)]
    result = []
    while True:
        exposures = [Exposure(ref, ns // 1_000_000 if ns is not None else 800)
                     for ref, ns in zip(clip.references, clip.durations_ns, strict=True)]
        result.extend(exposures * (cycles if clip.mode == 'loop' else 1))
        if clip.mode != 'next':
            if clip.mode == 'hold' and clip.durations_ns[-1] is not None:
                result.append(Exposure(clip.references[-1], 800))
            return tuple(result)
        assert clip.next_clip is not None
        clip = pack.clips[clip.next_clip]
