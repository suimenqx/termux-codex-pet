#!/usr/bin/env python3
"""Split a uniform square-cell sheet and downsample without changing its scale."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_pet.art import AKITA_SIZE, _decode_rgba_png, _png  # noqa: E402


def split_sheet(
    sheet: bytes,
    columns: int,
    rows: int,
    frame_count: int | None = None,
    output_size: int = AKITA_SIZE,
) -> tuple[bytes, ...]:
    """Return row-major frames from a square-cell sheet.

    The sheet is only cropped and resampled to the runtime raster size. It is
    never zoomed, repositioned, or upscaled. Alpha is filtered in premultiplied
    form and written back as straight-alpha RGBA PNG.
    """
    if columns < 1 or rows < 1 or output_size < 1:
        raise ValueError("columns, rows, and output size must be positive")

    width, height, pixels = _decode_rgba_png(sheet)
    if width * rows != height * columns:
        raise ValueError("sprite sheet must divide into equal square cells")

    cell_width = width / columns
    cell_height = height / rows
    if cell_width < output_size or cell_height < output_size:
        raise ValueError("sprite cells must not be upscaled to the output size")

    capacity = columns * rows
    count = capacity if frame_count is None else frame_count
    if count < 1 or count > capacity:
        raise ValueError("frame count must fit within the sprite sheet")

    frames = []
    for frame in range(count):
        column, row = frame % columns, frame // columns
        left_edge = column * cell_width
        right_edge = (column + 1) * cell_width
        top_edge = row * cell_height
        bottom_edge = (row + 1) * cell_height

        # Fractional grid edges are allowed when the complete sheet still has
        # an exact square-cell ratio (for example, 1774 x 887 at 4 x 2).
        left_pixel = max(0, math.ceil(left_edge - 0.5))
        right_pixel = min(width - 1, math.ceil(right_edge - 0.5) - 1)
        top_pixel = max(0, math.ceil(top_edge - 0.5))
        bottom_pixel = min(height - 1, math.ceil(bottom_edge - 0.5) - 1)

        output = bytearray(output_size * output_size * 4)
        for y in range(output_size):
            source_y = top_edge + (y + 0.5) * cell_height / output_size - 0.5
            source_y = max(top_pixel, min(bottom_pixel, source_y))
            top = math.floor(source_y)
            bottom = min(top + 1, bottom_pixel)
            fy = source_y - top

            for x in range(output_size):
                source_x = left_edge + (x + 0.5) * cell_width / output_size - 0.5
                source_x = max(left_pixel, min(right_pixel, source_x))
                left = math.floor(source_x)
                right = min(left + 1, right_pixel)
                fx = source_x - left
                samples = (
                    (left, top, (1 - fx) * (1 - fy)),
                    (right, top, fx * (1 - fy)),
                    (left, bottom, (1 - fx) * fy),
                    (right, bottom, fx * fy),
                )
                alpha = 0.0
                premultiplied = [0.0, 0.0, 0.0]
                for sample_x, sample_y, weight in samples:
                    offset = (sample_y * width + sample_x) * 4
                    sample_alpha = pixels[offset + 3] / 255.0
                    alpha += sample_alpha * weight
                    for channel in range(3):
                        premultiplied[channel] += (
                            pixels[offset + channel] * sample_alpha * weight
                        )

                destination = (y * output_size + x) * 4
                if alpha:
                    output[destination:destination + 3] = bytes(
                        min(255, round(channel / alpha))
                        for channel in premultiplied
                    )
                output[destination + 3] = round(alpha * 255)

        frames.append(_png(output_size, output_size, output))

    return tuple(frames)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sheet", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--columns", type=int, required=True)
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--frame-count", type=int)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    frames = split_sheet(
        args.sheet.read_bytes(), args.columns, args.rows, args.frame_count
    )
    for index, frame in enumerate(frames):
        (args.output / f"{index:02}.png").write_bytes(frame)


if __name__ == "__main__":
    main()
