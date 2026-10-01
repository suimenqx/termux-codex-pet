from pathlib import Path
import struct
import unittest
import zlib

from codex_pet.animation import AKITA_FRAME_COUNTS, AKITA_READY_LOOP_START
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
    def test_state_fallback_images_match_the_first_animation_frame(self) -> None:
        root = Path(__file__).resolve().parents[1] / "codex_pet/assets/akita"
        for state in AKITA_FRAME_COUNTS:
            with self.subTest(state=state):
                fallback = (root / f"{state}.png").read_bytes()
                first_frame = (root / "frames" / state / "00.png").read_bytes()
                self.assertEqual(fallback, first_frame)

    def test_animation_frame_files_are_contiguous_and_complete(self) -> None:
        root = Path(__file__).resolve().parents[1] / "codex_pet/assets/akita/frames"
        source_frame_counts = AKITA_FRAME_COUNTS
        for state, frame_count in source_frame_counts.items():
            with self.subTest(state=state):
                frame_names = sorted(path.name for path in (root / state).glob("*.png"))
                expected_names = [f"{frame:02}.png" for frame in range(frame_count)]
                self.assertEqual(frame_names, expected_names)

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
                # A one-shot may finish with repeated holds; locomotion must
                # supply distinct physical poses instead of duplicate frames.
                self.assertGreater(len(set(frames)), 4)
                if state == "running":
                    self.assertEqual(len(set(frames)), 32)
                self.assertEqual(icon(state, frame=AKITA_FRAME_COUNTS[state]), frames[-1])
                state_images.append(frames[0])
        self.assertEqual(len(set(state_images)), 5)

    def test_akita_uses_state_specific_illustrations_and_count_badge(self) -> None:
        self.assertNotEqual(icon("idle"), icon("running"))
        self.assertNotEqual(icon("needs_input"), icon("blocked"))
        self.assertNotEqual(icon("running", count=1), icon("running", count=2))
        self.assertNotEqual(icon("running", count=2), icon("running", count=9))
        self.assertNotEqual(icon("running", count=9), icon("running", count=10))

    def test_ready_rest_keeps_its_green_collar_on_the_shared_idle_pose(self) -> None:
        for frame in (0, 7, 20, 22, 31):
            idle = rgba_icon("idle", frame)
            ready = rgba_icon("ready", AKITA_READY_LOOP_START + frame)
            self.assertEqual(rgba_region(idle, (0, 0, 256, 130)),
                             rgba_region(ready, (0, 0, 256, 130)))
            self.assertEqual(rgba_region(idle, (0, 172, 256, 256)),
                             rgba_region(ready, (0, 172, 256, 256)))
            self.assertNotEqual(idle, ready)

    def test_akita_rgba_frames_remain_available_for_offline_audits(self) -> None:
        self.assertEqual(len(rgba_icon("idle", 0)), 256 * 256 * 4)
        self.assertNotEqual(rgba_icon("running", 0, 1), rgba_icon("running", 0, 2))

    def test_all_frames_keep_a_transparent_margin(self) -> None:
        for state, count in AKITA_FRAME_COUNTS.items():
            for frame in range(count):
                pixels = rgba_icon(state, frame)
                border = [(0, x) for x in range(256)] + [(255, x) for x in range(256)]
                border += [(y, 0) for y in range(256)] + [(y, 255) for y in range(256)]
                self.assertEqual(max(pixels[(y * 256 + x) * 4 + 3] for y, x in border), 0,
                                 (state, frame))

    def test_idle_blink_and_tail_are_present_in_exported_pixels(self) -> None:
        self.assertNotEqual(rgba_region(rgba_icon("idle", 20), (145, 70, 222, 110)),
                            rgba_region(rgba_icon("idle", 22), (145, 70, 222, 110)))
        self.assertNotEqual(rgba_region(rgba_icon("idle", 7), (20, 60, 105, 130)),
                            rgba_region(rgba_icon("idle", 25), (20, 60, 105, 130)))

    def test_blocked_final_frame_is_clamped_to_last_artwork(self) -> None:
        self.assertEqual(icon("blocked", AKITA_FRAME_COUNTS["blocked"]),
                         icon("blocked", AKITA_FRAME_COUNTS["blocked"] - 1))

    def test_unknown_configured_appearance_falls_back_to_akita(self) -> None:
        self.assertEqual(icon("idle", appearance="unknown"), icon("idle"))

if __name__ == "__main__":
    unittest.main()
