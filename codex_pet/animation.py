"""Pet animation policy and the shared playback timeline."""

from __future__ import annotations

from dataclasses import dataclass

from .pets import (
    ANIMATION_PROFILE_AKITA, ANIMATION_PROFILE_ROBOT, appearance_for,
)

AKITA_STATES = ("idle", "running", "needs_input", "ready", "blocked")
# Reach the near forepaw's forward extreme before folding it back. Keep the
# accepted source drawings and cycle duration; source numbering is not timing.
_AKITA_RUNNING_SEQUENCE = (0, 1, 3, 2, 4, 5, 6, 7)
_AKITA_READY_SEQUENCE = (
    ("ready", 4), ("ready", 1), ("ready", 2), ("ready", 3),
    ("idle", 1), ("idle", 0), ("blink", 0), ("idle", 0), ("idle", 3), ("idle", 6),
    ("idle", 7), ("idle", 0),
)
AKITA_READY_LOOP_START = 4
AKITA_FRAME_COUNTS = {
    "idle": 8,
    "running": len(_AKITA_RUNNING_SEQUENCE),
    "needs_input": 4,
    "ready": len(_AKITA_READY_SEQUENCE),
    "blocked": 4,
}
AKITA_FRAME_INTERVALS = {
    # Slow breath, one quick blink, then a quiet pause before the next loop.
    "idle": (0.6, 0.08, 0.08, 0.08, 0.6, 0.6, 0.6, 0.6),
    # Approved eight-pose cycle; frame count is not a gait quality metric.
    "running": (0.08,) * 8,
    # A small wave with a longer hold at the raised paw.
    "needs_input": (0.2, 0.18, 0.18, 0.85),
    # The entry hop settles into subtle breathing and a slow blink.
    "ready": (0.16, 0.20, 0.22, 0.36, 0.8, 0.28, 0.20, 0.30, 0.6, 0.8, 0.6, 0.8),
    # Blocked is a brief reaction that settles and holds its final pose.
    "blocked": (0.12, 0.18, 0.18, 0.12),
}
AKITA_LOOP_STATES = frozenset(("idle", "running", "needs_input", "ready"))
PREVIEW_FINAL_HOLD_SECONDS = 0.8


@dataclass(frozen=True)
class PlaybackFrame:
    """One logical frame and its finite duration in an offline playback."""

    frame: int
    duration_seconds: float


def _appearance_id(appearance: str) -> str:
    return appearance_for(appearance).id


def _akita_state(state: str) -> str:
    return state if state in AKITA_FRAME_COUNTS else "idle"


def _state_id(appearance: str, state: str) -> str:
    profile = appearance_for(appearance).animation_profile
    return _akita_state(state) if profile == ANIMATION_PROFILE_AKITA else state


def akita_artwork_frame(state: str, frame: int) -> tuple[str, int]:
    """Resolve one logical Akita frame to the artwork used for that pose."""
    state = _akita_state(state)
    frame = max(0, min(int(frame), AKITA_FRAME_COUNTS[state] - 1))
    if state == "ready":
        return _AKITA_READY_SEQUENCE[frame]
    if state == "running":
        return state, _AKITA_RUNNING_SEQUENCE[frame]
    return state, frame


def animation_interval(appearance: str, state: str, frame: int) -> float | None:
    """Return the frame's duration, or None when its final pose holds."""
    profile = appearance_for(appearance).animation_profile
    if profile == ANIMATION_PROFILE_AKITA:
        state = _akita_state(state)
        frame = max(0, int(frame))
        intervals = AKITA_FRAME_INTERVALS[state]
        if state not in AKITA_LOOP_STATES and frame >= len(intervals):
            return None
        return intervals[frame % len(intervals)]
    if profile == ANIMATION_PROFILE_ROBOT:
        if state == "running":
            return 2.0
        if state == "needs_input":
            return 1.4
        return None
    raise ValueError(f"Unsupported animation profile: {profile}")


