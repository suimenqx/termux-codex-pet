import json
from pathlib import Path
import struct
import tempfile
import unittest

from tools.audit_animation import render_audit, write_audit
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

    def test_running_tracks_both_hind_paws_relative_to_the_hip(self) -> None:
        result = render_audit("running", cycles=2, density=3)
        hind_legs = result.report["hind_leg_motion"]
        preview = _timeline("running", cycles=2)

        self.assertIsInstance(hind_legs, dict)
        self.assertTrue(hind_legs["passed"], hind_legs)
        self.assertTrue(hind_legs["all_paw_markers_on_opaque_cream_art"])
        self.assertTrue(hind_legs["pair_coordination_passed"])
        self.assertGreaterEqual(hind_legs["opposed_transitions"], 2)
        self.assertGreaterEqual(hind_legs["mean_pair_separation_dp"], 6.0)
        for leg in hind_legs["legs"].values():
            self.assertGreaterEqual(leg["horizontal_range_dp"], 8.0)
            self.assertGreaterEqual(leg["vertical_range_dp"], 4.0)
            self.assertGreaterEqual(leg["cycle_path_length_dp"], 24.0)
            self.assertTrue(all(point["opaque_coverage"] >= 0.8
                                and point["mean_blue_channel"] >= 120.0
                                for point in leg["positions"]))
        self.assertEqual(result.report["frame_count"], 16)
        self.assertEqual(result.report["duration_seconds"], 0.96)
        self.assertEqual(
            [frame.frame for frame in result.frames],
            [frame["frame"] for frame in preview],
        )
        self.assertEqual(
            hind_legs["phases"],
            ["compression", "rear_support", "hind_drive", "suspension",
             "fore_contact", "fore_support", "recovery_tuck", "loop_transfer"],
        )

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
