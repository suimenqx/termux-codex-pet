import json
from pathlib import Path
import tempfile
import unittest

from codex_pet.animation import (
    AKITA_FRAME_COUNTS,
    AKITA_FRAME_INTERVALS,
    AKITA_READY_LOOP_START,
    AKITA_READY_LOOP_END,
    animation_interval,
)
from codex_pet.art import icon, _png
from tools.preview_animation import _candidate_timeline, _html, _timeline


class AnimationPreviewTests(unittest.TestCase):
    def test_candidate_uses_its_own_files_and_exact_exposures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pose.png").write_bytes(icon("idle", 0))
            manifest = root / "frames.json"
            manifest.write_text(json.dumps({"frames": [
                {"file": "pose.png", "seconds": 0.04},
                {"file": "pose.png", "seconds": 0.08},
            ]}), encoding="utf-8")
            frames = _candidate_timeline(manifest, cycles=2)

        self.assertEqual([frame["seconds"] for frame in frames], [.04, .08] * 2)
        self.assertEqual([frame["frame"] for frame in frames], [0, 1] * 2)
        self.assertEqual(frames[0]["src"], frames[1]["src"])
        html = _html("running", 2, frames)
        self.assertIn("未替换生产素材", html)
        self.assertIn('max="3"', html)

    def test_candidate_rejects_invalid_exposures_and_raster_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "frames.json"
            for seconds in (0, -1, float("inf"), float("nan"), True, "0.04"):
                with self.subTest(seconds=seconds):
                    manifest.write_text(json.dumps({"frames": [
                        {"file": "pose.png", "seconds": seconds},
                    ]}), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "finite and positive"):
                        _candidate_timeline(manifest)
            (root / "pose.png").write_bytes(_png(1, 1, bytearray(4)))
            manifest.write_text(json.dumps({"frames": [
                {"file": "pose.png", "seconds": .04},
            ]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "256 x 256"):
                _candidate_timeline(manifest)
            manifest.write_text('{"frames": []}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "nonempty"):
                _candidate_timeline(manifest)

    def test_running_preview_uses_the_ten_pose_schedule(self) -> None:
        frames = _timeline("running", cycles=2)

        self.assertEqual([frame["frame"] for frame in frames], list(range(10)) * 2)
        self.assertEqual([frame["seconds"] for frame in frames], list(AKITA_FRAME_INTERVALS["running"]) * 2)
        self.assertTrue(all(str(frame["src"]).startswith("data:image/png;base64,")
                            for frame in frames))

    def test_ready_preview_uses_the_production_loop_and_frame_delays(self) -> None:
        frames = _timeline("ready", cycles=2)
        expected_indices = list(range(AKITA_READY_LOOP_END + 1))
        expected_indices.extend(range(AKITA_READY_LOOP_START, AKITA_READY_LOOP_END + 1))

        self.assertEqual([frame["frame"] for frame in frames], expected_indices)
        self.assertEqual(
            [frame["seconds"] for frame in frames],
            [animation_interval("akita", "ready", index) for index in expected_indices],
        )
        self.assertTrue(all(str(frame["src"]).startswith("data:image/png;base64,")
                            for frame in frames))


if __name__ == "__main__":
    unittest.main()