def advance_animation(appearance: str, state: str, frame: int) -> int:
    """Return the next logical frame, preserving each appearance's cycle."""
    profile = appearance_for(appearance).animation_profile
    if profile == ANIMATION_PROFILE_AKITA:
        state = _akita_state(state)
        frame = max(0, int(frame))
        frame_count = AKITA_FRAME_COUNTS[state]
        if state == "ready" and frame >= frame_count - 1:
            return AKITA_READY_LOOP_START
        if state in AKITA_LOOP_STATES:
            return (frame + 1) % frame_count
        return min(frame + 1, frame_count)
    if profile == ANIMATION_PROFILE_ROBOT:
        if state in ("running", "needs_input"):
            return 1 - frame
        return frame
    raise ValueError(f"Unsupported animation profile: {profile}")


def _cycle_bounds(appearance: str, state: str) -> tuple[int, int] | None:
    profile = appearance_for(appearance).animation_profile
    if profile == ANIMATION_PROFILE_AKITA:
        state = _akita_state(state)
        if state == "ready":
            return AKITA_READY_LOOP_START, AKITA_FRAME_COUNTS[state] - 1
        if state in AKITA_LOOP_STATES:
            return 0, AKITA_FRAME_COUNTS[state] - 1
        return None
    if profile == ANIMATION_PROFILE_ROBOT:
        if state in ("running", "needs_input"):
            return 0, 1
        return None
    raise ValueError(f"Unsupported animation profile: {profile}")


class AnimationTimeline:
    """Advance one pet state's frames against an anchored monotonic schedule."""

    def __init__(self, appearance: str, state: str, now: float,
                 running_count: int = 0) -> None:
        self.frame = 0
        self.deadline: float | None = None
        self.reset(appearance, state, now, running_count)

    def reset(self, appearance: str, state: str, now: float,
              running_count: int = 0) -> None:
        """Start a changed visual at frame zero and anchor its next deadline."""
        self.appearance = _appearance_id(appearance)
        self.state = _state_id(self.appearance, state)
        self.visual = (self.appearance, self.state,
                       int(running_count) if self.state == "running" else 0)
        self.frame = 0
        self._set_deadline(now)

    def sync(self, appearance: str, state: str, running_count: int,
             now: float) -> bool:
        """Reset only when the visible appearance, state, or badge changes."""
        appearance = _appearance_id(appearance)
        state = _state_id(appearance, state)
        visual = (appearance, state, int(running_count) if state == "running" else 0)
        if visual == self.visual:
            return False
        self.reset(appearance, state, now, running_count)
        return True

    def _set_deadline(self, now: float) -> None:
        interval = animation_interval(self.appearance, self.state, self.frame)
        self.deadline = now + interval if interval is not None else None

    def timeout(self, now: float) -> float | None:
        if self.deadline is None:
            return None
        return max(0.0, self.deadline - now)

    def due(self, now: float) -> bool:
        return self.deadline is not None and now >= self.deadline

    def advance(self, now: float) -> int:
        """Advance to the frame due now, skipping missed frames without a burst."""
        if not self.due(now):
            return self.frame

        assert self.deadline is not None
        next_deadline = self.deadline
        while True:
            self.frame = advance_animation(self.appearance, self.state, self.frame)
            interval = animation_interval(self.appearance, self.state, self.frame)
            if interval is None:
                self.deadline = None
                return self.frame

            next_deadline += interval
            if next_deadline > now:
                self.deadline = next_deadline
                return self.frame


def playback_frames(appearance: str, state: str, cycles: int = 1) -> tuple[PlaybackFrame, ...]:
    """Build the same finite frame schedule used by the GUI for offline tools."""
    if cycles < 1:
        raise ValueError("cycles must be at least 1")

    appearance = _appearance_id(appearance)
    state = _state_id(appearance, state)
    timeline = AnimationTimeline(appearance, state, now=0.0)
    cycle_bounds = _cycle_bounds(appearance, state)
    completed_cycles = 0
    scheduled: list[PlaybackFrame] = []

    while True:
        frame = timeline.frame
        interval = animation_interval(appearance, state, frame)
        scheduled.append(PlaybackFrame(
            frame=frame,
            duration_seconds=(interval if interval is not None
                              else PREVIEW_FINAL_HOLD_SECONDS),
        ))
        if interval is None:
            break

        assert timeline.deadline is not None
        timeline.advance(timeline.deadline)
        if (cycle_bounds is not None and frame == cycle_bounds[1]
                and timeline.frame == cycle_bounds[0]):
            completed_cycles += 1
            if completed_cycles >= cycles:
                break

    return tuple(scheduled)
