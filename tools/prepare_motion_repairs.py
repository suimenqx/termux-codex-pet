#!/usr/bin/env python3
"""Export the reviewed generated limb patches while locking original pixels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_pet.art import _decode_rgba_png, _png
from tools.prepare_sprite_frames import split_sheet


def replace_region(original: bytes, replacement: bytes,
                   box: tuple[int, int, int, int], feather: int = 6) -> bytes:
    """Import a generated patch; blend only inside its explicit edit boundary.

    This is an offline spatial seam, never a temporal blend of animation poses.
    All decoded pixels outside the rectangle remain exactly the original.
    """
    width, height, before = _decode_rgba_png(original)
    rw, rh, after = _decode_rgba_png(replacement)
    if (width, height) != (rw, rh):
        raise ValueError("patch and original must use the same canvas")
    x0, y0, x1, y1 = box
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError("edit boundary must fit the original canvas")
    if feather < 0 or feather * 2 >= min(x1 - x0, y1 - y0):
        raise ValueError("feather must leave an unblended patch interior")
    result = bytearray(before)
    for y in range(y0, y1):
        for x in range(x0, x1):
            distance = min(x - x0 + .5, x1 - x - .5, y - y0 + .5, y1 - y - .5)
            weight = min(1.0, distance / feather) if feather else 1.0
            weight = weight * weight * (3 - 2 * weight)
            i = (y * width + x) * 4
            old_alpha, new_alpha = before[i + 3] * (1 - weight), after[i + 3] * weight
            alpha = old_alpha + new_alpha
            for c in range(3):
                result[i + c] = round((before[i + c] * old_alpha + after[i + c] * new_alpha) / alpha) if alpha else 0
            result[i + 3] = round(alpha)
    return _png(width, height, result)


def export(manifest: Path, output: Path) -> None:
    if output.exists():
        raise ValueError("choose a new output directory")
    recipe = json.loads(manifest.read_text())
    frames = []
    for item in recipe["exports"]:
        name = Path(item["output"])
        if name.is_absolute() or ".." in name.parts or name.suffix != ".png":
            raise ValueError("output names must be relative PNG paths inside the export")
        if any(name == previous for previous, _ in frames):
            raise ValueError("duplicate export name")
        candidate = split_sheet((manifest.parent / item["source"]).read_bytes(), 1, 1, 1)[0]
        if "original" in item:
            candidate = replace_region((manifest.parent / item["original"]).read_bytes(),
                                       candidate, tuple(item["box"]), item["feather"])
        frames.append((name, candidate))
    output.mkdir(parents=True)
    for name, png in frames:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(png)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    export(args.manifest, args.output)
