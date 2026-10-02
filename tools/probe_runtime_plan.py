#!/usr/bin/env python3
"""Offline evidence for the refactor plan; never starts/stops a daemon or GUI.

Validates proposed clip manifests against production PNGs and exposure times,
measures the existing missed-frame walk against a running-cycle clock prototype,
and fills an isolated GuiWorker socketpair to demonstrate wake backpressure.
The clock prototype is deliberately limited to one loop, not a new runtime.
"""
from __future__ import annotations

import argparse
import fcntl
from bisect import bisect_right
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import platform
import select
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.historical_animation import AnimationTimeline, playback_frames  # noqa: E402
from tools.historical_art import (  # noqa: E402
    _add_count_badge, _akita_asset, _ready_blink_icon, _robot_icon, icon,
)
from codex_pet.gui import GuiWorker  # noqa: E402

STATES = ("idle", "running", "needs_input", "ready", "blocked")
COUNTS = (0, 1, 2, 9, 10, 25)
RUNNING_MS = (40, 40, 80, 80, 80, 40, 40, 80, 80, 80)


def clip(refs: list[str], durations: list[int | None],
         mode: str, next_clip: str | None = None) -> dict[str, Any]:
    end: dict[str, Any] = {"mode": mode}
    if next_clip is not None:
        end["clip"] = next_clip
    return {"frames": [{"frame": ref, "duration_ms": duration}
                       for ref, duration in zip(refs, durations, strict=True)],
            "end": end}


def manifests() -> list[dict[str, Any]]:
    frame_counts = {"idle": 8, "running": 10, "needs_input": 4,
                    "ready": 8, "blocked": 4}
    frames = {
        f"{state}/{index:02}": {"file": f"frames/{state}/{index:02}.png",
                               "fallback": f"{state}.png"}
        for state, count in frame_counts.items() for index in range(count)
    }
    frames["ready/blink"] = {
        "file": "derived/ready-blink.png",
        "derived_provenance": {"base": "idle/00", "patch": "idle/02",
                               "copy_rect": [58, 54, 198, 116]},
    }
    akita = {
        "schema_version": 1, "id": "akita", "canvas_px": [256, 256],
        "display_dp": [64, 64], "source": {"kind": "png_directory"},
        "frames": frames, "roles": {state: state for state in STATES},
        "transitions": [{"from": "running", "to": "ready",
                         "clip": "running_to_ready"}],
        "clips": {
            "idle": clip([f"idle/{i:02}" for i in range(8)],
                         [600, 80, 80, 80, 600, 600, 600, 600], "loop"),
            "running": clip([f"running/{i:02}" for i in
                             (0, 8, 1, 2, 3, 4, 9, 5, 6, 7)],
                            list(RUNNING_MS), "loop"),
            "needs_input": clip([f"needs_input/{i:02}" for i in range(4)],
                                [200, 180, 180, 850], "loop"),
            "ready": clip([f"ready/{i:02}" for i in (4, 1, 2, 3)],
                          [160, 200, 220, 360], "next", "ready_rest"),
            "ready_rest": clip(
                ["idle/01", "idle/00", "ready/blink", "idle/00", "idle/03",
                 "idle/06", "idle/07", "idle/00"],
                [800, 280, 200, 300, 600, 800, 600, 800], "loop"),
            "running_to_ready": clip([f"ready/{i:02}" for i in (5, 6, 7)],
                                     [120, 120, 120], "next", "ready"),
            "blocked": clip([f"blocked/{i:02}" for i in range(4)],
                            [120, 180, 180, 120], "hold"),
        },
        "decorations": {"count": {"style": "akita_count_v1",
                                  "visible_above": 1, "clamp": 10}},
    }
    robot = {
        "schema_version": 1, "id": "robot", "canvas_px": [64, 64],
        "display_dp": [64, 64], "source": {"kind": "builtin", "id": "robot_v1"},
        "frames": {
            f"{state}/{i:02}": {"pose": state, "variant": i}
            for state in STATES
            for i in range(2 if state in ("running", "needs_input") else 1)
        },
        "roles": {state: state for state in STATES}, "transitions": [],
        "clips": {
            state: clip(
                [f"{state}/{i:02}" for i in
                 range(2 if state in ("running", "needs_input") else 1)],
                [2000, 2000] if state == "running" else
                [1400, 1400] if state == "needs_input" else [None],
                "loop" if state in ("running", "needs_input") else "hold")
            for state in STATES
        },
        "decorations": {"count": {"style": "robot_count_v1",
                                  "visible_above": 1, "clamp": 10}},
    }
    return [akita, robot]


