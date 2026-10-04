"""Timing diagnostics must describe the actual playback, not certify gait."""

import unittest
from tools.audit_animation import _track_transitions


class AnimationRhythmTests(unittest.TestCase):
    def test_spacing_uses_each_exposure_and_includes_the_cycle_seam(self):
        rows = _track_transitions([(0, 0), (16, 0), (56, 0)],
                                  [.04, .04, .08], [4, 9, 5], 4)
        self.assertEqual([(r['from_physical'], r['to_physical']) for r in rows],
                         [(4, 9), (9, 5), (5, 4)])
        self.assertEqual([r['chord_speed_dp_s'] for r in rows], [100, 250, 175])
        self.assertEqual(rows[-1]['delta_dp'], [-14, 0])

    def test_hidden_paws_do_not_create_fictional_bridge_motion(self):
        rows = _track_transitions([(0, 0), None, (56, 0)], [.04, .04, .08], [0, 1, 2], 4)
        self.assertEqual([r['visible'] for r in rows], [False, False, True])
        for row in rows[:2]:
            self.assertNotIn('chord_speed_dp_s', row)

    def test_bad_samples_do_not_produce_plausible_motion_numbers(self):
        for points, seconds, physical, scale in [
            ([], [], [], 4), ([(0, 0)], [], [0], 4),
            ([(0, 0)], [.08], [], 4), ([(0, 0)], [0], [0], 4),
            ([(0, 0)], [float('nan')], [0], 4),
            ([(0, 0)], [.08], [0], 0),
            ([(0, 0)], [.08], [0], float('inf')),
            ([(float('nan'), 0)], [.08], [0], 4),
            ([(0,)], [.08], [0], 4),
        ]:
            with self.subTest(points=points, seconds=seconds, scale=scale):
                with self.assertRaises(ValueError):
                    _track_transitions(points, seconds, physical, scale)


if __name__ == '__main__':
    unittest.main()
