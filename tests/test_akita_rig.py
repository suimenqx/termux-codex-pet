import hashlib
import math
from pathlib import Path
import unittest

from codex_pet.animation import AKITA_FRAME_INTERVALS, AKITA_READY_LOOP_START
from tools.akita_rig import (
    MODEL_PATH, bone_point, clip_poses, gait_foot, load_model, pose_at, rigid,
    skin_point, solve_ik,
)


class AkitaRigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = load_model()

    def test_shared_layers_and_sources_match_the_recorded_hashes(self) -> None:
        root = Path(__file__).resolve().parents[1]
        model = self.model
        self.assertEqual(set(model['layers']), {'head', 'body', 'tail', 'collar', 'fore', 'hind'})
        for layer in model['layers'].values():
            self.assertEqual(hashlib.sha256((MODEL_PATH.parent / layer['file']).read_bytes()).hexdigest(),
                             layer['sha256'])
        for path, digest in [(root / model['source']['neutral'], model['source']['neutral_sha256']),
                             (MODEL_PATH.parent / model['source']['parts'], model['source']['parts_sha256'])]:
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_all_states_preserve_head_body_and_fixed_bone_lengths(self) -> None:
        # Sample between exported poses too: adding a frame may not expose an
        # unreachable IK target or secretly stretch a bone.
        for state, intervals in AKITA_FRAME_INTERVALS.items():
            for i in range(401):
                pose = pose_at(self.model, state, sum(intervals) * i / 400)
                for part in ('head', 'body', 'tail'):
                    transform = pose[part]
                    self.assertEqual(transform['scale'], 1)
                    pivot = self.model[f'{part}_pivot']
                    a = rigid((100, 70), pivot, transform['offset'], transform['angle'])
                    b = rigid((200, 100), pivot, transform['offset'], transform['angle'])
                    self.assertAlmostEqual(math.dist(a, b), math.hypot(100, 30))
                for name, leg in pose['legs'].items():
                    bind = self.model['limb_bind'][self.model['legs'][name]['kind']]
                    for a, b, length in zip(('root', 'knee'), ('knee', 'ankle'), leg['bone_lengths']):
                        self.assertAlmostEqual(math.dist(leg[a], leg[b]), length)
                    # Rigid skin patches cannot flip or collapse at a bend.
                    for bone in range(3):
                        a, b, c = [bone_point(p, bind, leg, bone) for p in ((0, 0), (1, 0), (0, 1))]
                        determinant = (b[0]-a[0])*(c[1]-a[1]) - (c[0]-a[0])*(b[1]-a[1])
                        self.assertAlmostEqual(determinant, leg['projection']**2)
                    self.assertLess(math.dist(skin_point(bind['paw'], bind, leg), leg['paw']), 1e-10)
                    if leg['contact']:
                        sole = skin_point((bind['paw'][0], bind['sole']), bind, leg)
                        self.assertAlmostEqual(sole[1], leg['ground_y'])

    def test_support_velocity_uses_one_projected_ground_speed(self) -> None:
        period = sum(AKITA_FRAME_INTERVALS['running'])
        self.assertAlmostEqual(period, self.model['running_period'])
        epsilon = 1e-6
        for leg in self.model['legs'].values():
            phase = leg['contact_phase'] + leg['stance'] / 2
            before, _, _ = gait_foot(leg, phase - epsilon)
            after, contact, angle = gait_foot(leg, phase + epsilon)
            speed = (after[0] - before[0]) / (2 * epsilon * period * leg['projection'])
            self.assertAlmostEqual(speed, -self.model['ground_speed'], places=5)
            self.assertEqual(after[1], leg['paw'][1])
            self.assertTrue(contact)
            self.assertEqual(angle, 0)

    def test_paw_position_and_velocity_are_continuous_at_contact_and_wrap(self) -> None:
        epsilon = 1e-6
        for leg in self.model['legs'].values():
            for phase in (leg['contact_phase'], leg['contact_phase'] + leg['stance']):
                p0, _, a0 = gait_foot(leg, phase - epsilon)
                p1, _, a1 = gait_foot(leg, phase)
                p2, _, a2 = gait_foot(leg, phase + epsilon)
                self.assertLess(math.dist(p0, p2), .001)
                for axis in (0, 1):
                    self.assertAlmostEqual((p1[axis]-p0[axis])/epsilon,
                                           (p2[axis]-p1[axis])/epsilon, delta=.005)
                self.assertAlmostEqual((a1-a0)/epsilon, (a2-a1)/epsilon, delta=.001)

    def test_four_contacts_are_staggered_with_suspension_between_pairs(self) -> None:
        contacts = [self.model['legs'][name]['contact_phase'] for name in
                    ('hind_far', 'hind_near', 'fore_far', 'fore_near')]
        self.assertEqual(contacts, [0, .10, .44, .56])
        poses = clip_poses(self.model, 'running')
        self.assertTrue(any(not any(leg['contact'] for leg in pose['legs'].values()) for pose in poses))
        for pair in (('fore_near', 'fore_far'), ('hind_near', 'hind_far')):
            self.assertTrue(any(pose['legs'][pair[0]]['contact'] != pose['legs'][pair[1]]['contact']
                                for pose in poses))

    def test_loop_endpoints_preserve_pose_and_velocity(self) -> None:
        epsilon = 1e-5
        for state in ('idle', 'running', 'needs_input'):
            period = sum(AKITA_FRAME_INTERVALS[state])
            start = pose_at(self.model, state, 0)
            end = pose_at(self.model, state, period)
            for key in ('head', 'body', 'tail', 'legs'):
                self.assertEqual(start[key], end[key], state)
            before = pose_at(self.model, state, period - epsilon)
            after = pose_at(self.model, state, epsilon)
            for part in ('head', 'body', 'tail'):
                self.assertAlmostEqual((start[part]['angle'] - before[part]['angle'])/epsilon,
                                       (after[part]['angle'] - start[part]['angle'])/epsilon, places=3)
            for name in self.model['legs']:
                for axis in (0, 1):
                    self.assertAlmostEqual((start['legs'][name]['paw'][axis] - before['legs'][name]['paw'][axis])/epsilon,
                                           (after['legs'][name]['paw'][axis] - start['legs'][name]['paw'][axis])/epsilon,
                                           delta=.06)

    def test_ready_rest_reuses_idle_motion_and_hop_has_grounded_anticipation(self) -> None:
        entry = sum(AKITA_FRAME_INTERVALS['ready'][:AKITA_READY_LOOP_START])
        idle_samples = clip_poses(self.model, 'idle')
        ready_samples = clip_poses(self.model, 'ready')[AKITA_READY_LOOP_START:]
        for idle, ready in zip(idle_samples, ready_samples):
            for key in ('head', 'body', 'tail', 'blink', 'legs'):
                self.assertEqual(idle[key], ready[key])
        for i in range(32):
            idle = idle_samples[i]
            ready = pose_at(self.model, 'ready', entry + idle['time_seconds'])
            for key in ('head', 'body', 'tail'):
                self.assertAlmostEqual(idle[key]['angle'], ready[key]['angle'])
                self.assertAlmostEqual(idle[key]['offset'][1], ready[key]['offset'][1])
            self.assertAlmostEqual(idle['blink'], ready['blink'])
        crouch = pose_at(self.model, 'ready', .34)
        flight = pose_at(self.model, 'ready', .65)
        self.assertGreater(crouch['body']['offset'][1], 0)
        self.assertTrue(all(leg['contact'] for leg in crouch['legs'].values()))
        self.assertLess(flight['body']['offset'][1], 0)
        self.assertTrue(all(not leg['contact'] for leg in flight['legs'].values()))

    def test_invalid_authoring_target_fails_instead_of_stretching(self) -> None:
        with self.assertRaisesRegex(ValueError, 'unreachable'):
            solve_ik((0, 0), (0, 100), 20, 20, 1)
        with self.assertRaisesRegex(ValueError, 'unknown clip'):
            pose_at(self.model, 'unknown', 0)


if __name__ == '__main__':
    unittest.main()
