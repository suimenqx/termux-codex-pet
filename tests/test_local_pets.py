"""Local-only packs survive releases and use the normal selection/playback path."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from codex_pet import cli, pets
from codex_pet.local_pets import import_local_pack
from codex_pet.pet_pack import bundled_pack
from codex_pet.pet_runtime import PetRuntime, PetVisual
from codex_pet.frames import FrameSource
from codex_pet.preferences import read_config, save_position, selected_appearance

ROOT = Path(__file__).resolve().parents[1]


class LocalPetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.patcher = patch.object(pets, 'local_pets_dir', return_value=self.folder / 'pets')
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        bundled_pack.cache_clear()
        self.addCleanup(bundled_pack.cache_clear)
        self.source = self.folder / 'source'
        shutil.copytree(ROOT / 'codex_pet/assets/pixel_dog', self.source)
        self.manifest = json.loads((self.source / 'pet.json').read_text())
        self.manifest.update(id='my_dog', display_name='My Dog', description='Local preview')
        self.write_manifest()

    def write_manifest(self):
        (self.source / 'pet.json').write_text(json.dumps(self.manifest))

    def test_import_selection_pixels_and_source_independence(self):
        installed = import_local_pack(self.source)
        shutil.rmtree(self.source)
        self.assertEqual(installed.id, 'my_dog')
        self.assertEqual(pets.appearance_for('my_dog').name, 'My Dog')
        config = self.folder / 'config.json'
        save_position(config, 40, 60)
        with patch.object(cli, 'CONFIG', config), patch.object(cli, 'request', side_effect=OSError), \
                patch.object(cli, '_status', return_value=None), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli._pet_use('my_dog'), 0)
            self.assertEqual(cli._pet_list(), 0)
        self.assertIn('* my_dog', output.getvalue())
        self.assertEqual(read_config(config)['position'], {'x': 40, 'y': 60})
        self.assertEqual(selected_appearance(config), 'my_dog')
        runtime = PetRuntime(PetVisual('my_dog', 'running'), 0)
        runtime.tick(.13)
        r = runtime.current()
        actual = FrameSource().frame(r.pack_id, r.revision, r.reference)
        original = bundled_pack('pixel_dog')
        expected = FrameSource().frame(original.id, original.revision, 'running/01')
        self.assertEqual(actual.pixels, expected.pixels)
        self.assertEqual(pets.DEFAULT_APPEARANCE, 'akita')

    def test_invalid_frame_and_builtin_collision_publish_nothing(self):
        for bad in ('akita', '../escape', 'my_dog'):
            self.manifest['id'] = bad
            self.write_manifest()
            if bad == 'my_dog':
                (self.source / 'frames/running/00.png').write_bytes(b'invalid')
            with self.subTest(id=bad), self.assertRaises(ValueError):
                import_local_pack(self.source)
            self.assertEqual(set(pets.appearance_catalog()), set(pets.APPEARANCE_BY_ID))

    def test_reimport_refuses_to_change_installed_pack(self):
        import_local_pack(self.source)
        before = (pets.local_pets_dir() / 'my_dog/pet.json').read_bytes()
        self.manifest['clips']['running']['frames'][0]['duration_ms'] = 999
        self.write_manifest()
        with self.assertRaises(FileExistsError):
            import_local_pack(self.source)
        self.assertEqual((pets.local_pets_dir() / 'my_dog/pet.json').read_bytes(), before)

    def test_bad_registry_or_missing_pack_falls_back_without_native_import(self):
        import_local_pack(self.source)
        (pets.local_pets_dir() / 'my_dog/pet.json').unlink()
        self.assertEqual(pets.appearance_for('my_dog').id, 'akita')
        (pets.local_pets_dir() / 'catalog.json').write_text('{')
        self.assertEqual(set(pets.appearance_catalog()), set(pets.APPEARANCE_BY_ID))

    def test_failed_catalog_publication_rolls_back_only_new_pack(self):
        import_local_pack(self.source)
        index = pets.local_pets_dir() / 'catalog.json'
        before = index.read_bytes()
        self.manifest['id'] = 'second_dog'
        self.write_manifest()
        with patch('codex_pet.local_pets.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                import_local_pack(self.source)
        self.assertEqual(index.read_bytes(), before)
        self.assertTrue((pets.local_pets_dir() / 'my_dog/pet.json').is_file())
        self.assertFalse((pets.local_pets_dir() / 'second_dog').exists())


if __name__ == '__main__':
    unittest.main()
