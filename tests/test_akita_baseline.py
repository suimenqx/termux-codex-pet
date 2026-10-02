"""Preserve unchanged states and identify the intentional running replacement."""

import hashlib
import json
from pathlib import Path
import unittest


class AkitaBaselineTests(unittest.TestCase):
    def test_only_reviewed_local_repair_and_transition_extend_the_baseline(self) -> None:
        root = Path(__file__).resolve().parents[1]
        baseline = json.loads((root / 'docs/artwork/akita/accepted-baseline.json').read_text())
        assets = root / 'codex_pet/assets/akita'
        actual = {
            path.relative_to(assets).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in assets.rglob('*.png')
        }
        delivery = json.loads((root / 'docs/artwork/akita/2026-10-local-motion/delivery.json').read_text())
        changes = delivery['sha256']
        self.assertEqual(set(changes), {'frames/running/02.png', 'frames/ready/05.png', 'frames/ready/06.png'})
        self.assertEqual(actual, {**baseline['sha256'], **changes})
        original = root / 'docs/artwork/akita/2026-10-local-motion/running-original.png'
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), baseline['sha256']['frames/running/02.png'])


if __name__ == '__main__':
    unittest.main()
