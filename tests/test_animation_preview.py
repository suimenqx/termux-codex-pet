import unittest

from codex_pet.animation import (
    AKITA_FRAME_COUNTS,
    AKITA_READY_LOOP_START,
    animation_interval,
)
from tools.preview_animation import _timeline


class AnimationPreviewTests(unittest.TestCase):
    def test_running_preview_uses_the_eight_pose_gallop_schedule(self) -> None:
        frames = _timeline("running", cycles=2)

        self.assertEqual([frame["frame"] for frame in frames], list(range(8)) * 2)
        self.assertEqual([frame["seconds"] for frame in frames], [0.08] * 16)
        self.assertTrue(all(str(frame["src"]).startswith("data:image/png;base64,")
                            for frame in frames))

    def test_ready_preview_uses_the_production_loop_and_frame_delays(self) -> None:
        frames = _timeline("ready", cycles=2)
        expected_indices = list(range(AKITA_FRAME_COUNTS["ready"]))
        expected_indices.extend(range(AKITA_READY_LOOP_START, AKITA_FRAME_COUNTS["ready"]))

        self.assertEqual([frame["frame"] for frame in frames], expected_indices)
        self.assertEqual(
            [frame["seconds"] for frame in frames],
            [animation_interval("akita", "ready", index) for index in expected_indices],
        )
        self.assertTrue(all(str(frame["src"]).startswith("data:image/png;base64,")
                            for frame in frames))


if __name__ == "__main__":
    unittest.main()
