import unittest

from codex_pet.gui import AnimationClock


class AnimationClockTests(unittest.TestCase):
    def test_frame_deadlines_stay_anchored_to_the_original_schedule(self) -> None:
        clock = AnimationClock("akita", "running", 0, now=10.0)

        self.assertEqual(clock.advance("akita", "running", 0, now=10.05), 0)
        self.assertEqual(clock.advance("akita", "running", 0, now=10.061), 1)
        self.assertAlmostEqual(clock.deadline or 0, 10.12)
        self.assertAlmostEqual(clock.timeout(now=10.11) or 0, 0.01)
        self.assertEqual(clock.advance("akita", "running", 1, now=10.121), 2)
        self.assertAlmostEqual(clock.deadline or 0, 10.18)

    def test_late_wakeup_skips_stale_frames_instead_of_catching_up_in_a_burst(self) -> None:
        clock = AnimationClock("akita", "running", 0, now=20.0)

        frame = clock.advance("akita", "running", 0, now=20.35)

        self.assertEqual(frame, 5)
        self.assertAlmostEqual(clock.deadline or 0, 20.36)

    def test_one_shot_animation_stops_its_clock_after_the_last_frame(self) -> None:
        clock = AnimationClock("akita", "blocked", 3, now=30.0)

        frame = clock.advance("akita", "blocked", 3, now=30.12)

        self.assertEqual(frame, 4)
        self.assertIsNone(clock.deadline)
        self.assertIsNone(clock.timeout(now=30.5))


if __name__ == "__main__":
    unittest.main()