def candidate_schedule(manifest: dict[str, Any], state: str, cycles: int,
                       from_state: str | None = None) -> list[tuple[str, int]]:
    name = manifest["roles"][state]
    if from_state is not None:
        for transition in manifest["transitions"]:
            if (transition["from"] == manifest["roles"][from_state]
                    and transition["to"] == name):
                name = transition["clip"]
                break
    output: list[tuple[str, int]] = []
    loops = 0
    while True:
        current = manifest["clips"][name]
        for frame in current["frames"]:
            duration = frame["duration_ms"]
            output.append((frame["frame"], 800 if duration is None else duration))
        end = current["end"]
        if end["mode"] == "next":
            name = end["clip"]
        elif end["mode"] == "loop":
            loops += 1
            if loops == cycles:
                return output
        else:
            if current["frames"][-1]["duration_ms"] is not None:
                output.append((current["frames"][-1]["frame"], 800))
            return output


@lru_cache(maxsize=None)
def candidate_hash(pet: str, ref: str, count: int) -> str:
    if pet == "robot":
        state, frame = ref.split("/")
        png = _robot_icon(state, int(frame), count)
    else:
        if ref == "ready/blink":
            png = _ready_blink_icon()
        else:
            state, frame = ref.split("/")
            png = _akita_asset(state, int(frame))
            if state == "running" and count > 1:
                png = _add_count_badge(png, min(count, 10))
    return hashlib.sha256(png).hexdigest()


@lru_cache(maxsize=None)
def production_hash(pet: str, state: str, frame: int, count: int) -> str:
    return hashlib.sha256(icon(state, frame, count, pet)).hexdigest()


def manifest_parity() -> dict[str, Any]:
    comparisons = exposures = 0
    for manifest in manifests():
        pet = manifest["id"]
        for state in STATES:
            for source in (None, *STATES):
                for cycles in (1, 2, 3):
                    for count in COUNTS:
                        original = [
                            (production_hash(pet, state, frame.frame, count),
                             round(frame.duration_seconds * 1000))
                            for frame in playback_frames(pet, state, cycles,
                                                         from_state=source)
                        ]
                        candidate = [
                            (candidate_hash(pet, ref, count), duration)
                            for ref, duration in candidate_schedule(
                                manifest, state, cycles, source)
                        ]
                        if original != candidate:
                            raise AssertionError((pet, state, source, cycles, count))
                        comparisons += 1
                        exposures += len(original)
    return {
        "comparisons": comparisons, "exposures_compared": exposures,
        "pets": ["akita", "robot"], "states": STATES,
        "from_states": [None, *STATES], "cycles": [1, 2, 3], "counts": COUNTS,
        "identity": "Exact production PNG SHA256 and exposure milliseconds",
        "pass": True,
        "limitations": [
            "Uses production frame/composition helpers; not a new loader or codec.",
            "Same-pack state transitions only; appearance switches require their own test.",
            "Static and blocked infinite holds get the existing offline 800 ms preview hold.",
        ],
    }


class RunningCycleClock:
    """One-loop arithmetic prototype, not the proposed generic clip runtime."""

    def __init__(self) -> None:
        total = 0
        self.ends: list[int] = []
        for duration in RUNNING_MS:
            total += duration * 1_000_000
            self.ends.append(total)
        self.cycle_ns = total

    def current(self, now_ns: int) -> tuple[int, int]:
        cycles, phase = divmod(now_ns, self.cycle_ns)
        frame = bisect_right(self.ends, phase)
        return frame, cycles * self.cycle_ns + self.ends[frame]


