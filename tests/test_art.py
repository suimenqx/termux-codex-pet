import struct
import unittest
import zlib

from codex_pet.animation import AKITA_FRAME_COUNTS
from codex_pet.art import icon, rgba_icon
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


def png_dimensions(image: bytes) -> tuple[int, int]:
    return struct.unpack_from(">II", image, 16)


def png_first_pixel(image: bytes) -> tuple[int, int, int, int]:
    offset = 8
    compressed = bytearray()
    while offset < len(image):
        size = struct.unpack_from(">I", image, offset)[0]
        kind = image[offset + 4:offset + 8]
        if kind == b"IDAT":
            compressed.extend(image[offset + 8:offset + 8 + size])
        offset += size + 12
    # PNG predictors have no left, above, or upper-left neighbors at (0, 0).
    raw = zlib.decompress(compressed)
    return tuple(raw[1:5])  # type: ignore[return-value]


def rgba_region(image: bytes, box: tuple[int, int, int, int]) -> bytes:
    x0, y0, x1, y1 = box
    return b"".join(
        image[(y * 256 + x0) * 4:(y * 256 + x1) * 4]
        for y in range(y0, y1)
    )


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

    def test_akita_uses_transparent_high_resolution_animation_frames(self) -> None:
        state_images = []
        for state in ("idle", "running", "needs_input", "ready", "blocked"):
            with self.subTest(state=state):
                frames = [icon(state, frame=frame)
                          for frame in range(AKITA_FRAME_COUNTS[state])]
                for image in frames:
                    self.assertEqual(png_dimensions(image), (256, 256))
                    self.assertEqual(image[24], 8)
                    self.assertEqual(image[25], 6)
                    self.assertEqual(png_first_pixel(image)[3], 0)
                if state == "ready":
                    # The loop deliberately reuses resting poses after its one-time hop.
                    self.assertEqual(len(set(frames)), AKITA_FRAME_COUNTS[state] - 2)
                else:
                    self.assertEqual(len(set(frames)), AKITA_FRAME_COUNTS[state])
                self.assertEqual(icon(state, frame=AKITA_FRAME_COUNTS[state]), frames[-1])
                state_images.append(frames[0])
        self.assertEqual(len(set(state_images)), 5)

    def test_akita_uses_state_specific_illustrations_and_count_badge(self) -> None:
        self.assertNotEqual(icon("idle"), icon("running"))
        self.assertNotEqual(icon("needs_input"), icon("blocked"))
        self.assertNotEqual(icon("running", count=1), icon("running", count=2))
        self.assertNotEqual(icon("running", count=2), icon("running", count=9))
        self.assertNotEqual(icon("running", count=9), icon("running", count=10))

    def test_akita_rgba_frames_remain_available_for_offline_audits(self) -> None:
        self.assertEqual(len(rgba_icon("idle", 0)), 256 * 256 * 4)
        self.assertNotEqual(rgba_icon("running", 0, 1), rgba_icon("running", 0, 2))

    def test_idle_tail_wag_is_more_visible_without_moving_the_chest(self) -> None:
        resting = rgba_icon("idle", 0)
        tail_high = rgba_icon("idle", 6)
        tail_low = rgba_icon("idle", 7)

        chest = (45, 120, 165, 220)
        tail = (180, 65, 256, 160)
        self.assertEqual(rgba_region(resting, chest), rgba_region(tail_high, chest))
        self.assertEqual(rgba_region(resting, chest), rgba_region(tail_low, chest))
        resting_tail = rgba_region(resting, tail)
        high_tail = rgba_region(tail_high, tail)
        low_tail = rgba_region(tail_low, tail)
        self.assertGreater(sum(resting_tail[i:i + 4] != high_tail[i:i + 4]
                               for i in range(0, len(resting_tail), 4)), 1000)
        self.assertGreater(sum(high_tail[i:i + 4] != low_tail[i:i + 4]
                               for i in range(0, len(high_tail), 4)), 1000)

    def test_ready_hop_bends_down_before_lifting_off(self) -> None:
        self.assertNotEqual(icon("ready", 0), icon("ready", 1))

    def test_ready_blink_only_changes_the_face_not_the_chest(self) -> None:
        before_blink = rgba_icon("ready", 6)
        blink = rgba_icon("ready", 7)
        after_blink = rgba_icon("ready", 8)

        chest = (70, 120, 180, 205)
        eyes = (62, 45, 195, 118)
        self.assertNotEqual(rgba_region(before_blink, eyes), rgba_region(blink, eyes))
        self.assertNotEqual(rgba_region(blink, eyes), rgba_region(after_blink, eyes))
        self.assertEqual(rgba_region(before_blink, chest), rgba_region(blink, chest))
        self.assertEqual(rgba_region(blink, chest), rgba_region(after_blink, chest))

    def test_blocked_final_frame_is_clamped_to_last_artwork(self) -> None:
        self.assertEqual(icon("blocked", AKITA_FRAME_COUNTS["blocked"]),
                         icon("blocked", AKITA_FRAME_COUNTS["blocked"] - 1))

    def test_unknown_configured_appearance_falls_back_to_akita(self) -> None:
        self.assertEqual(icon("idle", appearance="unknown"), icon("idle"))

if __name__ == "__main__":
    unittest.main()
