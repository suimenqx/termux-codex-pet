"""Protect the current Akita production baseline."""

import hashlib
import json
from pathlib import Path
import unittest


class AkitaBaselineTests(unittest.TestCase):
    def test_current_running_delivery_matches_runtime_assets(self) -> None:
        root = Path(__file__).resolve().parents[1]
        assets = root / 'codex_pet/assets/akita'
        delivery = json.loads(
            (root / 'docs/artwork/akita/2026-10-grok-v2/delivery.json').read_text()
        )
        current = json.loads(
            (root / 'docs/artwork/akita/current-running.json').read_text()
        )
        production = {
            path.relative_to(assets).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in assets.rglob('*.png')
        }
        running = {
            key: value for key, value in production.items()
            if key.startswith('frames/running/') or key == 'running.png'
        }
        expected = delivery['sha256']
        self.assertEqual(running, expected)
        self.assertEqual(current['source_archive_sha256'], delivery['source_archive']['sha256'])
        self.assertEqual(
            {f"frames/running/{item['file']}": item['sha256'] for item in current['frames']},
            {key: value for key, value in expected.items() if key.startswith('frames/running/')},
        )

    def test_manifest_and_delivery_name_the_current_revision(self) -> None:
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / 'codex_pet/assets/akita/pet.json').read_text())
        delivery = json.loads(
            (root / 'docs/artwork/akita/2026-10-grok-v2/delivery.json').read_text()
        )
        self.assertEqual(manifest['source']['running_revision'], '2026-10-grok-v2')
        self.assertEqual(delivery['input']['frame_count'], 20)
        self.assertEqual(delivery['input']['cycle_ms'], 834)
        self.assertEqual(
            delivery['outputs']['preferred_256'],
            'review/frames_256-v2-raw/',
        )


if __name__ == '__main__':
    unittest.main()
