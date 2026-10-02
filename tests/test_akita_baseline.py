"""Allow only recorded motion and collar revisions over the accepted artwork."""

import hashlib
import json
from pathlib import Path
import unittest


class AkitaBaselineTests(unittest.TestCase):
    def test_only_recorded_artwork_revisions_extend_the_baseline(self) -> None:
        root = Path(__file__).resolve().parents[1]
        baseline = json.loads((root / 'docs/artwork/akita/accepted-baseline.json').read_text())
        assets = root / 'codex_pet/assets/akita'
        derived = json.loads((root / 'docs/artwork/akita/2026-10-pack/derived-blink.json').read_text())
        actual = {
            path.relative_to(assets).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in assets.rglob('*.png')
        }
        delivery = json.loads((root / 'docs/artwork/akita/2026-10-local-motion/delivery.json').read_text())
        changes = delivery['sha256']
        self.assertEqual(set(changes), {'frames/running/02.png', 'frames/ready/05.png', 'frames/ready/06.png'})
        collars = json.loads((root / 'docs/artwork/akita/2026-10-collar/delivery.json').read_text())
        expected_collars = {
            f'frames/{state}/{frame:02}.png'
            for state, count in [('idle', 8), ('needs_input', 4), ('ready', 5), ('blocked', 4)]
            for frame in range(count)
        } | {f'{state}.png' for state in ('idle', 'needs_input', 'ready', 'blocked')}
        self.assertEqual(set(collars['sha256']), expected_collars)
        continuity = json.loads((root / 'docs/artwork/akita/2026-10-continuity/delivery.json').read_text())
        self.assertEqual(set(continuity['sha256']), {
            'frames/running/08.png', 'frames/running/09.png',
            'frames/ready/06.png', 'frames/ready/07.png',
        })
        self.assertEqual(actual, {**baseline['sha256'], **changes, **collars['sha256'],
                                  **continuity['sha256'], 'derived/ready-blink.png': derived['png_sha256']})
        original = root / 'docs/artwork/akita/2026-10-local-motion/running-original.png'
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), baseline['sha256']['frames/running/02.png'])


if __name__ == '__main__':
    unittest.main()
