"""Timing diagnostics must describe the actual playback, not certify gait."""

import unittest
import hashlib
from png_fingerprint import historical_png_sha256
import json
from pathlib import Path
import tempfile

from codex_pet.art import _decode_rgba_png
from tools.audit_animation import _track_transitions
from tools.prepare_motion_repairs import export

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'docs/artwork/akita/2026-10-rhythm'


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

    def test_rejected_candidate_is_reproducible_and_protects_original_face(self):
        manifest = json.loads((PACKAGE / 'candidate.json').read_text())
        recipe = json.loads((PACKAGE / 'export-draft.json').read_text())
        self.assertIn('rejected-for-production', manifest['status'])
        self.assertEqual(len(manifest['frames']), 8)
        self.assertAlmostEqual(sum(f['seconds'] for f in manifest['frames']), .64)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'export'
            export(PACKAGE / 'export-draft.json', target)
            for item, frame in zip(recipe['exports'], manifest['frames']):
                png = (target / item['output']).read_bytes()
                self.assertEqual(_decode_rgba_png(png), _decode_rgba_png((PACKAGE / frame['file']).read_bytes()))
                self.assertEqual(historical_png_sha256(png), frame['sha256'])
                w, h, actual = _decode_rgba_png(png)
                self.assertEqual((w, h), (256, 256))
                _, _, reference = _decode_rgba_png((PACKAGE / item['original']).read_bytes())
                boxes = [r['box'] for r in item['regions']]
                for y in range(h):
                    for x in range(w):
                        if not any(x0 <= x < x1 and y0 <= y < y1 for x0, y0, x1, y1 in boxes):
                            q = (y * w + x) * 4
                            self.assertEqual(actual[q:q+4], reference[q:q+4], (item['output'], x, y))

    def test_rejected_candidate_has_not_replaced_any_production_art(self):
        references = json.loads((PACKAGE / 'references.json').read_text())
        production = ROOT / 'codex_pet/assets/akita'
        paths = set()
        for item in references:
            file = Path(item['file']).relative_to('originals')
            paths.add(file.as_posix())
            for path in [PACKAGE / item['file'], production / file]:
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item['sha256'])
        derived = json.loads((ROOT / 'docs/artwork/akita/2026-10-pack/derived-blink.json').read_text())
        blink = production / 'derived/ready-blink.png'
        self.assertEqual(hashlib.sha256(blink.read_bytes()).hexdigest(), derived['png_sha256'])
        self.assertEqual(paths | {'derived/ready-blink.png'},
                         {p.relative_to(production).as_posix() for p in production.rglob('*.png')})

    def test_generation_inputs_and_prompts_remain_available(self):
        records = json.loads((PACKAGE / 'generation-inputs.json').read_text())
        self.assertEqual(len(records), 15)
        for item in records:
            self.assertFalse(item['accepted_for_production'])
            self.assertTrue((PACKAGE / item['prompt']).read_text().strip())
            for reference in item['inputs']:
                self.assertTrue((PACKAGE / reference).is_file(), reference)
            self.assertEqual(hashlib.sha256((PACKAGE / item['source']).read_bytes()).hexdigest(), item['sha256'])


if __name__ == '__main__':
    unittest.main()
