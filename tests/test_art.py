import struct
import unittest
import zlib

from codex_pet.art import (
    AKITA_FRAME_COUNTS,
    AKITA_READY_SEQUENCE,
    AKITA_READY_LOOP_START,
    advance_animation,
    animation_interval,
    icon,
    rgba_icon,
)
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

    def test_akita_looping_states_use_slow_idle_and_fluid_action_timing(self) -> None:
        self.assertEqual(animation_interval("akita", "idle", 0), 0.6)
        self.assertEqual(animation_interval("akita", "idle", 6), 0.6)
        self.assertEqual(animation_interval("akita", "running", 0), 0.08)
        self.assertEqual(animation_interval("akita", "needs_input", 3), 0.85)
        self.assertEqual(advance_animation("akita", "idle", 5), 6)
        self.assertEqual(advance_animation("akita", "idle", 7), 0)
        self.assertEqual(AKITA_FRAME_COUNTS["running"], 8)
        self.assertEqual(advance_animation("akita", "running", 7), 0)
        self.assertEqual(advance_animation("akita", "needs_input", 3), 0)

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

    def test_ready_loop_uses_the_wider_tail_wag_poses(self) -> None:
        self.assertEqual(AKITA_READY_SEQUENCE[10:12], (("idle", 6), ("idle", 7)))

    def test_akita_ready_hops_once_then_loops_breath_and_blink(self) -> None:
        frame = 0
        for _ in range(AKITA_READY_LOOP_START):
            self.assertIsNotNone(animation_interval("akita", "ready", frame))
            frame = advance_animation("akita", "ready", frame)
        self.assertEqual(frame, AKITA_READY_LOOP_START)

        self.assertEqual(animation_interval("akita", "ready", frame), 0.8)
        self.assertEqual(animation_interval("akita", "ready", 11), 0.6)
        self.assertEqual(animation_interval("akita", "ready", 12), 0.8)
        for _ in range(AKITA_FRAME_COUNTS["ready"] - AKITA_READY_LOOP_START):
            frame = advance_animation("akita", "ready", frame)
        self.assertEqual(frame, AKITA_READY_LOOP_START)

    def test_ready_loop_does_not_replay_a_jump_pose(self) -> None:
        loop = AKITA_READY_SEQUENCE[AKITA_READY_LOOP_START:]

        self.assertTrue(all(asset_state in ("idle", "blink")
                            for asset_state, _ in loop))

    def test_ready_hop_bends_down_before_lifting_off(self) -> None:
        self.assertEqual(
            AKITA_READY_SEQUENCE[:5],
            (("ready", 0), ("ready", 4), ("ready", 1), ("ready", 2), ("ready", 3)),
        )
        self.assertEqual(AKITA_READY_LOOP_START, 5)
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

    def test_ready_blink_is_slower_and_less_frequent(self) -> None:
        self.assertGreaterEqual(animation_interval("akita", "ready", 7) or 0, 0.18)
        cycle = sum(animation_interval("akita", "ready", frame) or 0
                    for frame in range(AKITA_READY_LOOP_START, AKITA_FRAME_COUNTS["ready"]))
        self.assertGreaterEqual(cycle, 3.5)

    def test_ready_hop_has_time_to_prepare_and_settle(self) -> None:
        hop = [animation_interval("akita", "ready", frame) or 0 for frame in range(AKITA_READY_LOOP_START)]

        self.assertGreaterEqual(hop[0], 0.3)
        self.assertGreaterEqual(hop[1], 0.14)
        self.assertGreaterEqual(hop[2], 0.18)
        self.assertGreaterEqual(hop[3], 0.2)
        self.assertGreaterEqual(hop[4], 0.32)
        self.assertGreaterEqual(sum(hop), 1.2)

    def test_akita_blocked_reaction_plays_once_then_holds(self) -> None:
        frame_count = AKITA_FRAME_COUNTS["blocked"]
        frame = 0
        for _ in range(frame_count):
            self.assertIsNotNone(animation_interval("akita", "blocked", frame))
            frame = advance_animation("akita", "blocked", frame)
        self.assertEqual(frame, frame_count)
        self.assertIsNone(animation_interval("akita", "blocked", frame))
        self.assertEqual(advance_animation("akita", "blocked", frame), frame)
        self.assertEqual(icon("blocked", frame), icon("blocked", frame_count - 1))

    def test_robot_animation_timing_remains_unchanged(self) -> None:
        self.assertEqual(animation_interval("robot", "running", 0), 2.0)
        self.assertEqual(advance_animation("robot", "running", 0), 1)

    def test_unknown_configured_appearance_falls_back_to_akita(self) -> None:
        self.assertEqual(icon("idle", appearance="unknown"), icon("idle"))

if __name__ == "__main__":
    unittest.main()
