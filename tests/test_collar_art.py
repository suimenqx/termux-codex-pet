"""Fixed accessory coverage, deterministic export and original pixel protection."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from codex_pet.animation import AKITA_FRAME_COUNTS, akita_artwork_frame
from codex_pet.art import _decode_rgba_png, _png, rgba_icon
from tools.prepare_motion_repairs import export

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'docs/artwork/akita/2026-10-collar'
ASSETS = ROOT / 'codex_pet/assets/akita/frames'


class CollarArtTests(unittest.TestCase):
    def test_every_physical_and_logical_pose_has_a_blue_collar(self):
        model = json.loads((PACKAGE / 'model.json').read_text())
        model['frames'].update(json.loads((ROOT / 'docs/artwork/akita/2026-10-continuity/model.json').read_text())['frames'])
        actual = {p.relative_to(ASSETS).as_posix() for p in ASSETS.glob('*/*.png')}
        self.assertEqual(set(model['frames']), actual)
        self.assertEqual(len(actual), 34)
        for state, count in AKITA_FRAME_COUNTS.items():
            for index in range(count):
                physical, number = akita_artwork_frame(state, index)
                if physical == 'blink':
                    physical = 'idle'
                key = f'{physical}/{number:02}.png'
                x, y = model['frames'][key]['sample_xy']
                pixels = rgba_icon(state, index)
                r, g, b, a = pixels[(y * 256 + x) * 4:(y * 256 + x + 1) * 4]
                with self.subTest(state=state, frame=index):
                    self.assertEqual(a, model['frames'][key]['sample_rgba'][3])
                    self.assertGreater(a, 0)
                    self.assertLess(r, g)
                    self.assertLess(g, b)
        for key, record in model['frames'].items():
            pixels = _decode_rgba_png((ASSETS / key).read_bytes())[2]
            x, y = record['sample_xy']
            self.assertEqual(list(pixels[(y * 256 + x) * 4:(y * 256 + x + 1) * 4]), record['sample_rgba'])

    def test_neck_edits_preserve_every_pixel_outside_recorded_regions(self):
        recipe = json.loads((PACKAGE / 'export.json').read_text())
        edited = {item['output']: item for item in recipe['exports']}
        for path in (PACKAGE / 'originals').glob('*/*.png'):
            key = path.relative_to(PACKAGE / 'originals').as_posix()
            before = _decode_rgba_png(path.read_bytes())[2]
            target = ASSETS / key
            if key == 'ready/06.png':
                target = ROOT / 'docs/artwork/akita/2026-10-continuity/originals' / key
            after = _decode_rgba_png(target.read_bytes())[2]
            self.assertEqual(before[3::4], after[3::4], key)
            if key not in edited:
                self.assertEqual(before, after, key)
                continue
            x0, y0, x1, y1 = edited[key]['box']
            changed = 0
            for y in range(256):
                for x in range(256):
                    i = (y * 256 + x) * 4
                    if not (x0 <= x < x1 and y0 <= y < y1):
                        self.assertEqual(before[i:i+4], after[i:i+4], (key, x, y))
                    else:
                        changed += before[i:i+4] != after[i:i+4]
            self.assertGreater(changed, 0, key)

    def test_preserved_originals_match_the_prior_reviewed_version(self):
        baseline = json.loads((ROOT / 'docs/artwork/akita/accepted-baseline.json').read_text())['sha256']
        motion = json.loads((ROOT / 'docs/artwork/akita/2026-10-local-motion/delivery.json').read_text())['sha256']
        prior = {**baseline, **motion}
        for path in (PACKAGE / 'originals').glob('*/*.png'):
            key = 'frames/' + path.relative_to(PACKAGE / 'originals').as_posix()
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), prior[key])

    def test_export_reproduces_every_shipped_collar_edit(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'export'
            export(PACKAGE / 'export.json', output)
            for item in json.loads((PACKAGE / 'export.json').read_text())['exports']:
                self.assertEqual(_decode_rgba_png((output / item['output']).read_bytes()),
                                 _decode_rgba_png((ASSETS / item['output']).read_bytes()))

    def test_sheet_cell_selection_and_invalid_indices(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            # Two full production-size cells, no resize or interpolation.
            pixels = bytearray()
            for _ in range(256):
                pixels.extend(bytes([10, 20, 30, 255]) * 256)
                pixels.extend(bytes([40, 50, 60, 255]) * 256)
            (folder / 'source.png').write_bytes(_png(512, 256, pixels))
            item = {'source': 'source.png', 'grid': [2, 1, 2], 'cell': 1, 'output': 'frame.png'}
            manifest = folder / 'export.json'
            manifest.write_text(json.dumps({'exports': [item]}))
            export(manifest, folder / 'ok')
            self.assertEqual(_decode_rgba_png((folder / 'ok/frame.png').read_bytes())[2], bytes([40, 50, 60, 255]) * 256 * 256)
            for cell in (-1, 2, '0'):
                item['cell'] = cell
                manifest.write_text(json.dumps({'exports': [item]}))
                with self.assertRaises(ValueError):
                    export(manifest, folder / 'invalid')


if __name__ == '__main__':
    unittest.main()
