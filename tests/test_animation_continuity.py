"""Recorded breakdowns, fixed key times and interruptible turn completion."""

import hashlib
from png_fingerprint import historical_png_sha256
import json
from pathlib import Path
import tempfile
import unittest

from tools.historical_animation import AnimationTimeline, akita_artwork_frame, playback_frames
from tools.historical_art import _decode_rgba_png, _png
from tools.prepare_motion_repairs import export, replace_region

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'docs/artwork/akita/2026-10-continuity'
ASSETS = ROOT / 'codex_pet/assets/akita/frames'


class AnimationContinuityTests(unittest.TestCase):
    def test_breakdowns_preserve_all_eight_key_times_and_drawings(self):
        at = 0
        times = {}
        for step in playback_frames('akita', 'running'):
            physical = akita_artwork_frame('running', step.frame)[1]
            times[physical] = at
            at += step.duration_seconds
        self.assertEqual(len(times), 10)
        self.assertAlmostEqual(at, .64)
        for frame in range(8):
            self.assertAlmostEqual(times[frame], frame * .08)
            name = f'running/{frame:02}.png'
            self.assertEqual((ASSETS / name).read_bytes(),
                             (PACKAGE / 'originals' / name).read_bytes())
        self.assertAlmostEqual(times[8], .04)
        self.assertAlmostEqual(times[9], .36)

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

    def test_exports_and_recorded_hashes_reproduce_the_four_deliveries(self):
        delivery = json.loads((PACKAGE / 'delivery.json').read_text())
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'export'
            export(PACKAGE / 'export.json', output)
            for key, expected in delivery['sha256'].items():
                relative = Path(key).relative_to('frames')
                data = (output / relative).read_bytes()
                self.assertEqual(historical_png_sha256(data), expected)
                self.assertEqual(_decode_rgba_png(data), _decode_rgba_png((ASSETS / relative).read_bytes()))

    def test_breakdowns_preserve_pixels_outside_the_declared_limb_regions(self):
        for item in json.loads((PACKAGE / 'export.json').read_text())['exports']:
            if 'original' not in item:
                continue
            before = _decode_rgba_png((PACKAGE / item['original']).read_bytes())[2]
            after = _decode_rgba_png((ASSETS / item['output']).read_bytes())[2]
            regions = item.get('regions', [item])
            boxes = [r['box'] for r in regions]
            changed = 0
            for y in range(256):
                for x in range(256):
                    i = (y * 256 + x) * 4
                    if not any(x0 <= x < x1 and y0 <= y < y1 for x0, y0, x1, y1 in boxes):
                        self.assertEqual(before[i:i+4], after[i:i+4], (item['output'], x, y))
                    else:
                        changed += before[i:i+4] != after[i:i+4]
            self.assertGreater(changed, 0)

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