def clock_probe(repeats: int) -> dict[str, Any]:
    clock = RunningCycleClock()
    rows = []
    for gap in (60, 3600, 86400):
        legacy_times = []
        prototype_times = []
        for _ in range(repeats):
            timeline = AnimationTimeline("akita", "running", 0)
            start = time.perf_counter_ns()
            legacy_frame = timeline.advance(gap)
            legacy_times.append(time.perf_counter_ns() - start)
            start = time.perf_counter_ns()
            frame, deadline = clock.current(gap * 1_000_000_000)
            prototype_times.append(time.perf_counter_ns() - start)
        rows.append({
            "gap_seconds": gap, "legacy_wall_ns": legacy_times,
            "legacy_median_ns": statistics.median(legacy_times),
            "prototype_wall_ns": prototype_times,
            "prototype_median_ns": statistics.median(prototype_times),
            "legacy_frame": legacy_frame, "legacy_deadline_seconds": timeline.deadline,
            "prototype_frame": frame, "prototype_deadline_ns": deadline,
        })
    # Check every exposure boundary on ten loops and both sides, independent of
    # legacy float accumulation. Exact boundaries belong to the next exposure.
    boundary_checks = 0
    for cycle in range(10):
        start_ns = cycle * clock.cycle_ns
        for index, end in enumerate(clock.ends):
            before, before_deadline = clock.current(start_ns + end - 1)
            at, at_deadline = clock.current(start_ns + end)
            after, after_deadline = clock.current(start_ns + end + 1)
            assert before == index and before_deadline == start_ns + end
            expected = (index + 1) % len(clock.ends)
            assert at == after == expected
            assert at_deadline == after_deadline > start_ns + end
            boundary_checks += 3
    # Non-boundary sampling checks phase parity without equating long-term
    # floating-point rounding artifacts to the intended timing contract.
    parity_checks = 0
    for step in range(1, 501):
        now_ns = step * 17_123_457
        timeline = AnimationTimeline("akita", "running", 0)
        legacy = timeline.advance(now_ns / 1_000_000_000)
        candidate, _ = clock.current(now_ns)
        assert legacy == candidate, (now_ns, legacy, candidate)
        parity_checks += 1
    return {
        "repeats": repeats, "rows": rows,
        "exact_integer_boundary_checks": boundary_checks,
        "non_boundary_legacy_phase_comparisons": parity_checks,
        "pass": True,
        "limitations": [
            "Local wall-clock diagnostic, not controlled CPU, energy, or Android frame timing.",
            "Prototype covers Akita running loop; generic next/hold/transition clock remains to implement.",
            "Legacy float deadlines can choose the preceding exposure at mathematically exact boundaries after long gaps.",
        ],
    }


def wake_probe() -> dict[str, Any]:
    # Constructing GuiWorker only allocates sockets/thread metadata; never start.
    worker = GuiWorker(Path("/unused-probe-config"), lambda: {}, lambda *_: None)
    original_timeout = worker.write_wake.gettimeout()
    sent = 0
    timeout_seconds = 0.01
    try:
        worker.write_wake.setblocking(False)
        while sent < 100_000:
            try:
                worker.write_wake.send(b"x")
                sent += 1
            except BlockingIOError:
                break
        else:
            raise AssertionError("Isolated socketpair did not saturate")
        worker.write_wake.settimeout(timeout_seconds)
        start = time.perf_counter_ns()
        worker.wake()  # Swallows timeout as OSError, measuring the wait itself.
        saturated_wake_ns = time.perf_counter_ns() - start
        worker.write_wake.setblocking(False)
        start = time.perf_counter_ns()
        worker.wake()  # EAGAIN is swallowed immediately: coalesced notification.
        nonblocking_wake_ns = time.perf_counter_ns() - start
        worker.read_wake.setblocking(False)
        drained = 0
        while True:
            try:
                drained += len(worker.read_wake.recv(4096))
            except BlockingIOError:
                break
        worker.wake()
        resumed = worker.read_wake.recv(1) == b"x"
        return {
            "original_write_socket_timeout": original_timeout,
            "original_socket_blocking": original_timeout is None,
            "injected_timeout_seconds": timeout_seconds,
            "one_byte_sends_before_saturation": sent,
            "bytes_drained": drained,
            "saturated_wake_wall_ns_with_injected_timeout": saturated_wake_ns,
            "nonblocking_saturated_wake_wall_ns": nonblocking_wake_ns,
            "wake_after_drain_succeeded": resumed,
            "pass": resumed and original_timeout is None and drained == sent,
            "interpretation": (
                "Existing wake has no timeout; a full isolated socket makes its send wait. "
                "The probe injects a timeout to bound that wait. Nonblocking coalescing "
                "returns immediately while a wake byte is already pending. The daemon's "
                "event branch calls wake after releasing its state lock; reconnect calls "
                "wake inside that lock. Either can stall the single IPC server thread."
            ),
            "limitations": [
                "No production hook flood and no GUI connection used.",
                "Saturation count depends on kernel/socket limits; not a session-count limit.",
            ],
        }
    finally:
        worker.read_wake.close()
        worker.write_wake.close()



