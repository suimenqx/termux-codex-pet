"""Verify restoration of the user's chosen artwork, not its aesthetic quality."""

import hashlib
import json
from pathlib import Path
import unittest


class AkitaBaselineTests(unittest.TestCase):
    def test_production_pngs_match_the_accepted_visual_baseline(self) -> None:
        root = Path(__file__).resolve().parents[1]
        baseline = json.loads((root / 'docs/artwork/akita/accepted-baseline.json').read_text())
        assets = root / 'codex_pet/assets/akita'
        actual = {
            path.relative_to(assets).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in assets.rglob('*.png')
        }
        self.assertEqual(actual, baseline['sha256'])


if __name__ == '__main__':
    unittest.main()
