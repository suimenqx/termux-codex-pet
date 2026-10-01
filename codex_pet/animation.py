"""Pet animation policy and the shared playback timeline."""

from __future__ import annotations

from dataclasses import dataclass

from .pets import (
    ANIMATION_PROFILE_AKITA, ANIMATION_PROFILE_ROBOT, appearance_for,
)

AKITA_STATES = ("idle", "running", "needs_input", "ready", "blocked")
AKITA_READY_LOOP_START = 32
_AKITA_REST_INTERVALS = (0.12,) * 20 + (0.04,) * 4 + (0.12,) * 8
AKITA_FRAME_INTERVALS = {
    # Slow body/tail motion; finer exposures only around the 160 ms blink.
    "idle": _AKITA_REST_INTERVALS,
    # The shared rig supplies 32 poses without changing the 640 ms stride.
    "running": (0.02,) * 32,
    "needs_input": ((0.05,) * 7 + (0.08,) * 6 + (0.65,)
                    + (0.05,) * 7 + (0.19,) * 3),
    # One 1.28 s hop, then the same rest motion with the Ready collar color.
    "ready": (0.04,) * AKITA_READY_LOOP_START + _AKITA_REST_INTERVALS,
    "blocked": (0.05,) * 16,
}
AKITA_FRAME_COUNTS = {state: len(delays) for state, delays in AKITA_FRAME_INTERVALS.items()}
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
