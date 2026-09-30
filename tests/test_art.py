import struct
import unittest
import zlib

from codex_pet.art import advance_animation, animation_interval, icon
from codex_pet.pets import DEFAULT_APPEARANCE


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
    def test_pixels_outside_the_robot_silhouette_are_fully_transparent(self) -> None:
        for state in ("idle", "running", "needs_input", "ready", "blocked"):
            with self.subTest(state=state):
                image = icon(state, appearance="robot")
                self.assertEqual(png_pixel(image, 14, 15)[3], 0)
                self.assertEqual(png_pixel(image, 63, 63)[3], 0)

    def test_face_expression_changes_with_status(self) -> None:
        blush = (226, 126, 147, 255)
        face = (43, 55, 70, 255)
        needs_input = (255, 191, 75, 255)
        blocked = (255, 108, 117, 255)

        self.assertEqual(png_pixel(icon("idle", appearance="robot"), 18, 39), blush)
        self.assertEqual(png_pixel(icon("needs_input", appearance="robot"), 32, 42), face)
        self.assertEqual(png_pixel(icon("needs_input", appearance="robot"), 29, 42), needs_input)
        self.assertEqual(png_pixel(icon("ready", appearance="robot"), 24, 32), face)
        self.assertEqual(png_pixel(icon("blocked", appearance="robot"), 32, 40), blocked)


class AkitaArtTests(unittest.TestCase):
    def test_akita_is_the_default_and_robot_remains_selectable(self) -> None:
        self.assertEqual(DEFAULT_APPEARANCE, "akita")
        self.assertEqual(icon("idle"), icon("idle", appearance="akita"))
        self.assertNotEqual(icon("idle"), icon("idle", appearance="robot"))

    def test_each_akita_state_has_distinct_animation_frames(self) -> None:
        for state in ("idle", "running", "needs_input", "ready", "blocked"):
            with self.subTest(state=state):
                frames = {icon(state, frame=frame) for frame in range(5)}
                self.assertGreater(len(frames), 1)

    def test_animated_states_use_bounded_state_specific_cadence(self) -> None:
        self.assertEqual(animation_interval("akita", "running", 0), 0.14)
        self.assertEqual(animation_interval("akita", "ready", 4), None)
        self.assertEqual(advance_animation("akita", "running", 3), 0)
        self.assertEqual(advance_animation("akita", "ready", 4), 4)

    def test_unknown_configured_appearance_falls_back_to_akita(self) -> None:
        self.assertEqual(icon("idle", appearance="unknown"), icon("idle"))

    def test_state_badges_and_multi_session_count_are_visible(self) -> None:
        self.assertEqual(png_pixel(icon("needs_input"), 53, 4), (49, 39, 34, 255))
        self.assertNotEqual(icon("running", count=1), icon("running", count=2))


if __name__ == "__main__":
    unittest.main()
