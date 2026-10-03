#!/usr/bin/env python3
"""Normalize a cleaned v2 running cycle to the current production envelope.

The v2 package owns the cleaned matte and motion. This script computes one
fixed affine transform for the whole cycle from the union alpha bounds of v2
and the current production running frames. It never scales frames individually
and uses premultiplied-alpha resampling to avoid creating a new matte halo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


FRAME_COUNT = 20
RUNTIME_SIZE = 256
DISPLAY_SIZE = 192


def _paths(root: Path) -> list[Path]:
    paths = [root / f"{index:02d}.png" for index in range(FRAME_COUNT)]
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing frames: {', '.join(map(str, missing))}")
    return paths


def _union_bbox(root: Path, threshold: int = 128) -> tuple[int, int, int, int]:
    bounds = []
    for path in _paths(root):
        alpha = np.asarray(Image.open(path).convert("RGBA"))[..., 3]
        ys, xs = np.where(alpha >= threshold)
        if len(xs):
            bounds.append((int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())))
    if not bounds:
        raise ValueError(f"no visible pixels in {root}")
    return (
        min(box[0] for box in bounds),
        min(box[1] for box in bounds),
        max(box[2] for box in bounds),
        max(box[3] for box in bounds),
    )


def _edge_geometry(box: tuple[int, int, int, int]) -> tuple[float, float, float]:
    x0, y0, x1, y1 = box
    return ((x0 + x1 + 1) / 2.0, float(y1 + 1), float(x1 - x0 + 1))


def _resize_plane(plane: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    image = Image.fromarray(np.clip(np.rint(plane), 0, 255).astype(np.uint8), "L")
    return np.asarray(image.resize(size, Image.Resampling.LANCZOS), dtype=np.float32)


def _premultiplied_resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    data = np.asarray(image.convert("RGBA"), dtype=np.float32)
    alpha = data[..., 3]
    premultiplied = data[..., :3] * (alpha[..., None] / 255.0)
    resized_alpha = _resize_plane(alpha, size)
    resized_rgb = np.stack(
        [_resize_plane(premultiplied[..., channel], size) for channel in range(3)],
        axis=-1,
    )
    rgb = np.zeros_like(resized_rgb)
    np.divide(
        resized_rgb * 255.0,
        np.maximum(resized_alpha[..., None], 1.0),
        out=rgb,
        where=resized_alpha[..., None] > 0,
    )
    alpha_u8 = np.clip(np.rint(resized_alpha), 0, 255).astype(np.uint8)
    output = np.dstack((np.clip(np.rint(rgb), 0, 255).astype(np.uint8), alpha_u8))
    output[alpha_u8 == 0, :3] = 0
    return Image.fromarray(output, "RGBA")


def _transform(image: Image.Image, scale: float, source_anchor: tuple[float, float],
               target_anchor: tuple[float, float], size: int) -> Image.Image:
    """Transform one image with x' = target + scale * (x - source)."""
    sx, sy = source_anchor
    tx, ty = target_anchor
    matrix = (
        1.0 / scale,
        0.0,
        sx - tx / scale,
        0.0,
        1.0 / scale,
        sy - ty / scale,
    )
    data = np.asarray(image.convert("RGBA"), dtype=np.float32)
    alpha = data[..., 3]
    premultiplied = data[..., :3] * (alpha[..., None] / 255.0)

    def warp(plane: np.ndarray) -> np.ndarray:
        return np.asarray(
            Image.fromarray(np.clip(np.rint(plane), 0, 255).astype(np.uint8), "L")
            .transform((size, size), Image.Transform.AFFINE, matrix,
                       resample=Image.Resampling.BICUBIC, fillcolor=0),
            dtype=np.float32,
        )

    warped_alpha = warp(alpha)
    warped_rgb = np.stack([warp(premultiplied[..., c]) for c in range(3)], axis=-1)
    rgb = np.zeros_like(warped_rgb)
    np.divide(
        warped_rgb * 255.0,
        np.maximum(warped_alpha[..., None], 1.0),
        out=rgb,
        where=warped_alpha[..., None] > 0,
    )
    alpha_u8 = np.clip(np.rint(warped_alpha), 0, 255).astype(np.uint8)
    output = np.dstack((np.clip(np.rint(rgb), 0, 255).astype(np.uint8), alpha_u8))
    output[alpha_u8 == 0, :3] = 0
    return Image.fromarray(output, "RGBA")


def _composite(image: Image.Image, background: tuple[int, int, int]) -> Image.Image:
    canvas = Image.new("RGBA", image.size, (*background, 255))
    canvas.alpha_composite(image)
    return canvas.convert("RGB").resize((DISPLAY_SIZE, DISPLAY_SIZE), Image.Resampling.LANCZOS)


def _comparison(images: list[tuple[str, Image.Image]], output: Path) -> None:
    label_height = 21
    width = DISPLAY_SIZE * len(images)
    sheet = Image.new("RGB", (width, (DISPLAY_SIZE + label_height) * 2), (232, 232, 232))
    draw = ImageDraw.Draw(sheet)
    for row, background in enumerate(((245, 245, 245), (38, 38, 42))):
        for column, (label, image) in enumerate(images):
            x = column * DISPLAY_SIZE
            y = row * (DISPLAY_SIZE + label_height)
            sheet.paste(_composite(image, background), (x, y))
            draw.rectangle((x, y + DISPLAY_SIZE, x + DISPLAY_SIZE, y + DISPLAY_SIZE + label_height), fill=(232, 232, 232))
            draw.text((x + 4, y + DISPLAY_SIZE + 3), label, fill=(20, 20, 20))
    sheet.save(output)


