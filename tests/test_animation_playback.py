import unittest

from codex_pet.animation import (
    AKITA_FRAME_COUNTS,
    AKITA_FRAME_INTERVALS,
    AKITA_READY_LOOP_START,
    AnimationTimeline,
    akita_artwork_frame,
    animation_interval,
    advance_animation,
    playback_frames,
)


class AnimationTimelineTests(unittest.TestCase):
    def test_frame_deadlines_stay_anchored_to_the_original_schedule(self) -> None:
        timeline = AnimationTimeline("akita", "running", now=10.0)

        self.assertEqual(timeline.advance(now=10.015), 0)
        self.assertEqual(timeline.advance(now=10.021), 1)
        self.assertAlmostEqual(timeline.deadline or 0, 10.04)
        self.assertAlmostEqual(timeline.timeout(now=10.035) or 0, 0.005)
        self.assertEqual(timeline.advance(now=10.041), 2)
        self.assertAlmostEqual(timeline.deadline or 0, 10.06)

    def test_late_wakeup_skips_stale_frames_instead_of_catching_up_in_a_burst(self) -> None:
        timeline = AnimationTimeline("akita", "running", now=20.0)

        frame = timeline.advance(now=20.35)

        self.assertEqual(frame, 17)
        self.assertAlmostEqual(timeline.deadline or 0, 20.36)

    def test_state_reset_starts_a_new_visual_at_frame_zero(self) -> None:
        timeline = AnimationTimeline("akita", "running", now=10.0)
        timeline.advance(now=10.081)

        timeline.reset("akita", "ready", now=12.0)

        self.assertEqual(timeline.frame, 0)
        self.assertAlmostEqual(timeline.deadline or 0, 12.04)

    def test_sync_resets_for_visible_changes_only(self) -> None:
        timeline = AnimationTimeline("akita", "idle", now=1.0, running_count=1)
        timeline.advance(now=1.121)
        self.assertFalse(timeline.sync("akita", "idle", 4, now=2.0))
        self.assertEqual(timeline.frame, 1)

        self.assertTrue(timeline.sync("akita", "running", 1, now=2.0))
        self.assertEqual(timeline.frame, 0)
        self.assertAlmostEqual(timeline.deadline or 0, 2.02)
        timeline.advance(now=2.09)
        self.assertTrue(timeline.sync("akita", "running", 2, now=3.0))
        self.assertEqual(timeline.frame, 0)
        self.assertAlmostEqual(timeline.deadline or 0, 3.02)

        self.assertTrue(timeline.sync("robot", "running", 2, now=4.0))
        self.assertAlmostEqual(timeline.deadline or 0, 6.0)

    def test_ready_artwork_mapping_clamps_and_preserves_entry_then_loop(self) -> None:
        frames = playback_frames("akita", "ready", cycles=2)
        artwork = [akita_artwork_frame("ready", step.frame) for step in frames]

        self.assertEqual(artwork[:32], [("ready", i) for i in range(32)])
        self.assertEqual(artwork[32:], [("ready", i) for i in range(32, 64)] * 2)
        self.assertEqual(akita_artwork_frame("ready", -1), artwork[0])
        self.assertEqual(akita_artwork_frame("blocked", 99), ("blocked", 15))

    def test_one_shot_animation_holds_its_final_frame_indefinitely(self) -> None:
        timeline = AnimationTimeline("akita", "blocked", now=30.0)
        for now in (30.12, 30.30, 30.48):
            timeline.advance(now=now)
        frame = timeline.advance(now=30.801)

        self.assertEqual(frame, 16)
        self.assertIsNone(timeline.deadline)
        self.assertIsNone(timeline.timeout(now=31.0))


class PlaybackScheduleTests(unittest.TestCase):
    def test_akita_looping_states_keep_their_frame_order_and_cadence(self) -> None:
        self.assertEqual(animation_interval("akita", "idle", 0), 0.12)
        self.assertEqual(animation_interval("akita", "idle", 21), 0.04)
        self.assertEqual(animation_interval("akita", "running", 0), 0.02)
        self.assertEqual(animation_interval("akita", "needs_input", 13), 0.65)
        for state in ("idle", "running", "needs_input"):
            self.assertEqual(advance_animation("akita", state, AKITA_FRAME_COUNTS[state] - 1), 0)
        self.assertEqual(AKITA_FRAME_COUNTS["running"], 32)

    def test_running_schedule_uses_two_complete_rig_cycles(self) -> None:
        frames = playback_frames("akita", "running", cycles=2)
        self.assertEqual([item.frame for item in frames], list(range(32)) * 2)
        self.assertEqual([item.duration_seconds for item in frames], [0.02] * 64)
        self.assertAlmostEqual(sum(item.duration_seconds for item in frames), 1.28)

    def test_ready_schedule_hops_once_then_repeats_only_the_rest_loop(self) -> None:
        frames = playback_frames("akita", "ready", cycles=2)
        expected = list(range(AKITA_FRAME_COUNTS["ready"]))
        expected.extend(range(AKITA_READY_LOOP_START, AKITA_FRAME_COUNTS["ready"]))

        self.assertEqual([item.frame for item in frames], expected)
        self.assertEqual(
            [item.duration_seconds for item in frames],
            [AKITA_FRAME_INTERVALS["ready"][frame] for frame in expected],
        )
        self.assertEqual(AKITA_READY_LOOP_START, 32)

    def test_ready_entry_and_loop_have_explicit_durations(self) -> None:
        intervals = AKITA_FRAME_INTERVALS["ready"]
        self.assertAlmostEqual(sum(intervals[:AKITA_READY_LOOP_START]), 1.28)
        self.assertEqual(intervals[AKITA_READY_LOOP_START:], AKITA_FRAME_INTERVALS["idle"])
        self.assertAlmostEqual(sum(intervals[AKITA_READY_LOOP_START:]), 3.52)

    def test_akita_blocked_reaction_plays_once_then_holds(self) -> None:
        frame_count = AKITA_FRAME_COUNTS["blocked"]
        frame = 0
        for _ in range(frame_count):
            self.assertIsNotNone(animation_interval("akita", "blocked", frame))
            frame = advance_animation("akita", "blocked", frame)
        self.assertEqual(frame, frame_count)
        self.assertIsNone(animation_interval("akita", "blocked", frame))
        self.assertEqual(advance_animation("akita", "blocked", frame), frame)


    def test_one_shot_schedule_includes_a_finite_offline_final_hold(self) -> None:
        frames = playback_frames("akita", "blocked", cycles=3)

        self.assertEqual([item.frame for item in frames], list(range(17)))
        self.assertEqual([item.duration_seconds for item in frames],
                         [0.05] * 16 + [0.8])

    def test_robot_loops_keep_their_existing_two_frame_cadence(self) -> None:
        frames = playback_frames("robot", "running", cycles=2)

        self.assertEqual([item.frame for item in frames], [0, 1, 0, 1])
        self.assertEqual([item.duration_seconds for item in frames], [2.0] * 4)
        self.assertEqual(animation_interval("robot", "needs_input", 0), 1.4)
        self.assertEqual(advance_animation("robot", "needs_input", 0), 1)

    def test_cycle_count_must_be_positive(self) -> None:
        with self.assertRaisesRegex(ValueError, "cycles must be at least 1"):
            playback_frames("akita", "running", cycles=0)


if __name__ == "__main__":
    unittest.main()
