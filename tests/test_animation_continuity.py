"""Recorded breakdowns, fixed key times and interruptible turn completion."""

import json
from pathlib import Path
import tempfile
import unittest

from tools.historical_animation import AnimationTimeline, akita_artwork_frame, playback_frames
from tools.historical_art import _png
from tools.prepare_motion_repairs import export, replace_region


class AnimationContinuityTests(unittest.TestCase):
    def test_all_turn_poses_can_be_interrupted_and_never_replayed(self):
        for offset, physical in [(0, 5), (.120001, 6), (.240001, 7), (.360001, 4)]:
            for target in ['idle', 'running', 'needs_input', 'blocked']:
                timeline = AnimationTimeline('akita', 'running', now=0)
                timeline.sync('akita', 'ready', 0, now=1)
                timeline.advance(1 + offset)
                self.assertEqual(akita_artwork_frame('ready', timeline.frame), ('ready', physical))
                self.assertFalse(timeline.sync('akita', 'ready', 0, now=1 + offset))
                self.assertTrue(timeline.sync('akita', target, 1, now=1 + offset))
                self.assertEqual((timeline.state, timeline.frame), (target, 0))
        steps = playback_frames('akita', 'ready', cycles=2, from_state='running')
        poses = [akita_artwork_frame('ready', s.frame) for s in steps]
        for physical in [5, 6, 7]:
            self.assertEqual(poses.count(('ready', physical)), 1)
        rest = next(i for i, pose in enumerate(poses) if pose[0] == 'idle')
        self.assertAlmostEqual(sum(s.duration_seconds for s in steps[:rest]), 1.30)

    def test_ordered_regions_use_one_source_without_moving_pixels(self):
        original = _png(256, 256, bytearray([180, 30, 10, 255] * 256 * 256))
        patch = _png(256, 256, bytearray([20, 50, 80, 255] * 256 * 256))
        regions = [{'box': [4, 4, 20, 20], 'feather': 2},
                   {'box': [12, 12, 28, 28], 'feather': 3}]
        expected = original
        for region in regions:
            expected = replace_region(expected, patch, tuple(region['box']), region['feather'])
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            (p / 'original.png').write_bytes(original)
            (p / 'patch.png').write_bytes(patch)
            item = {'source': 'patch.png', 'original': 'original.png',
                    'regions': regions, 'output': 'result.png'}
            recipe = p / 'export.json'
            recipe.write_text(json.dumps({'exports': [item]}))
            export(recipe, p / 'export')
            self.assertEqual((p / 'export/result.png').read_bytes(), expected)
            for invalid in [[], regions]:
                item['regions'] = invalid
                if invalid:
                    item['box'] = [4, 4, 20, 20]
                recipe.write_text(json.dumps({'exports': [item]}))
                with self.assertRaisesRegex(ValueError, 'choose one box'):
                    export(recipe, p / 'invalid')


if __name__ == '__main__':
    unittest.main()
