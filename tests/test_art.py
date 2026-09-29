import struct
import unittest
import zlib

from codex_pet.art import icon


def png_pixel(image: bytes, x: int, y: int) -> tuple[int, int, int, int]:
    offset = 8
    compressed = bytearray()
    while offset < len(image):
        size = struct.unpack_from(">I", image, offset)[0]
        kind = image[offset + 4:offset + 8]
        data = image[offset + 8:offset + 8 + size]
        if kind == b"IDAT":
            compressed.extend(data)
        offset += size + 12
    pixels = zlib.decompress(compressed)
    stride = 1 + 64 * 4
    row = pixels[y * stride:(y + 1) * stride]
    start = 1 + x * 4
    return tuple(row[start:start + 4])  # type: ignore[return-value]


class RobotArtTests(unittest.TestCase):
    def test_face_expression_changes_with_status(self) -> None:
        blush = (226, 126, 147, 255)
        face = (43, 55, 70, 255)
        needs_input = (255, 191, 75, 255)
        blocked = (255, 108, 117, 255)

        self.assertEqual(png_pixel(icon("idle"), 18, 39), blush)
        self.assertEqual(png_pixel(icon("needs_input"), 32, 42), face)
        self.assertEqual(png_pixel(icon("needs_input"), 29, 42), needs_input)
        self.assertEqual(png_pixel(icon("ready"), 24, 32), face)
        self.assertEqual(png_pixel(icon("blocked"), 32, 40), blocked)


if __name__ == "__main__":
    unittest.main()
