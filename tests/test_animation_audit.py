import json
from pathlib import Path
import struct
import tempfile
import unittest

from codex_pet.art import rgba_icon
from tools.audit_animation import render_audit, write_audit
from tools.prepare_running_frames import split_sheet
from tools.preview_animation import _timeline


class AnimationAuditTests(unittest.TestCase):
    def test_audit_renders_the_production_ready_sequence_at_overlay_size(self) -> None:
        result = render_audit("ready", cycles=2, density=3)
        preview = _timeline("ready", cycles=2)

        self.assertEqual(
            [frame.frame for frame in result.frames],
            [frame["frame"] for frame in preview],
        )
        self.assertEqual(
            [frame.delay_seconds for frame in result.frames],
            [frame["seconds"] for frame in preview],
        )
        self.assertTrue(all(len(frame.rgba) == 192 * 192 * 4
                            for frame in result.frames))
        self.assertEqual(result.report["duration_seconds"], 10.02)

        width, height = struct.unpack_from(">II", result.contact_sheet, 16)
        self.assertEqual(width, 828)
        self.assertEqual(height, 1344)

    def test_tail_motion_survives_display_scaling_while_chest_stays_still(self) -> None:
        result = render_audit("ready", cycles=1, density=3)
        tail = result.report["tail_motion"]

        self.assertIsInstance(tail, dict)
        self.assertTrue(tail["passed"])
        self.assertGreaterEqual(
            tail["changed_pixels_at_display_size"], tail["minimum_changed_pixels"]
        )
        self.assertGreaterEqual(
            tail["alpha_centroid_delta_dp"], tail["minimum_centroid_delta_dp"]
        )
        self.assertGreaterEqual(
            tail["outer_tail_edge_sweep_dp"], tail["minimum_edge_sweep_dp"]
        )
        self.assertEqual(tail["chest_changed_pixels_at_display_size"], 0)

    def test_audit_normalizes_tail_motion_for_a_low_density_display(self) -> None:
        result = render_audit("ready", cycles=1, density=1)
        tail = result.report["tail_motion"]

        self.assertEqual(result.report["display_size_px"], 64)
        self.assertIsInstance(tail, dict)
        self.assertTrue(tail["passed"])

    def test_running_tracks_all_four_paws_relative_to_the_hip(self) -> None:
        result = render_audit("running", cycles=2, density=3)
        hind_legs = result.report["hind_leg_motion"]
        fore_legs = result.report["fore_leg_motion"]
        preview = _timeline("running", cycles=2)

        self.assertIsInstance(hind_legs, dict)
        self.assertTrue(hind_legs["passed"], hind_legs)
        self.assertTrue(hind_legs["all_paw_markers_on_visible_art"])
        self.assertTrue(hind_legs["pair_coordination_passed"])
        self.assertGreaterEqual(hind_legs["opposed_transitions"], 2)
        self.assertGreaterEqual(hind_legs["mean_pair_separation_dp"], 6.0)
        for leg in hind_legs["legs"].values():
            self.assertGreaterEqual(leg["horizontal_range_dp"],
                                    leg["minimum_horizontal_range_dp"])
            self.assertGreaterEqual(leg["vertical_range_dp"],
                                    leg["minimum_vertical_range_dp"])
            self.assertGreaterEqual(leg["cycle_path_length_dp"],
                                    leg["minimum_cycle_path_length_dp"])
        self.assertIsInstance(fore_legs, dict)
        self.assertTrue(fore_legs["passed"], fore_legs)
        self.assertTrue(fore_legs["all_paw_markers_on_visible_art"])
        self.assertTrue(fore_legs["pair_coordination_passed"])
        self.assertGreaterEqual(fore_legs["separated_poses"], 5)
        self.assertGreaterEqual(fore_legs["opposed_transitions"], 3)
        self.assertGreaterEqual(fore_legs["mean_pair_separation_dp"], 8.0)
        for name, leg in fore_legs["legs"].items():
            self.assertEqual(len(leg["positions"]), 8)
            self.assertGreaterEqual(leg["visible_poses"], 7)
            self.assertTrue(all(
                point["opaque_coverage"] >= 0.8
                and point["mean_blue_channel"] >= 120.0
                for point in leg["positions"] if point["visible"]
            ), name)
        self.assertFalse(fore_legs["legs"]["fore_far"]["positions"][1]["visible"])
        self.assertEqual(result.report["frame_count"], 16)
        self.assertEqual(result.report["duration_seconds"], 1.28)
        self.assertEqual(
            [frame.frame for frame in result.frames],
            [frame["frame"] for frame in preview],
        )
        self.assertEqual(
            hind_legs["phases"],
            ["compression", "rear_support", "hind_drive", "suspension",
             "fore_contact", "fore_support", "recovery_tuck", "loop_transfer"],
        )

    def test_running_sheet_reproduces_registered_frames_with_clear_edges(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sheet = (root / "docs/artwork/running-gait-sheet.png").read_bytes()
        frames = split_sheet(sheet)

        self.assertEqual(len(frames), 8)
        for index, frame in enumerate(frames):
            path = root / f"codex_pet/assets/akita/frames/running/{index:02}.png"
            self.assertEqual(frame, path.read_bytes())
            pixels = rgba_icon("running", index)
            border_alpha = (
                [pixels[(x * 4) + 3] for x in range(256)]
                + [pixels[((255 * 256 + x) * 4) + 3] for x in range(256)]
                + [pixels[((y * 256) * 4) + 3] for y in range(256)]
                + [pixels[((y * 256 + 255) * 4) + 3] for y in range(256)]
            )
            self.assertLessEqual(max(border_alpha), 16, index)
        self.assertEqual(frames[0],
                         (root / "codex_pet/assets/akita/running.png").read_bytes())

    def test_running_head_has_no_jump_at_phase_or_cycle_boundary(self) -> None:
        head_tops = []
        for frame in range(8):
            pixels = rgba_icon("running", frame)
            head_tops.append(min(
                y for y in range(35, 110) for x in range(120, 230)
                if pixels[(y * 256 + x) * 4 + 3] > 128
            ))

        jumps = [abs(after - before) for before, after in zip(
            head_tops, head_tops[1:] + head_tops[:1]
        )]
        self.assertLessEqual(max(jumps), 8, head_tops)

    def test_audit_writes_a_contact_sheet_and_frame_manifest(self) -> None:
        result = render_audit("idle", cycles=1, density=3)
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = write_audit(result, Path(directory))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertTrue((Path(directory) / "contact-sheet.png").is_file())
            self.assertEqual(manifest["frames"][6]["file"],
                             "frames/step-06-frame-06.png")
            self.assertTrue((Path(directory) / manifest["frames"][6]["file"]).is_file())
            self.assertNotIn("file", result.report["frames"][6])


if __name__ == "__main__":
    unittest.main()
