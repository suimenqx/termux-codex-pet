"""Pixel correctness through a shared byte budget, eviction and no-cache mode."""
import hashlib
import json
from pathlib import Path
import unittest
from codex_pet.frame_cache import FrameCache
from codex_pet.frames import FrameSource, FrameComposer
from codex_pet.pet_pack import bundled_pack
from codex_pet.clip_timeline import schedule


class FrameCacheTests(unittest.TestCase):
    def test_variants_survive_eviction_without_exceeding_managed_budget(self):
        baseline = json.loads(
            (Path(__file__).parent / 'fixtures/playback-baseline.json').read_text())['cases']
        for budget in (0, 512 * 1024, 32 * 1024 * 1024):
            cache = FrameCache(budget)
            source, composer = FrameSource(cache), FrameComposer(cache)
            for pet, state, count in [('akita', 'running', 2), ('robot', 'running', 10), ('akita', 'ready', 0),
                                      ('akita', 'running', 9), ('akita', 'running', 2)]:
                pack = bundled_pack(pet)
                frames = []
                for exposure in schedule(pack, state):
                    frame = composer.compose(source.frame(
                        pet, pack.revision, exposure.reference), count)
                    frames.append(
                        (hashlib.sha256(frame.pixels).hexdigest(), exposure.duration_ms))
                    self.assertLessEqual(cache.stats().bytes_used, budget)
                expected = baseline[f'{pet}|{state}|None|1|{count}']
                self.assertEqual(hashlib.sha256(json.dumps(frames, separators=(
                    ',', ':')).encode()).hexdigest(), expected['sha256'])
            if budget == 0:
                self.assertEqual(cache.stats().entries, 0)
            if budget == 512 * 1024:
                self.assertGreater(cache.stats().evictions, 0)
            if budget == 32 * 1024 * 1024:
                self.assertGreater(cache.stats().hits, 0)
            cache.clear()
            self.assertEqual(cache.stats().bytes_used, 0)

    def test_wrong_pack_revision_cannot_reuse_old_pixels(self):
        source = FrameSource(FrameCache())
        pack = bundled_pack('akita')
        source.frame('akita', pack.revision, 'running/00')
        with self.assertRaises(ValueError):
            source.frame('akita', 'different', 'running/00')


if __name__ == '__main__':
    unittest.main()
