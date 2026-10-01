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

from codex_pet.animation import (  # noqa: E402
    AKITA_STATES,
    AKITA_READY_LOOP_START,
    playback_frames,
)
from codex_pet.art import (  # noqa: E402
    AKITA_SIZE,
    AKITA_ASSET_DIR,
    _png,
    rgba_icon,
    premultiplied_icon,
)

from tools.akita_rig import MODEL_PATH, clip_poses, load_model, skin_point  # noqa: E402

PET_SIZE_DP = 64
PREVIEW_DENSITY = 3.0
PAW_COLORS = {"hind_near": (255, 72, 194, 255),
              "hind_far": (48, 218, 245, 255),
              "fore_near": (157, 255, 78, 255),
              "fore_far": (255, 187, 67, 255)}
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


def _same_pose(actual: object, expected: object) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _same_pose(actual[key], value) for key, value in expected.items())
    if isinstance(expected, (list, tuple)):
        return (isinstance(actual, (list, tuple)) and len(actual) == len(expected)
                and all(_same_pose(a, b) for a, b in zip(actual, expected)))
    if isinstance(expected, float):
        return isinstance(actual, (int, float)) and math.isclose(actual, expected, abs_tol=1e-8)
    return actual == expected


def validated_clip(state: str, asset_dir: Path = AKITA_ASSET_DIR,
                   model_path: Path = MODEL_PATH) -> tuple[dict, list[dict]]:
    """Refuse stale annotations: validate source, PNG bytes, pixels, and timing."""
    manifest = json.loads((asset_dir / "rig-manifest.json").read_text())
    model = load_model(model_path)
    if hashlib.sha256(model_path.read_bytes()).hexdigest() != manifest["model_sha256"]:
        raise ValueError("stale rig model hash; export the clips again")
    for name in ("prepare_akita_model.py", "akita_rig.py", "render_akita.py"):
        if hashlib.sha256((ROOT / "tools" / name).read_bytes()).hexdigest() != manifest["authoring_sha256"].get(name):
            raise ValueError(f"stale authoring hash: {name}")
    for name, layer in model["layers"].items():
        if hashlib.sha256((model_path.parent / layer["file"]).read_bytes()).hexdigest() != layer["sha256"]:
            raise ValueError(f"stale layer hash: {name}")
    clip = manifest["clips"][state]
    if (clip["loop_start"] != (AKITA_READY_LOOP_START if state == "ready" else 0)
            or clip["final_hold"] != ("until_state_change" if state == "blocked" else None)):
        raise ValueError(f"stale playback lifecycle: {state}")
    frames = clip["frames"]
    expected = clip_poses(model, state)
    if len(frames) != len(expected):
        raise ValueError(f"frame count mismatch: {state}")
    for index, (frame, pose) in enumerate(zip(frames, expected)):
        filename = f"frames/{state}/{index:02}.png"
        if frame["file"] != filename or not _same_pose(frame, pose):
            raise ValueError(f"stale pose or timing: {filename}")
        if hashlib.sha256((asset_dir / filename).read_bytes()).hexdigest() != frame["sha256"]:
            raise ValueError(f"stale PNG hash: {filename}")
        # The live renderer must resolve the exact exported pixels, including
        # the Ready loop. This detects obsolete composition or frame aliases.
        if hashlib.sha256(rgba_icon(state, index)).hexdigest() != frame["rgba_sha256"]:
            raise ValueError(f"runtime pixels differ: {filename}")
        if hashlib.sha256(premultiplied_icon(state, index)).hexdigest() != frame['native_rgba_sha256']:
            raise ValueError(f"native runtime pixels differ: {filename}")
        for leg in frame["legs"].values():
            fraction = leg["visible_fraction"]
            if not isinstance(fraction, (int, float)) or not 0 <= fraction <= 1:
                raise ValueError(f"invalid visibility: {filename}")
    native = manifest['native_archive']
    if (native['file'] != 'native-frames.zip' or native['format'] != 'premultiplied RGBA8'
            or native['size'] != [AKITA_SIZE, AKITA_SIZE]
            or hashlib.sha256((asset_dir / native['file']).read_bytes()).hexdigest() != native['sha256']):
        raise ValueError('stale native archive hash or format')
    return model, frames


