import json
from pathlib import Path
import tempfile
import unittest

from tools.historical_animation import (AKITA_FRAME_INTERVALS, AnimationTimeline,
                                 akita_artwork_frame, playback_frames)
from tools.historical_art import _decode_rgba_png, _png
from tools.prepare_motion_repairs import export, replace_region

ROOT = Path(__file__).resolve().parents[1]


class MotionRepairTests(unittest.TestCase):
    def test_run_to_ready_has_one_interruptible_settle_and_turn(self):
        for frame in range(10):
            with self.subTest(frame=frame):
                timeline = AnimationTimeline('akita', 'running', now=0)
                timeline.advance(sum(AKITA_FRAME_INTERVALS["running"][:frame]) + .001)
                self.assertEqual(timeline.frame, frame)
                timeline.sync('akita', 'ready', 0, now=1)
                self.assertEqual(timeline.state, 'ready')
                self.assertEqual(akita_artwork_frame('ready', timeline.frame), ('ready', 5))
                timeline.advance(1.120001)
                self.assertEqual(akita_artwork_frame('ready', timeline.frame), ('ready', 6))
                timeline.advance(1.240001)
                self.assertEqual(akita_artwork_frame('ready', timeline.frame), ('ready', 7))
                timeline.sync('akita', 'needs_input', 0, now=1.25)
                self.assertEqual(timeline.state, 'needs_input')
                self.assertEqual(timeline.frame, 0)

    def test_other_sources_and_appearance_switch_do_not_turn_back_to_side(self):
        for appearance, state in [('akita', 'idle'), ('akita', 'needs_input'),
                                  ('akita', 'blocked'), ('robot', 'running')]:
            timeline = AnimationTimeline(appearance, state, now=0)
            timeline.sync('akita', 'ready', 0, now=1)
            self.assertEqual(akita_artwork_frame('ready', timeline.frame), ('ready', 4))

    def test_same_ready_event_preserves_entry_and_badge_does_not_restart_it(self):
        timeline = AnimationTimeline('akita', 'running', now=0)
        timeline.sync('akita', 'ready', 0, now=1)
        timeline.advance(1.13)
        frame, deadline = timeline.frame, timeline.deadline
        self.assertFalse(timeline.sync('akita', 'ready', 9, now=1.14))
        self.assertEqual((timeline.frame, timeline.deadline), (frame, deadline))
        for target in ('running', 'idle', 'blocked'):
            timeline.sync('akita', target, 1, now=2)
            self.assertEqual(timeline.state, target)
            self.assertEqual(timeline.frame, 0)

    def test_offline_transition_uses_live_sequence_and_never_repeats_turn(self):
        steps = playback_frames('akita', 'ready', cycles=2, from_state='running')
        poses = [akita_artwork_frame('ready', step.frame) for step in steps]
        self.assertEqual(poses[:4], [('ready', 5), ('ready', 6), ('ready', 7), ('ready', 4)])
        self.assertEqual(poses.count(('ready', 5)), 1)
        self.assertEqual(poses.count(('ready', 6)), 1)
        self.assertAlmostEqual(sum(s.duration_seconds for s in steps), 10.06)
        self.assertEqual([s.duration_seconds for s in steps[:3]], [.12, .12, .12])

    def test_edit_boundary_locks_all_original_pixels_outside_the_patch(self):
        original = _png(16, 16, bytearray([180, 30, 10, 255] * 256))
        patch = _png(16, 16, bytearray([20, 50, 80, 255] * 256))
        _, _, result = _decode_rgba_png(replace_region(original, patch, (4, 4, 12, 12), 2))
        for y in range(16):
            for x in range(16):
                pixel = result[(y * 16 + x) * 4:(y * 16 + x + 1) * 4]
                if x < 4 or x >= 12 or y < 4 or y >= 12:
                    self.assertEqual(pixel, bytes([180, 30, 10, 255]))
        self.assertEqual(result[(8 * 16 + 8) * 4:(8 * 16 + 9) * 4], bytes([20, 50, 80, 255]))

    def test_transparent_replacement_erases_old_leg_without_dark_fringe(self):
        original = _png(16, 16, bytearray([180, 30, 10, 255] * 256))
        transparent = _png(16, 16, bytearray([0, 0, 0, 0] * 256))
        _, _, result = _decode_rgba_png(replace_region(original, transparent, (4, 4, 12, 12), 2))
        i = (4 * 16 + 8) * 4
        self.assertEqual(result[i:i+3], bytes([180, 30, 10]))
        self.assertGreater(result[i+3], 0)
        self.assertLess(result[i+3], 255)
        self.assertEqual(result[(8 * 16 + 8) * 4 + 3], 0)

    def test_production_patch_protects_head_torso_tail_and_hindlegs(self):
        folder = ROOT / 'docs/artwork/akita/2026-10-local-motion'
        original = _decode_rgba_png((folder / 'running-original.png').read_bytes())[2]
        repaired = _decode_rgba_png((ROOT / 'codex_pet/assets/akita/frames/running/02.png').read_bytes())[2]
        changes = 0
        for y in range(256):
            for x in range(256):
                i = (y * 256 + x) * 4
                if not (126 <= x < 256 and 174 <= y < 242):
                    self.assertEqual(original[i:i+4], repaired[i:i+4])
                elif original[i:i+4] != repaired[i:i+4]:
                    changes += 1
        self.assertGreater(changes, 0)

    def test_exports_reproduce_the_shipped_assets(self):
        folder = ROOT / 'docs/artwork/akita/2026-10-local-motion'
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'export'
            export(folder / 'export.json', output)
            for item in json.loads((folder / 'export.json').read_text())['exports']:
                target = ROOT / 'codex_pet/assets/akita/frames' / item['output']
                if item['output'] == 'ready/06.png':
                    target = ROOT / 'docs/artwork/akita/2026-10-continuity/originals/ready/06.png'
                self.assertEqual(_decode_rgba_png((output / item['output']).read_bytes()),
                                 _decode_rgba_png(target.read_bytes()))
            with self.assertRaises(ValueError):
                export(folder / 'export.json', output)

    def test_settle_preserves_the_running_face_and_original_scale(self):
        original = _decode_rgba_png((ROOT / 'codex_pet/assets/akita/frames/running/00.png').read_bytes())[2]
        settled = _decode_rgba_png((ROOT / 'codex_pet/assets/akita/frames/ready/05.png').read_bytes())[2]
        self.assertEqual(original[:174 * 256 * 4], settled[:174 * 256 * 4])

    def test_preview_and_audit_include_the_contextual_entry(self):
        from tools.preview_animation import _timeline
        from tools.audit_animation import render_audit
        expected = playback_frames('akita', 'ready', cycles=1, from_state='running')
        preview = _timeline('ready', 1, from_state='running')
        audit = render_audit('ready', 1, density=1, from_state='running')
        self.assertEqual([f['frame'] for f in preview], [s.frame for s in expected])
        self.assertEqual([f.frame for f in audit.frames], [s.frame for s in expected])
        self.assertEqual(audit.report['from_state'], 'running')
        self.assertTrue(audit.report['tail_motion']['passed'])
        self.assertEqual(audit.report['tail_motion']['chest_changed_pixels_at_display_size'], 0)
        self.assertEqual(audit.report['tail_motion']['high_step'], 12)
        self.assertEqual(audit.report['tail_motion']['low_step'], 13)

    def test_invalid_patch_bounds_and_canvas_mismatch_are_rejected(self):
        a = _png(16, 16, bytearray(16 * 16 * 4))
        b = _png(8, 8, bytearray(8 * 8 * 4))
        for box, feather in [((-1, 0, 10, 10), 2), ((0, 0, 17, 10), 2), ((0, 0, 8, 8), 4)]:
            with self.assertRaises(ValueError):
                replace_region(a, a, box, feather)
        with self.assertRaises(ValueError):
            replace_region(a, b, (0, 0, 8, 8), 2)


if __name__ == '__main__':
    unittest.main()