def startup_lock_probe() -> dict[str, Any]:
    """Reproduce the pre-deadline flock wait using only a temporary lock file."""
    startup_wait = 0.05
    watchdog = 0.3
    child_code = """import sys
from pathlib import Path
from codex_pet import runtime
runtime.START_LOCK = Path(sys.argv[1])
runtime.directories = lambda: None
runtime.request = lambda *args, **kwargs: {"ok": True}
print("entered", flush=True)
print(runtime.start_daemon(float(sys.argv[2])), flush=True)
"""
    with tempfile.TemporaryDirectory(prefix="codex-pet-start-lock-probe-") as temporary:
        lock_path = Path(temporary) / "start.lock"
        with lock_path.open("a+b") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            process = subprocess.Popen(
                [sys.executable, "-c", child_code, str(lock_path), str(startup_wait)],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                assert process.stdout is not None
                ready, _, _ = select.select([process.stdout], [], [], 3.0)
                if not ready or process.stdout.readline().strip() != "entered":
                    raise RuntimeError("Isolated startup-lock probe did not enter its call")
                start = time.perf_counter_ns()
                try:
                    process.wait(timeout=watchdog)
                except subprocess.TimeoutExpired:
                    elapsed = time.perf_counter_ns() - start
                    process.kill()
                    stdout, stderr = process.communicate(timeout=3)
                    return {
                        "recorded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "start_daemon_wait_seconds": startup_wait,
                        "watchdog_seconds": watchdog,
                        "still_blocked_after_ns": elapsed,
                        "observed_unbounded_start_lock_wait": True,
                        "child_terminated_by_watchdog": True,
                        "production_contact": False,
                        "child_stdout_after_ready": stdout,
                        "child_stderr": stderr,
                        "interpretation": (
                            "start_daemon acquires START_LOCK with blocking flock before "
                            "creating its startup deadline. The wait parameter does not "
                            "bound lock acquisition. A held temporary lock kept the call "
                            "blocked beyond the requested startup wait."
                        ),
                        "isolation": [
                            "Only a TemporaryDirectory start.lock is opened/locked.",
                            "Child directories is replaced with a no-op.",
                            "Child request always returns an in-memory ok reply; no IPC is sent.",
                            "If the lock were acquired, the mock reply would return before spawning a daemon.",
                        ],
                        "limitations": [
                            "This reproduces a failure path, not an observed production lock stall.",
                            "Mocked request isolates flock behavior; it does not validate real startup or notification timing.",
                        ],
                    }
                stdout, stderr = process.communicate(timeout=3)
                raise AssertionError(
                    f"Call unexpectedly returned while lock held: {process.returncode}, {stdout!r}, {stderr!r}"
                )
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path.home() / ".cache/codex-pet/refactor-research/runtime-results.json")
    parser.add_argument("--clock-repeats", type=int, default=3)
    args = parser.parse_args()
    if args.clock_repeats < 1:
        parser.error("--clock-repeats must be at least 1")
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    report = {
        "recorded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_revision": revision, "python": platform.python_version(),
        "machine": platform.machine(),
        "scope": "Offline refactor prototypes; no daemon/GUI connection/config mutation",
        "manifest_parity": manifest_parity(),
        "clock": clock_probe(args.clock_repeats),
        "wake": wake_probe(),
        "startup_lock": startup_lock_probe(),
        "proposed_manifests": manifests(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output),
                      "manifest_comparisons": report["manifest_parity"]["comparisons"],
                      "exposures_compared": report["manifest_parity"]["exposures_compared"],
                      "clock_pass": report["clock"]["pass"],
                      "wake": report["wake"],
                      "startup_lock": report["startup_lock"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
