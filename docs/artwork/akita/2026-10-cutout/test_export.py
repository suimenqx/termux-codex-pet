"""Optional offline artwork experiment: export/import and playback contracts.

Requires NumPy only to reproduce the authoring experiment, never for the daemon.
These checks cannot certify the appearance or perceived quality of the motion.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from codex_pet import pets
from codex_pet.frames import FrameSource
from codex_pet.local_pets import import_local_pack
from codex_pet.pet_pack import bundled_pack
from codex_pet.pet_runtime import PetRuntime, PetVisual

RECIPE = ROOT / 'docs/artwork/akita/2026-10-cutout'


@unittest.skipUnless(importlib.util.find_spec('numpy'), 'Optional cutout authoring needs NumPy')
class AkitaCutoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('akita_cutout_recipe', RECIPE / 'build.py')
        cls.recipe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.recipe)
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.folder = Path(cls.temp.name)
        cls.pack = cls.folder / 'export'
        cls.report = cls.recipe.build(cls.pack)

    def test_export_is_reproducible_and_refuses_to_overwrite(self):
        with self.assertRaises(FileExistsError):
            self.recipe.build(self.pack)
        again = self.recipe.build(self.folder / 'again')
        self.assertEqual(again['files'], self.report['files'])
        baseline = json.loads((RECIPE / 'source.json').read_text())
        for name, sha in baseline['production_assets'].items():
            self.assertEqual(hashlib.sha256((ROOT / 'codex_pet/assets/akita' / name).read_bytes()).hexdigest(), sha)
        original = json.loads((ROOT / 'codex_pet/assets/akita/pet.json').read_text())
        candidate = json.loads((self.pack / 'pet.json').read_text())
        for name, clip in original['clips'].items():
            if name != 'running':
                self.assertEqual(candidate['clips'][name], clip)
        for name, ref in original['frames'].items():
            if not name.startswith('running/'):
                self.assertEqual((self.pack / ref['file']).read_bytes(),
                                 (ROOT / 'codex_pet/assets/akita' / ref['file']).read_bytes())

    def test_local_import_plays_every_frame_loops_and_preserves_other_pets(self):
        with patch.object(pets, 'local_pets_dir', return_value=self.folder / 'local-pets'):
            bundled_pack.cache_clear()
            self.addCleanup(bundled_pack.cache_clear)
            installed = import_local_pack(self.pack)
            self.assertEqual(installed.id, 'akita_run_cutout_v1')
            self.assertEqual(pets.DEFAULT_APPEARANCE, 'akita')
            runtime = PetRuntime(PetVisual(installed.id, 'running'), 0)
            source = FrameSource()
            for i in range(33):
                runtime.tick(i * .04)
                request = runtime.current()
                self.assertEqual(request.reference, f'running/{i % 16:02}')
                pixels = source.frame(request.pack_id, request.revision, request.reference)
                self.assertEqual(len(pixels.pixels), 256 * 256 * 4)
            for i in range(16):
                runtime.sync(PetVisual(installed.id, 'running', 2+i%2), 2+i)
                runtime.tick(2+i+i*.04)
                runtime.sync(PetVisual(installed.id, 'ready'), 2+i+i*.04)
                self.assertEqual(runtime.current().reference, 'ready/05')
                runtime.sync(PetVisual(installed.id, 'needs_input'), 2+i+.65)
                self.assertEqual(runtime.current().reference, 'needs_input/00')
            with self.assertRaises(FileExistsError):
                import_local_pack(self.pack)

    def test_curve_closes_with_matching_velocity_at_contact_and_loop(self):
        import numpy as np
        f = self.recipe.foot
        epsilon = 1e-6
        for _, _, onset, x, _, ground, _, _ in self.recipe.LEGS:
            for boundary in (onset, onset+.28, 1.):
                left = f(boundary-epsilon, onset, x, ground)[0]
                center = f(boundary, onset, x, ground)[0]
                right = f(boundary+epsilon, onset, x, ground)[0]
                np.testing.assert_allclose(left, right, atol=.001)
                np.testing.assert_allclose((center-left)/epsilon, (right-center)/epsilon, atol=.02)
        layers = {name:self.recipe.cut(self.recipe.Image.open(RECIPE/'source.png').convert('RGBA'), name)
                  for name in self.recipe.POLYGONS}
        first, _ = self.recipe.render(layers, 0.)
        wrap, _ = self.recipe.render(layers, 1.)
        self.assertEqual(first.tobytes(), wrap.tobytes())


if __name__ == '__main__':
    unittest.main()
