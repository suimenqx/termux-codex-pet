"""Pillow capability, color/alpha, allocation and real install entrypoints."""
from io import BytesIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from PIL import Image, PngImagePlugin
from codex_pet import image_codec
from codex_pet.deployment import deploy
from codex_pet.renderer.protocol import RgbaFrame
ROOT = Path(__file__).resolve().parents[1]


class PillowContractTests(unittest.TestCase):
    def test_png_capability_and_alpha_hidden_colors_roundtrip(self):
        image_codec.check_capability()
        pixels = bytes([21, 71, 131, 0, 50, 80, 120, 128, 255, 250, 10, 255])
        encoded = image_codec.encode_png(3, 1, pixels)
        self.assertEqual(image_codec.decode_png(
            encoded), (3, 1, bytearray(pixels)))

    def test_all_color_alpha_pairs_use_android_premultiplication(self):
        straight = bytes(channel for color in range(256) for alpha in range(256)
                         for channel in (color, color, color, alpha))
        expected = bytes(channel for color in range(256) for alpha in range(256)
                         for channel in ((color * alpha + 127) // 255,) * 3 + (alpha,))
        self.assertEqual(image_codec.premultiply(256, 256, straight), expected)

    def test_unknown_profiles_are_rejected_without_implicit_color_conversion(self):
        for chunk, payload in [(b'cICP', bytes([9, 16, 0, 1])), (b'gAMA', (100000).to_bytes(4, 'big'))]:
            info = PngImagePlugin.PngInfo()
            info.add(chunk, payload)
            with Image.new('RGBA', (1, 1), (50, 80, 120, 128)) as img:
                output = BytesIO()
                img.save(output, format='PNG', pnginfo=info)
            with self.assertRaisesRegex(ValueError, 'profile|gamma'):
                image_codec.decode_png(output.getvalue())
        with Image.new('RGBA', (1, 1)) as img:
            output = BytesIO()
            img.save(output, format='PNG', icc_profile=b'unknown profile')
        with self.assertRaisesRegex(ValueError, 'profile'):
            image_codec.decode_png(output.getvalue())
        with self.assertRaises(ValueError):
            RgbaFrame(('p3',), 1, 1, bytes(4), color_space='display-p3')
        with self.assertRaises(ValueError):
            image_codec.encode_png(100000, 100000, b'')

    def test_missing_pillow_or_decoder_cannot_activate_a_release(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / 'home'
            home.mkdir()
            first = deploy(ROOT, home)
            sentinel = home / '.codex/hooks.json'
            sentinel.parent.mkdir()
            sentinel.write_text('user hooks')
            args = ['deploy', '--source', str(ROOT), '--home', str(home)]
            missing = [sys.executable, '-S', '-m',
                       'codex_pet.deployment', *args]
            no_decoder = [sys.executable, '-c',
                          'from PIL import Image; del Image.core.zip_decoder; from codex_pet.deployment import main; main()', *args]
            for command in (missing, no_decoder):
                result = subprocess.run(
                    command, cwd=ROOT, capture_output=True, text=True, timeout=15)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Pillow PNG capability', result.stderr)
                self.assertEqual(
                    (home / '.local/share/codex-pet/current').resolve(), first)
                self.assertEqual(sentinel.read_text(), 'user hooks')
            second = deploy(ROOT, home)
            self.assertNotEqual(second, first)

    def test_actual_hook_status_and_catalog_do_not_import_image_or_gui_dependencies(self):
        script = '''import runpy,sys
sys.argv=sys.argv[1:]
try: runpy.run_path(sys.argv[0],run_name='__main__')
except SystemExit: pass
assert not any(name.split('.')[0] in ('PIL','termuxgui','numpy') for name in sys.modules)
print('lightweight-entry-ok')
'''
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, 'HOME': directory}
            for entry, args in [('codex-pet', ['status']), ('codex-pet', ['pet', 'list']), ('codex-pet-event', [])]:
                command = [sys.executable, '-S', '-c',
                           script, str(ROOT / 'bin' / entry), *args]
                result = subprocess.run(
                    command, cwd=ROOT, env=env, input='{}', text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('lightweight-entry-ok', result.stdout)


if __name__ == '__main__':
    unittest.main()
