import unittest

from codex_pet.animation import (
    AKITA_FRAME_COUNTS,
    AKITA_FRAME_INTERVALS,
    AKITA_READY_SEQUENCE,
    AKITA_READY_LOOP_START,
    AnimationTimeline,
    animation_interval,
    advance_animation,
    playback_frames,
)


class AnimationTimelineTests(unittest.TestCase):
    def test_frame_deadlines_stay_anchored_to_the_original_schedule(self) -> None:
        timeline = AnimationTimeline("akita", "running", now=10.0)

        self.assertEqual(timeline.advance(now=10.05), 0)
        self.assertEqual(timeline.advance(now=10.081), 1)
        self.assertAlmostEqual(timeline.deadline or 0, 10.16)
        self.assertAlmostEqual(timeline.timeout(now=10.15) or 0, 0.01)
        self.assertEqual(timeline.advance(now=10.161), 2)
        self.assertAlmostEqual(timeline.deadline or 0, 10.24)

    def test_late_wakeup_skips_stale_frames_instead_of_catching_up_in_a_burst(self) -> None:
        timeline = AnimationTimeline("akita", "running", now=20.0)

        frame = timeline.advance(now=20.35)

        self.assertEqual(frame, 4)
        self.assertAlmostEqual(timeline.deadline or 0, 20.4)

    def test_state_reset_starts_a_new_visual_at_frame_zero(self) -> None:
        timeline = AnimationTimeline("akita", "running", now=10.0)
        timeline.advance(now=10.081)

        timeline.reset("akita", "ready", now=12.0)

        self.assertEqual(timeline.frame, 0)
        self.assertAlmostEqual(timeline.deadline or 0, 12.32)

    def test_one_shot_animation_holds_its_final_frame_indefinitely(self) -> None:
        timeline = AnimationTimeline("akita", "blocked", now=30.0)
        for now in (30.12, 30.30, 30.48):
            timeline.advance(now=now)
        frame = timeline.advance(now=30.60)

        self.assertEqual(frame, 4)
        self.assertIsNone(timeline.deadline)
        self.assertIsNone(timeline.timeout(now=31.0))


class PlaybackScheduleTests(unittest.TestCase):
    def test_akita_looping_states_keep_their_frame_order_and_cadence(self) -> None:
        self.assertEqual(animation_interval("akita", "idle", 0), 0.6)
        self.assertEqual(animation_interval("akita", "idle", 6), 0.6)
        self.assertEqual(animation_interval("akita", "running", 0), 0.08)
        self.assertEqual(animation_interval("akita", "needs_input", 3), 0.85)
        self.assertEqual(advance_animation("akita", "idle", 5), 6)
        self.assertEqual(advance_animation("akita", "idle", 7), 0)
        self.assertEqual(AKITA_FRAME_COUNTS["running"], 8)
        self.assertEqual(advance_animation("akita", "running", 7), 0)
        self.assertEqual(advance_animation("akita", "needs_input", 3), 0)

    def test_running_schedule_uses_two_complete_eight_pose_cycles(self) -> None:
        frames = playback_frames("akita", "running", cycles=2)

        self.assertEqual([item.frame for item in frames], list(range(8)) * 2)
        self.assertEqual([item.duration_seconds for item in frames], [0.08] * 16)

    def test_ready_schedule_hops_once_then_repeats_only_the_rest_loop(self) -> None:
        frames = playback_frames("akita", "ready", cycles=2)
        expected = list(range(AKITA_FRAME_COUNTS["ready"]))
        expected.extend(range(AKITA_READY_LOOP_START, AKITA_FRAME_COUNTS["ready"]))

        self.assertEqual([item.frame for item in frames], expected)
        self.assertEqual(
            [item.duration_seconds for item in frames],
            [AKITA_FRAME_INTERVALS["ready"][frame] for frame in expected],
        )
        self.assertEqual(AKITA_READY_SEQUENCE[10:12], (("idle", 6), ("idle", 7)))
        self.assertTrue(all(
            asset_state in ("idle", "blink")
            for asset_state, _ in AKITA_READY_SEQUENCE[AKITA_READY_LOOP_START:]
        ))
        self.assertEqual(
            AKITA_READY_SEQUENCE[:5],
            (("ready", 0), ("ready", 4), ("ready", 1), ("ready", 2), ("ready", 3)),
        )
        self.assertEqual(AKITA_READY_LOOP_START, 5)

    def test_ready_entry_and_loop_keep_their_established_durations(self) -> None:
        self.assertEqual(animation_interval("akita", "ready", 7), 0.20)
        cycle = sum(AKITA_FRAME_INTERVALS["ready"][frame]
                    for frame in range(AKITA_READY_LOOP_START, AKITA_FRAME_COUNTS["ready"]))
        self.assertGreaterEqual(cycle, 3.5)
        hop = [AKITA_FRAME_INTERVALS["ready"][frame]
               for frame in range(AKITA_READY_LOOP_START)]
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


    def test_one_shot_schedule_includes_a_finite_offline_final_hold(self) -> None:
        frames = playback_frames("akita", "blocked", cycles=3)

        self.assertEqual([item.frame for item in frames], [0, 1, 2, 3, 4])
        self.assertEqual([item.duration_seconds for item in frames],
                         [0.12, 0.18, 0.18, 0.12, 0.8])

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
