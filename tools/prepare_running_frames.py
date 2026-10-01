#!/usr/bin/env python3
"""Slice a four-by-two transparent running-pose sheet into 256px frames."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_pet.art import AKITA_SIZE, _decode_rgba_png, _png  # noqa: E402

SECOND_ROW_Y_OFFSET_PX = 10
# Match the visible footprint of the other Akita states in the fixed 64dp view.
RUNNING_ART_SCALE = 1.18


def split_sheet(sheet: bytes) -> tuple[bytes, ...]:
    """Downsample each cell with premultiplied alpha to protect fur edges."""
    width, height, pixels = _decode_rgba_png(sheet)
    if width != height * 2 or height < AKITA_SIZE * 2:
        raise ValueError("running sheet must be a 4 by 2 grid of square cells")

    frames = []
    for frame in range(8):
        column, row = frame % 4, frame // 4
        x0 = round(column * width / 4)
        x1 = round((column + 1) * width / 4)
        y0 = round(row * height / 2)
        y1 = round((row + 1) * height / 2)
        cell_width, cell_height = x1 - x0, y1 - y0
        output = bytearray(AKITA_SIZE * AKITA_SIZE * 4)
        canvas_center = AKITA_SIZE / 2

        for y in range(AKITA_SIZE):
            # Register the source sheet's lower row, then enlarge every pose
            # around the same canvas center without changing the GUI layout.
            registered_y = (canvas_center
                            + (y + 0.5 - canvas_center) / RUNNING_ART_SCALE
                            - (SECOND_ROW_Y_OFFSET_PX if row else 0))
            source_y = max(0.0, min(cell_height - 1.0,
                registered_y * cell_height / AKITA_SIZE - 0.5))
            top = math.floor(source_y)
            bottom = min(top + 1, cell_height - 1)
            fy = source_y - top
            for x in range(AKITA_SIZE):
                registered_x = (canvas_center
                                + (x + 0.5 - canvas_center) / RUNNING_ART_SCALE)
                source_x = max(0.0, min(cell_width - 1.0,
                    registered_x * cell_width / AKITA_SIZE - 0.5))
                left = math.floor(source_x)
                right = min(left + 1, cell_width - 1)
                fx = source_x - left
                samples = (
                    (left, top, (1 - fx) * (1 - fy)),
                    (right, top, fx * (1 - fy)),
                    (left, bottom, (1 - fx) * fy),
                    (right, bottom, fx * fy),
                )
                alpha = 0.0
                channels = [0.0, 0.0, 0.0]
                for sample_x, sample_y, weight in samples:
                    offset = ((y0 + sample_y) * width + x0 + sample_x) * 4
                    sample_alpha = pixels[offset + 3] / 255.0
                    alpha += sample_alpha * weight
                    for channel in range(3):
                        channels[channel] += pixels[offset + channel] * sample_alpha * weight
                destination = (y * AKITA_SIZE + x) * 4
                if alpha:
                    output[destination:destination + 3] = bytes(
                        min(255, round(channel / alpha)) for channel in channels
                    )
                output[destination + 3] = round(alpha * 255)

        frames.append(_png(AKITA_SIZE, AKITA_SIZE, output))
    return tuple(frames)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sheet", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    frames = split_sheet(args.sheet.read_bytes())
    for index, frame in enumerate(frames):
        (args.output / f"{index:02}.png").write_bytes(frame)


if __name__ == "__main__":
    main()
