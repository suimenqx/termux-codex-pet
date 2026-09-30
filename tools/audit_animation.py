#!/usr/bin/env python3
"""Render and measure Pet animation frames without capturing the device screen."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_pet.art import (  # noqa: E402
    AKITA_FRAME_COUNTS,
    AKITA_LOOP_STATES,
    AKITA_READY_LOOP_START,
    AKITA_READY_SEQUENCE,
    AKITA_SIZE,
    AKITA_STATES,
    _png,
    advance_animation,
    animation_interval,
    rgba_icon,
)

PET_SIZE_DP = 64
PREVIEW_DENSITY = 3.0
FINAL_HOLD_SECONDS = 0.8
TAIL_SOURCE_BOX = (180, 65, 256, 140)
CHEST_SOURCE_BOX = (45, 120, 165, 220)
MIN_TAIL_CHANGED_PIXELS = 500
MIN_TAIL_CENTROID_DELTA_DP = 1.0
MIN_TAIL_EDGE_SWEEP_DP = 1.5
CHANGE_THRESHOLD = 12

_FONT = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "/": ("001", "001", "010", "100", "100"),
}


@dataclass(frozen=True)
class RenderedFrame:
    step: int
    frame: int
    delay_seconds: float
    rgba: bytes


@dataclass(frozen=True)
class RenderAudit:
    report: dict[str, object]
    frames: tuple[RenderedFrame, ...]
    contact_sheet: bytes


def _timeline_length(state: str, cycles: int) -> int:
    frame_count = AKITA_FRAME_COUNTS[state]
    if state == "ready":
        return frame_count + (cycles - 1) * (frame_count - AKITA_READY_LOOP_START)
    if state in AKITA_LOOP_STATES:
        return frame_count * cycles
    return frame_count + 1


def _resize_rgba(source: bytes, size: int) -> bytes:
    """Scale the shared-buffer RGBA frame with premultiplied bilinear sampling."""
    expected = AKITA_SIZE * AKITA_SIZE * 4
    if len(source) != expected:
        raise ValueError(f"expected {expected} RGBA bytes, received {len(source)}")

    result = bytearray(size * size * 4)
    source_width = source_height = AKITA_SIZE
    for y in range(size):
        source_y = max(0.0, min(source_height - 1.0,
                                (y + 0.5) * source_height / size - 0.5))
        top = math.floor(source_y)
        bottom = min(top + 1, source_height - 1)
        fy = source_y - top
        for x in range(size):
            source_x = max(0.0, min(source_width - 1.0,
                                    (x + 0.5) * source_width / size - 0.5))
            left = math.floor(source_x)
            right = min(left + 1, source_width - 1)
            fx = source_x - left
            samples = (
                (top, left, (1 - fx) * (1 - fy)),
                (top, right, fx * (1 - fy)),
                (bottom, left, (1 - fx) * fy),
                (bottom, right, fx * fy),
            )
            alpha = 0.0
            color = [0.0, 0.0, 0.0]
            for sample_y, sample_x, weight in samples:
                offset = (sample_y * source_width + sample_x) * 4
                sample_alpha = source[offset + 3] / 255.0
                alpha += sample_alpha * weight
                for channel in range(3):
                    color[channel] += source[offset + channel] * sample_alpha * weight

            output = (y * size + x) * 4
            if alpha:
                result[output:output + 3] = bytes(round(channel / alpha) for channel in color)
            result[output + 3] = round(alpha * 255)
    return bytes(result)


def _scaled_box(box: tuple[int, int, int, int], size: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    scale = size / AKITA_SIZE
    return (math.floor(x0 * scale), math.floor(y0 * scale),
            math.ceil(x1 * scale), math.ceil(y1 * scale))


def _changed_pixels(first: bytes, second: bytes, size: int,
                    box: tuple[int, int, int, int] | None = None) -> tuple[int, float]:
    x0, y0, x1, y1 = box or (0, 0, size, size)
    changed = 0
    difference = 0
    channels = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            offset = (y * size + x) * 4
            deltas = [abs(first[offset + c] - second[offset + c]) for c in range(4)]
            changed += max(deltas) > CHANGE_THRESHOLD
            difference += sum(deltas)
            channels += 4
    return changed, difference / channels if channels else 0.0


def _tail_pose_frames(state: str) -> tuple[int, int] | None:
    if state == "idle":
        return 6, 7
    if state != "ready":
        return None
    pose_steps: dict[int, int] = {}
    for step, (asset_state, asset_frame) in enumerate(AKITA_READY_SEQUENCE):
        if asset_state == "idle" and asset_frame in (6, 7):
            pose_steps.setdefault(asset_frame, step)
    if set(pose_steps) == {6, 7}:
        return pose_steps[6], pose_steps[7]
    return None


def _alpha_centroid(rgba: bytes, size: int,
                    box: tuple[int, int, int, int]) -> tuple[float, float] | None:
    x0, y0, x1, y1 = box
    alpha_sum = x_sum = y_sum = 0.0
    for y in range(y0, y1):
        for x in range(x0, x1):
            alpha = rgba[(y * size + x) * 4 + 3]
            if alpha <= 16:
                continue
            alpha_sum += alpha
            x_sum += (x + 0.5) * alpha
            y_sum += (y + 0.5) * alpha
    if not alpha_sum:
        return None
    return x_sum / alpha_sum, y_sum / alpha_sum


def _alpha_bounds(rgba: bytes, size: int,
                  box: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    x0, y0, x1, y1 = box
    points = [
        (x, y)
        for y in range(y0, y1)
        for x in range(x0, x1)
        if rgba[(y * size + x) * 4 + 3] > 16
    ]
    if not points:
        return None
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def _tail_metrics(state: str, frames: tuple[RenderedFrame, ...], size: int,
                  density: float) -> dict[str, object] | None:
    steps = _tail_pose_frames(state)
    if steps is None or max(steps) >= len(frames):
        return None
    high, low = (frames[step] for step in steps)
    tail_box = _scaled_box(TAIL_SOURCE_BOX, size)
    chest_box = _scaled_box(CHEST_SOURCE_BOX, size)
    changed, mean_delta = _changed_pixels(high.rgba, low.rgba, size, tail_box)
    chest_changed, _ = _changed_pixels(high.rgba, low.rgba, size, chest_box)
    high_center = _alpha_centroid(high.rgba, size, tail_box)
    low_center = _alpha_centroid(low.rgba, size, tail_box)
    high_bounds = _alpha_bounds(high.rgba, size, tail_box)
    low_bounds = _alpha_bounds(low.rgba, size, tail_box)
    centroid_delta_dp = None
    if high_center is not None and low_center is not None:
        centroid_delta_dp = round(math.dist(high_center, low_center) / density, 3)
    edge_sweep_dp = None
    if high_bounds is not None and low_bounds is not None:
        edge_sweep_dp = round(abs(high_bounds[2] - low_bounds[2]) / density, 3)
    minimum_changed = max(1, round(
        MIN_TAIL_CHANGED_PIXELS * (size / (PET_SIZE_DP * PREVIEW_DENSITY)) ** 2
    ))
    centroid_passed = (centroid_delta_dp is not None
                       and centroid_delta_dp >= MIN_TAIL_CENTROID_DELTA_DP)
    edge_passed = (edge_sweep_dp is not None
                   and edge_sweep_dp >= MIN_TAIL_EDGE_SWEEP_DP)
    return {
        "high_step": high.step,
        "low_step": low.step,
        "changed_pixels_at_display_size": changed,
        "mean_absolute_channel_delta": round(mean_delta, 3),
        "alpha_centroid_delta_dp": centroid_delta_dp,
        "outer_tail_edge_sweep_dp": edge_sweep_dp,
        "chest_changed_pixels_at_display_size": chest_changed,
        "minimum_changed_pixels": minimum_changed,
        "minimum_centroid_delta_dp": MIN_TAIL_CENTROID_DELTA_DP,
        "minimum_edge_sweep_dp": MIN_TAIL_EDGE_SWEEP_DP,
        "passed": (changed >= minimum_changed and centroid_passed and edge_passed
                   and chest_changed == 0),
    }


def _draw_text(canvas: bytearray, width: int, x: int, y: int, label: str) -> None:
    scale = 2
    color = (222, 228, 236, 255)
    for char_index, character in enumerate(label):
        glyph = _FONT[character]
        for row, pattern in enumerate(glyph):
            for column, bit in enumerate(pattern):
                if bit != "1":
                    continue
                for dy in range(scale):
                    for dx in range(scale):
                        pixel_x = x + char_index * 8 + column * scale + dx
                        pixel_y = y + row * scale + dy
                        if pixel_x >= width:
                            continue
                        offset = (pixel_y * width + pixel_x) * 4
                        canvas[offset:offset + 4] = bytes(color)


def _contact_sheet(frames: tuple[RenderedFrame, ...], size: int) -> bytes:
    columns = min(4, len(frames))
    rows = math.ceil(len(frames) / columns)
    gutter, padding, label_height = 12, 12, 18
    width = padding * 2 + columns * size + (columns - 1) * gutter
    cell_height = size + label_height
    height = padding * 2 + rows * cell_height + (rows - 1) * gutter
    background = (21, 25, 31, 255)
    canvas = bytearray(bytes(background) * (width * height))

    for index, frame in enumerate(frames):
        cell_x = padding + (index % columns) * (size + gutter)
        cell_y = padding + (index // columns) * (cell_height + gutter)
        for y in range(size):
            for x in range(size):
                checker = (x // 12 + y // 12) % 2
                color = (45, 53, 64, 255) if checker else (34, 40, 49, 255)
                destination = ((cell_y + y) * width + cell_x + x) * 4
                source = (y * size + x) * 4
                alpha = frame.rgba[source + 3]
                inverse = 255 - alpha
                canvas[destination:destination + 4] = bytes((
                    (frame.rgba[source] * alpha + color[0] * inverse + 127) // 255,
                    (frame.rgba[source + 1] * alpha + color[1] * inverse + 127) // 255,
                    (frame.rgba[source + 2] * alpha + color[2] * inverse + 127) // 255,
                    255,
                ))
        _draw_text(canvas, width, cell_x + 2, cell_y + size + 4,
                   f"{frame.step:02d}/{frame.frame:02d}")
    return _png(width, height, canvas)


def render_audit(state: str, cycles: int = 1,
                 density: float = PREVIEW_DENSITY) -> RenderAudit:
    """Render the production RGBA sequence at overlay size and report its motion."""
    if state not in AKITA_STATES:
        raise ValueError(f"unknown Akita state: {state}")
    if cycles < 1:
        raise ValueError("cycles must be at least 1")
    if not math.isfinite(density) or density <= 0:
        raise ValueError("density must be greater than 0")

    display_size = round(PET_SIZE_DP * density)
    if display_size < 1:
        raise ValueError("density is too small to render a pixel")

    count = _timeline_length(state, cycles)
    scale_cache: dict[int, bytes] = {}
    rendered: list[RenderedFrame] = []
    frame = 0
    for step in range(count):
        delay = animation_interval("akita", state, frame)
        if delay is None:
            delay = FINAL_HOLD_SECONDS
        pixels = scale_cache.get(frame)
        if pixels is None:
            pixels = _resize_rgba(rgba_icon(state, frame), display_size)
            scale_cache[frame] = pixels
        rendered.append(RenderedFrame(step, frame, delay, pixels))
        next_frame = advance_animation("akita", state, frame)
        if next_frame == frame and delay == FINAL_HOLD_SECONDS:
            break
        frame = next_frame

    transitions = []
    for before, after in zip(rendered, rendered[1:]):
        changed, mean_delta = _changed_pixels(before.rgba, after.rgba, display_size)
        transitions.append({
            "from_step": before.step,
            "to_step": after.step,
            "from_frame": before.frame,
            "to_frame": after.frame,
            "changed_pixels_at_display_size": changed,
            "mean_absolute_channel_delta": round(mean_delta, 3),
        })

    frames = tuple(rendered)
    tail_metrics = _tail_metrics(state, frames, display_size, density)
    report: dict[str, object] = {
        "renderer": "rgba_icon with premultiplied bilinear downsampling",
        "state": state,
        "display_size_dp": PET_SIZE_DP,
        "density": density,
        "display_size_px": display_size,
        "frame_count": len(frames),
        "duration_seconds": round(sum(item.delay_seconds for item in frames), 3),
        "frames": [
            {
                "step": item.step,
                "frame": item.frame,
                "delay_seconds": item.delay_seconds,
                "sha256": hashlib.sha256(item.rgba).hexdigest(),
            }
            for item in frames
        ],
        "transitions": transitions,
        "tail_motion": tail_metrics,
        "contact_sheet": "contact-sheet.png",
    }
    return RenderAudit(report, frames, _contact_sheet(frames, display_size))


def write_audit(result: RenderAudit, output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    frame_dir = output / "frames"
    frame_dir.mkdir(exist_ok=True)
    report = dict(result.report)
    report_frames = [dict(frame) for frame in report["frames"]]  # type: ignore[arg-type]
    report["frames"] = report_frames
    size = int(report["display_size_px"])
    for frame, metadata in zip(result.frames, report_frames):
        name = f"step-{frame.step:02d}-frame-{frame.frame:02d}.png"
        (frame_dir / name).write_bytes(_png(
            size,
            size,
            bytearray(frame.rgba),
        ))
        metadata["file"] = f"frames/{name}"
    sheet = output / "contact-sheet.png"
    sheet.write_bytes(result.contact_sheet)
    manifest = output / "audit.json"
    manifest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", choices=AKITA_STATES, default="ready")
    parser.add_argument("--cycles", type=int, default=2)
    parser.add_argument("--density", type=float, default=PREVIEW_DENSITY,
                        help="device density multiplier; default matches the overlay's 3x fallback")
    parser.add_argument("--output", type=Path,
                        default=Path.home() / ".cache" / "codex-pet" / "animation-audit")
    args = parser.parse_args()
    if args.cycles < 1:
        parser.error("--cycles must be at least 1")
    if not math.isfinite(args.density) or args.density <= 0:
        parser.error("--density must be greater than 0")

    result = render_audit(args.state, args.cycles, args.density)
    manifest = write_audit(result, args.output)
    tail = result.report["tail_motion"]
    if isinstance(tail, dict):
        print(
            f"Tail motion at {result.report['display_size_px']}px: "
            f"{tail['changed_pixels_at_display_size']} changed pixels, "
            f"centroid shift {tail['alpha_centroid_delta_dp']} dp, "
            f"outer edge sweep {tail['outer_tail_edge_sweep_dp']} dp; "
            f"chest changes {tail['chest_changed_pixels_at_display_size']} pixels; "
            f"{'PASS' if tail['passed'] else 'FAIL'}"
        )
    print(f"Rendered {result.report['frame_count']} frames over "
          f"{result.report['duration_seconds']}s to {manifest.parent}")
    if isinstance(tail, dict) and not tail["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
