"""Imported dog at the public catalog, pixel-source and playback boundaries."""
import hashlib
from pathlib import Path
import unittest

from PIL import Image
from codex_pet.frames import FrameSource, FrameComposer
from codex_pet.pet_pack import bundled_pack
from codex_pet.pet_runtime import PetRuntime, PetVisual
from codex_pet.pets import APPEARANCE_BY_ID, DEFAULT_APPEARANCE

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/artwork/pixel_dog/2026-10-import/dog_medium.png'


class PixelDogTests(unittest.TestCase):
    def test_new_catalog_entry_preserves_default_and_existing_pets(self):
        self.assertIn('pixel_dog', APPEARANCE_BY_ID)
        self.assertEqual(DEFAULT_APPEARANCE, 'akita')
        self.assertIn('akita', APPEARANCE_BY_ID)
        self.assertIn('robot', APPEARANCE_BY_ID)
        self.assertEqual(bundled_pack('pixel_dog').canvas, (64, 64))

    def test_every_imported_frame_matches_its_source_cell_with_fixed_padding(self):
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                         '77a32e17840c921f939a754cc5d73622334e568a0bc2c40d55d534b487d2a58a')
        pack = bundled_pack('pixel_dog')
        source, composer = FrameSource(), FrameComposer()
        with Image.open(SOURCE) as sheet:
            for name, row, count in [('bark', 0, 4), ('running', 2, 5),
                                     ('sit', 3, 3), ('sitting', 4, 4), ('standing', 5, 4)]:
                for column in range(count):
                    ref = f'{name}/{column:02d}'
                    with self.subTest(frame=ref):
                        frame = source.frame(pack.id, pack.revision, ref)
                        with Image.frombytes('RGBA', (64, 64), frame.pixels) as actual:
                            expected = sheet.crop((column * 60, row * 38,
                                                   (column + 1) * 60, (row + 1) * 38))
                            self.assertEqual(actual.crop((2, 13, 62, 51)).tobytes(), expected.tobytes())
                            self.assertFalse(actual.crop((0, 0, 64, 13)).getbbox())
                            self.assertFalse(actual.crop((0, 51, 64, 64)).getbbox())
                        decorated = composer.compose(frame, 10)
                        self.assertNotEqual(frame.pixels, decorated.pixels)
                        self.assertEqual(len(decorated.pixels), 64 * 64 * 4)
        self.assertEqual(len(pack.frames), 20)

    def test_running_uses_five_original_poses_and_ready_sits_only_once(self):
        runtime = PetRuntime(PetVisual('pixel_dog', 'running'), 0)
        for index in range(11):
            runtime.tick(index * .13)
            self.assertEqual(runtime.current().reference, f'running/{index % 5:02d}')
        runtime.sync(PetVisual('pixel_dog', 'ready'), 2)
        for elapsed, ref in [(0, 'sit/00'), (.14, 'sit/01'), (.28, 'sit/02'),
                             (.42, 'sitting/00'), (1.22, 'sitting/00'), (800.42, 'sitting/00')]:
            runtime.tick(2 + elapsed)
            self.assertEqual(runtime.current().reference, ref)
        runtime.sync(PetVisual('pixel_dog', 'blocked'), 900)
        runtime.tick(901)
        self.assertEqual(runtime.current().reference, 'sitting/00')
        self.assertIsNone(runtime.deadline)
        runtime.sync(PetVisual('pixel_dog', 'needs_input'), 902)
        self.assertEqual(runtime.current().reference, 'bark/00')
        runtime.tick(902.6)
        self.assertEqual(runtime.current().reference, 'standing/00')
        runtime.tick(903.4)
        self.assertEqual(runtime.current().reference, 'bark/00')


if __name__ == '__main__':
    unittest.main()
