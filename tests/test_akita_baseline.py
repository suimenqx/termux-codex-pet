"""Preserve unchanged states and identify the intentional running replacement."""

import hashlib
import json
from pathlib import Path
import unittest


class AkitaBaselineTests(unittest.TestCase):
    def test_non_running_pngs_preserve_the_accepted_visual_baseline(self) -> None:
        root = Path(__file__).resolve().parents[1]
        baseline = json.loads((root / 'docs/artwork/akita/accepted-baseline.json').read_text())
        assets = root / 'codex_pet/assets/akita'
        actual = {
            path.relative_to(assets).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in assets.rglob('*.png')
            if path.name != 'running.png' and path.parent.name != 'running'
        }
        self.assertEqual(actual, {name: digest for name, digest in baseline['sha256'].items()
                                  if name != 'running.png' and not name.startswith('frames/running/')})

    def test_running_pngs_match_the_versioned_generated_manifest(self) -> None:
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / 'docs/artwork/akita/2026-10-gallop/manifest.json').read_text())
        for item in manifest['frames']:
            path = root / 'codex_pet/assets/akita/frames/running' / item['file']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item['sha256'])
        self.assertAlmostEqual(sum(item['seconds'] for item in manifest['frames']), .64)


if __name__ == '__main__':
    unittest.main()
