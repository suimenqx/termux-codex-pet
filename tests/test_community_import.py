"""Exercise offline imports through their public build boundary, without art/network."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from tools.pet_import.pipeline import build_recipe


class CommunityImportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        self.output = self.root / 'output'
        self.path = self.root / 'recipe.json'
        self.recipe = {
            'version': 1, 'id': 'fixture', 'name': 'Fixture', 'description': 'Generated test art',
            'canvas': [16, 16], 'sources': {}, 'credits': 'Synthetic fixture', 'sequences': {},
            'clips': {'cycle': {'sequence': 'motion', 'end': 'loop'},
                      'done': {'sequence': 'motion', 'end': 'cycle'},
                      'stop': {'sequence': 'motion', 'select': [-1], 'end': 'hold', 'hold': True}},
            'roles': {'idle': 'cycle', 'running': 'cycle', 'needs_input': 'cycle',
                      'ready': 'done', 'blocked': 'stop'}}

    def source(self, data):
        sha = hashlib.sha256(data).hexdigest()
        (self.cache / sha).write_bytes(data)
        self.recipe['sources']['art'] = {'url': 'https://example.invalid/art', 'sha256': sha}
        return self.cache / sha

    def build(self):
        self.path.write_text(json.dumps(self.recipe))
        return build_recipe(self.path, self.cache, self.output)

    def gif(self):
        frames = []
        for x, color in [(1, 1), (6, 2), (10, 3)]:
            frame = Image.new('P', (16, 16), 0)
            frame.putpalette([0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255] + [0] * 756)
            frame.paste(color, (x, 5, x + 3, 9))
            frames.append(frame)
        data = io.BytesIO()
        frames[0].save(data, format='GIF', save_all=True, append_images=frames[1:],
                       duration=[70, 130, 200], loop=0, transparency=0, disposal=2, optimize=False)
        path = self.source(data.getvalue())
        self.recipe['sequences']['motion'] = {'kind': 'gif', 'source': 'art'}
        return path

    def test_gif_disposal_exposures_roles_and_deterministic_export(self):
        self.gif()
        pack = self.build()
        manifest = json.loads((pack / 'pet.json').read_text())
        self.assertEqual([f['duration_ms'] for f in manifest['clips']['cycle']['frames']], [70, 130, 200])
        self.assertEqual(manifest['clips']['done']['end'], {'mode': 'next', 'clip': 'cycle'})
        self.assertIsNone(manifest['clips']['stop']['frames'][0]['duration_ms'])
        with Image.open(pack / manifest['frames']['motion/0001']['file']) as frame:
            self.assertEqual(frame.getpixel((2, 6))[3], 0)  # Previous red rectangle was disposed.
            self.assertEqual(frame.getpixel((7, 6)), (0, 255, 0, 255))
        second = build_recipe(self.path, self.cache, self.root / 'another')
        self.assertEqual({p.relative_to(pack): p.read_bytes() for p in pack.rglob('*') if p.is_file()},
                         {p.relative_to(second): p.read_bytes() for p in second.rglob('*') if p.is_file()})

    def test_hash_failure_and_existing_destination_preserve_previous_work(self):
        source = self.gif()
        pack = self.build()
        before = (pack / 'pet.json').read_bytes()
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual((pack / 'pet.json').read_bytes(), before)
        self.recipe['id'] = 'second'
        source.write_bytes(b'corrupt source')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.build()
        self.assertFalse((self.output / 'second').exists())

    def test_bad_download_does_not_pollute_cache_or_publish_pack(self):
        self.gif()
        for path in self.cache.iterdir():
            path.unlink()
        self.path.write_text(json.dumps(self.recipe))
        response = io.BytesIO(b'wrong server response')
        response.url = 'https://example.invalid/art'
        with patch('tools.pet_import.pipeline.urllib.request.urlopen', return_value=response), \
                self.assertRaisesRegex(ValueError, 'Download hash mismatch'):
            build_recipe(self.path, self.cache, self.output, download=True)
        self.assertEqual(list(self.cache.iterdir()), [])
        self.assertFalse((self.output / 'fixture').exists())

    def test_mid_export_layout_failure_removes_partial_pack(self):
        self.gif()
        # Frame0 fits, frame1 fails; already-written PNGs must not be published.
        self.recipe['sequences']['motion']['layout'] = {'offset': [8, 0]}
        with self.assertRaisesRegex(ValueError, 'clips nontransparent'):
            self.build()
        self.assertEqual([p.name for p in self.output.iterdir()], ['.build.lock'])

    def xml(self, end='100'):
        sheet = Image.new('RGBA', (32, 16))
        sheet.paste((255, 0, 255, 255), (1, 1, 3, 3))  # Exact color-key.
        sheet.paste((255, 0, 0, 128), (5, 5, 8, 8))
        sheet.paste((0, 255, 0, 255), (20, 5, 23, 8))
        data = io.BytesIO()
        sheet.save(data, format='PNG')
        xml = f'''<pet xmlns="https://esheep.petrucci.ch/"><image><tilesx>2</tilesx><tilesy>1</tilesy>
        <png>{base64.b64encode(data.getvalue()).decode()}</png><transparency>Magenta</transparency></image>
        <animations><animation id="1"><start><interval>100</interval></start>
        <end><interval>{end}</interval></end><sequence repeat="random" repeatfrom="0">
        <frame>0</frame><frame>1</frame><frame>1</frame></sequence></animation></animations></pet>'''
        self.source(xml.encode())
        self.recipe['sequences']['motion'] = {'kind': 'esheep', 'source': 'art', 'animation': '1'}

    def test_xml_namespace_tiles_alpha_repeated_exposures_and_deduplication(self):
        self.xml()
        pack = self.build()
        manifest = json.loads((pack / 'pet.json').read_text())
        self.assertEqual(len(list((pack / 'frames').rglob('*.png'))), 2)
        frames = manifest['clips']['cycle']['frames']
        self.assertEqual([f['duration_ms'] for f in frames], [100, 100, 100])
        self.assertEqual(manifest['frames'][frames[1]['frame']], manifest['frames'][frames[2]['frame']])
        with Image.open(pack / manifest['frames'][frames[0]['frame']]['file']) as image:
            self.assertEqual(image.getpixel((1, 1))[3], 0)
            self.assertEqual(image.getpixel((6, 6)), (255, 0, 0, 128))
        with Image.open(pack / manifest['frames'][frames[1]['frame']]['file']) as image:
            self.assertEqual(image.getpixel((5, 6)), (0, 255, 0, 255))

    def test_unsupported_xml_timing_is_explicit_not_approximated(self):
        self.xml('200')
        with self.assertRaisesRegex(ValueError, 'equal positive literal intervals'):
            self.build()
        self.assertFalse((self.output / 'fixture').exists())

    def test_invalid_recipe_id_cannot_escape_output(self):
        self.gif()
        self.recipe['id'] = '../escape'
        with self.assertRaisesRegex(ValueError, 'invalid pet ID'):
            self.build()
        self.assertFalse((self.root / 'escape').exists())

    def test_decoded_budget_failure_publishes_nothing(self):
        self.gif()
        with patch('tools.pet_import.pipeline.MAX_PACK_BYTES', 16 * 16 * 4 * 2), \
                self.assertRaisesRegex(ValueError, 'decoded frame budget'):
            self.build()
        self.assertFalse((self.output / 'fixture').exists())

    def test_original_notice_can_declare_legacy_encoding(self):
        self.gif()
        notice = 'Copyright Jürgen'.encode('latin-1')
        sha = hashlib.sha256(notice).hexdigest()
        (self.cache / sha).write_bytes(notice)
        self.recipe['sources']['notice'] = {'url': 'https://example.invalid/AUTHORS',
            'sha256': sha, 'encoding': 'latin-1'}
        self.recipe['notices'] = ['notice']
        pack = self.build()
        self.assertIn('Copyright Jürgen', (pack / 'CREDITS.md').read_text())
