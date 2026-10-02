import unittest

from tools.historical_art import _decode_rgba_png, _png
from tools.prepare_sprite_frames import split_sheet


def solid_sheet(columns: int, rows: int, cell_size: int) -> bytes:
    width, height = columns * cell_size, rows * cell_size
    pixels = bytearray(width * height * 4)
    colors = (
        (220, 30, 40, 255),
        (20, 210, 50, 255),
        (30, 60, 230, 255),
        (240, 210, 30, 255),
    )
    for y in range(height):
        for x in range(width):
            color = colors[(y // cell_size) * columns + x // cell_size]
            offset = (y * width + x) * 4
            pixels[offset:offset + 4] = bytes(color)
    return _png(width, height, pixels)


class SpriteSheetTests(unittest.TestCase):
    def test_splits_row_major_square_cells_to_runtime_size(self) -> None:
        frames = split_sheet(solid_sheet(2, 2, 512), 2, 2)

        self.assertEqual(len(frames), 4)
        expected = (
            (220, 30, 40, 255), (20, 210, 50, 255),
            (30, 60, 230, 255), (240, 210, 30, 255),
        )
        for frame, color in zip(frames, expected):
            width, height, pixels = _decode_rgba_png(frame)
            self.assertEqual((width, height), (256, 256))
            self.assertEqual(tuple(pixels[:4]), color)

    def test_accepts_fractional_pixel_grid_edges_when_cell_geometry_is_square(self) -> None:
        width, height, columns, rows = 10, 5, 4, 2
        pixels = bytearray(width * height * 4)
        colors = (
            (220, 30, 40, 255), (20, 210, 50, 255),
            (30, 60, 230, 255), (240, 210, 30, 255),
            (150, 40, 180, 255), (30, 170, 190, 255),
            (180, 150, 30, 255), (80, 90, 100, 255),
        )
        for y in range(height):
            for x in range(width):
                column = min(columns - 1, int((x + 0.5) * columns / width))
                row = min(rows - 1, int((y + 0.5) * rows / height))
                offset = (y * width + x) * 4
                pixels[offset:offset + 4] = bytes(colors[row * columns + column])

        frames = split_sheet(_png(width, height, pixels), columns, rows,
                             output_size=2)
        self.assertEqual(len(frames), 8)
        for frame, color in zip(frames, colors):
            _, _, frame_pixels = _decode_rgba_png(frame)
            self.assertEqual(tuple(frame_pixels[:4]), color)

    def test_rejects_non_square_cell_geometry(self) -> None:
        pixels = bytearray(16 * 16 * 4)
        with self.assertRaisesRegex(ValueError, "square cells"):
            split_sheet(_png(16, 16, pixels), 2, 1, output_size=4)

    def test_rejects_upscaling_and_frame_count_overflow(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be upscaled"):
            split_sheet(solid_sheet(1, 1, 128), 1, 1)
        with self.assertRaisesRegex(ValueError, "fit within"):
            split_sheet(solid_sheet(2, 1, 256), 2, 1, frame_count=3)

    def test_transparent_source_colors_do_not_bleed_into_filtered_edges(self) -> None:
        size = 512
        pixels = bytearray(bytes((255, 0, 0, 0)) * (size * size))
        offset = (100 * size + 100) * 4
        pixels[offset:offset + 4] = bytes((0, 0, 255, 255))

        (frame,) = split_sheet(_png(size, size, pixels), 1, 1)
        _, _, result = _decode_rgba_png(frame)
        offset = (50 * 256 + 50) * 4
        self.assertEqual(tuple(result[offset:offset + 4]), (0, 0, 255, 64))


if __name__ == "__main__":
    unittest.main()