def rig_metrics(model: dict, poses: list[dict]) -> dict:
    bone_error = contact_error = 0.0
    scales = []
    borders = []
    for pose in poses:
        scales.extend(pose[part]["scale"] for part in ("head", "body", "tail"))
        for name, leg in pose["legs"].items():
            for a, b, length in zip(("root", "knee"), ("knee", "ankle"), leg["bone_lengths"]):
                bone_error = max(bone_error, abs(math.dist(leg[a], leg[b]) - length))
            if leg["contact"]:
                bind = model["limb_bind"][model["legs"][name]["kind"]]
                sole = skin_point((bind["paw"][0], bind["sole"]), bind, leg)
                contact_error = max(contact_error, abs(sole[1] - leg["ground_y"]))
        pixels = rgba_icon(pose["state"], pose["frame"])
        borders.append(max(pixels[(y * 256 + x) * 4 + 3]
                           for y, x in ([(0, x) for x in range(256)]
                                        + [(255, x) for x in range(256)]
                                        + [(y, 0) for y in range(256)]
                                        + [(y, 255) for y in range(256)])))
    paws = {}
    for name in model["legs"]:
        tracks = [pose["legs"][name] for pose in poses]
        paws[name] = {
            "positions": [{"frame": pose["frame"], "xy": leg["paw"],
                           "contact": leg["contact"], "visible_fraction": leg["visible_fraction"],
                           "marker_visible": leg["visible_fraction"] >= .5}
                          for pose, leg in zip(poses, tracks)],
            "horizontal_range_dp": (max(p["paw"][0] for p in tracks) - min(p["paw"][0] for p in tracks)) / 4,
            "vertical_range_dp": (max(p["paw"][1] for p in tracks) - min(p["paw"][1] for p in tracks)) / 4,
            "contact_frames": [p["frame"] for p in poses if p["legs"][name]["contact"]],
        }
    tail_angles = [math.degrees(pose["tail"]["angle"]) for pose in poses]
    return {
        "measurement": "hash-verified exported rig and production RGBA; design coordinates / 4 = dp",
        "scale_range": [min(scales), max(scales)],
        "max_bone_length_error_px": bone_error,
        "max_contact_height_error_px": contact_error,
        "border_alpha_max": max(borders),
        "tail_angle_range_degrees": [min(tail_angles), max(tail_angles)],
        "paws": paws,
        "passed": min(scales) == max(scales) == 1 and bone_error < 1e-7
                  and contact_error < 1e-7 and max(borders) == 0,
        "limitation": "Numeric registration/contact checks do not certify perceived motion or device frame delivery.",
    }


def _resize_rgba(source: bytes, size: int) -> bytes:
    """Scale the offline RGBA frame with premultiplied bilinear sampling."""
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


def _draw_paw_marker(canvas: bytearray, width: int, center_x: int, center_y: int,
                     color: tuple[int, int, int, int], radius: int) -> None:
    for y in range(center_y - radius, center_y + radius + 1):
        for x in range(center_x - radius, center_x + radius + 1):
            if (x < 0 or y < 0 or (x - center_x) ** 2 + (y - center_y) ** 2
                    > radius * radius or (x - center_x) ** 2 + (y - center_y) ** 2
                    < (radius - 1) * (radius - 1)):
                continue
            offset = (y * width + x) * 4
            canvas[offset:offset + 4] = bytes(color)


def _contact_sheet(frames: tuple[RenderedFrame, ...], size: int,
                   poses: list[dict]) -> bytes:
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
        if poses[0]["state"] == "running":
            marker_radius = max(2, round(size / AKITA_SIZE * 6))
            for name, leg in poses[min(frame.frame, len(poses) - 1)]["legs"].items():
                # A ring marks a majority-visible paw sample, not an inferred
                # position painted on top of an occluding leg.
                if leg["visible_fraction"] < .5:
                    continue
                point = leg["paw"]
                marker_x = cell_x + round(point[0] * size / AKITA_SIZE)
                marker_y = cell_y + round(point[1] * size / AKITA_SIZE)
                _draw_paw_marker(canvas, width, marker_x, marker_y,
                                 PAW_COLORS[name], marker_radius)
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

    model, poses = validated_clip(state)
    rig = rig_metrics(model, poses)
    scale_cache: dict[int, bytes] = {}
    rendered: list[RenderedFrame] = []
    for step, scheduled in enumerate(playback_frames("akita", state, cycles)):
        frame = scheduled.frame
        pixels = scale_cache.get(frame)
        if pixels is None:
            pixels = _resize_rgba(rgba_icon(state, frame), display_size)
            scale_cache[frame] = pixels
        rendered.append(RenderedFrame(step, frame, scheduled.duration_seconds, pixels))

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
        "rig": rig,
        "passed": rig["passed"],
        "contact_sheet": "contact-sheet.png",
    }
    return RenderAudit(report, frames, _contact_sheet(frames, display_size, poses))


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
    print(f"{args.state}: {result.report['frame_count']} exposures, "
          f"{result.report['duration_seconds']}s; fixed scale/bones/contact "
          f"{'PASS' if result.report['passed'] else 'FAIL'}; {manifest}")
    return 0 if result.report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