def _contact(frames: dict[str, list[Image.Image]], output: Path) -> None:
    labels = list(frames)
    indices = (0, 6, 14)
    label_height = 18
    sheet = Image.new("RGB", (DISPLAY_SIZE * len(indices), (DISPLAY_SIZE + label_height) * len(labels)), (232, 232, 232))
    draw = ImageDraw.Draw(sheet)
    for row, label in enumerate(labels):
        for column, index in enumerate(indices):
            x = column * DISPLAY_SIZE
            y = row * (DISPLAY_SIZE + label_height)
            sheet.paste(_composite(frames[label][index], (245, 245, 245)), (x, y))
            draw.rectangle((x, y + DISPLAY_SIZE, x + DISPLAY_SIZE, y + DISPLAY_SIZE + label_height), fill=(232, 232, 232))
            draw.text((x + 4, y + DISPLAY_SIZE + 2), f"{label} / {index:02d}", fill=(20, 20, 20))
    sheet.save(output)


def _write_manifest(directory: Path, output: Path) -> None:
    durations = [0.042 if index % 3 != 2 else 0.041 for index in range(FRAME_COUNT)]
    manifest = {
        "frames": [
            {
                "file": f"{directory.name}/{index:02d}.png",
                "seconds": durations[index],
                "sha256": hashlib.sha256((directory / f"{index:02d}.png").read_bytes()).hexdigest(),
            }
            for index in range(FRAME_COUNT)
        ]
    }
    output.write_text(json.dumps(manifest, indent=1) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v2-256", type=Path, required=True)
    parser.add_argument("--v2-hd", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    v2_256 = _paths(args.v2_256)
    v2_hd = _paths(args.v2_hd)
    target = _paths(args.target)
    source_box = _union_bbox(args.v2_256)
    target_box = _union_bbox(args.target)
    source_center, source_bottom, source_width = _edge_geometry(source_box)
    target_center, target_bottom, target_width = _edge_geometry(target_box)
    target_height = target_box[3] - target_box[1] + 1
    source_height = source_box[3] - source_box[1] + 1
    scale = min(target_width / source_width, target_height / source_height)

    args.output.mkdir(parents=True, exist_ok=True)
    v2_normalized: list[Image.Image] = []
    hd_normalized: list[Image.Image] = []
    for source_path, hd_path in zip(v2_256, v2_hd):
        v2_image = _transform(Image.open(source_path), scale, (source_center, source_bottom),
                               (target_center, target_bottom), RUNTIME_SIZE)
        hd_image = _transform(Image.open(hd_path), scale,
                               (source_center * 3, source_bottom * 3),
                               (target_center * 3, target_bottom * 3), 768)
        hd_downsampled = _premultiplied_resize(hd_image, (RUNTIME_SIZE, RUNTIME_SIZE))
        v2_normalized.append(v2_image)
        hd_normalized.append(hd_downsampled)

    v2_dir = args.output / "frames_256-v2-normalized"
    hd_dir = args.output / "frames_256-hd-normalized"
    v2_dir.mkdir(exist_ok=True)
    hd_dir.mkdir(exist_ok=True)
    for index, (v2_image, hd_image) in enumerate(zip(v2_normalized, hd_normalized)):
        v2_image.save(v2_dir / f"{index:02d}.png")
        hd_image.save(hd_dir / f"{index:02d}.png")
    _write_manifest(v2_dir, args.output / "candidate-v2-normalized.json")
    _write_manifest(hd_dir, args.output / "candidate-v2-hd-normalized.json")

    raw_00 = Image.open(v2_256[0]).convert("RGBA")
    current_00 = Image.open(target[0]).convert("RGBA")
    _comparison([
        ("current", current_00),
        ("v2 raw", raw_00),
        ("v2 norm", v2_normalized[0]),
        ("v2 HD norm", hd_normalized[0]),
    ], args.output / "v2-normalization-compare-192px.png")
    _contact({
        "current": [Image.open(path).convert("RGBA") for path in target],
        "v2 raw": [Image.open(path).convert("RGBA") for path in v2_256],
        "v2 norm": v2_normalized,
        "v2 HD norm": hd_normalized,
    }, args.output / "v2-normalization-contact-192px.png")

    metadata = {
        "source_union_bbox_256": source_box,
        "target_union_bbox_256": target_box,
        "fixed_scale": scale,
        "source_anchor_256": [source_center, source_bottom],
        "target_anchor_256": [target_center, target_bottom],
        "source_archive": "akita-run-grok-v2.zip",
        "note": "one transform for all 20 frames; no per-frame fit or pose change",
        "v2_raw_frame_sha256": [hashlib.sha256(path.read_bytes()).hexdigest() for path in v2_256],
        "v2_normalized_sha256": [hashlib.sha256((v2_dir / f"{index:02d}.png").read_bytes()).hexdigest() for index in range(FRAME_COUNT)],
        "v2_hd_normalized_sha256": [hashlib.sha256((hd_dir / f"{index:02d}.png").read_bytes()).hexdigest() for index in range(FRAME_COUNT)],
    }
    (args.output / "xform-normalized.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({
        "source_union_bbox_256": source_box,
        "target_union_bbox_256": target_box,
        "fixed_scale": scale,
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
