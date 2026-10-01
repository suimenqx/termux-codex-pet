from types import SimpleNamespace
import hashlib
import json
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

from codex_pet import art
from codex_pet.animation import AKITA_FRAME_COUNTS
from codex_pet.art import _premultiply_rgba, premultiplied_icon, rgba_icon
from codex_pet.frame_display import FrameDisplay
from codex_pet.pets import appearance_for


class FrameDisplayTests(unittest.TestCase):
    def setUp(self) -> None:
        art._akita_premultiplied.cache_clear()
        art._native_archive.cache_clear()

    def tearDown(self) -> None:
        art._akita_premultiplied.cache_clear()
        art._native_archive.cache_clear()

    def test_baked_native_frames_match_every_png_and_manifest_hash(self) -> None:
        root = art.AKITA_ASSET_DIR
        manifest = json.loads((root / 'rig-manifest.json').read_text())
        path = root / 'native-frames.zip'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         manifest['native_archive']['sha256'])
        with ZipFile(path) as archive:
            self.assertEqual(len(archive.namelist()), sum(AKITA_FRAME_COUNTS.values()))
            for state, count in AKITA_FRAME_COUNTS.items():
                for frame in range(count):
                    pixels = archive.read(f'{state}/{frame:02}.rgba')
                    self.assertEqual(pixels, _premultiply_rgba(rgba_icon(state, frame)))
                    self.assertEqual(hashlib.sha256(pixels).hexdigest(),
                                     manifest['clips'][state]['frames'][frame]['native_rgba_sha256'])

    def test_cold_live_frames_and_badges_need_no_png_decode_or_premultiplication(self) -> None:
        for state, frame, count in [('idle', 3, 0), ('running', 5, 1),
                                    ('running', 17, 2), ('running', 24, 10), ('ready', 54, 0)]:
            expected = _premultiply_rgba(rgba_icon(state, frame, count))
            art._akita_premultiplied.cache_clear()
            with patch.object(art, '_decode_rgba_png', side_effect=AssertionError('live PNG decode')), \
                 patch.object(art, '_premultiply_rgba', side_effect=AssertionError('live premultiplication')):
                self.assertEqual(premultiplied_icon(state, frame, count), expected)

    def test_missing_native_archive_falls_back_but_invalid_pixel_size_is_rejected(self) -> None:
        expected = _premultiply_rgba(rgba_icon('blocked', 7))
        art._akita_premultiplied.cache_clear()
        with patch.object(art, 'ZipFile', side_effect=FileNotFoundError):
            self.assertEqual(premultiplied_icon('blocked', 7), expected)
        art._akita_premultiplied.cache_clear()
        with patch.object(art, 'ZipFile') as archive:
            archive.return_value.read.return_value = b'short'
            with self.assertRaisesRegex(ValueError, 'native Akita frame size'):
                premultiplied_icon('blocked', 7)

    def test_premultiplication_covers_every_alpha_and_channel_value(self) -> None:
        source = bytearray()
        expected = bytearray()
        for alpha in range(256):
            for value in range(256):
                color = (value, (value * 37) % 256, 255 - value)
                source.extend((*color, alpha))
                expected.extend((*((c * alpha + 127) // 255 for c in color), alpha))
        self.assertEqual(_premultiply_rgba(source), expected)
        with self.assertRaises(ValueError):
            _premultiply_rgba(b'bad')

    def test_visible_transparent_fur_cannot_emit_unassociated_bright_colors(self) -> None:
        source = rgba_icon('running', 8, 2)
        result = premultiplied_icon('running', 8, 2)
        self.assertNotEqual(source, result)
        self.assertEqual(source[3::4], result[3::4])
        for i in range(0, len(result), 4):
            alpha = result[i + 3]
            self.assertTrue(all(result[i + c] <= alpha for c in range(3)))
            if alpha == 0:
                self.assertEqual(result[i:i + 4], bytes(4))

    def test_buffer_is_reused_and_copy_completes_before_the_next_write(self) -> None:
        actions = []
        buffer = SimpleNamespace(mem=bytearray(256 * 256 * 4),
                                 blit=lambda: actions.append('blit'),
                                 remove=Mock())
        face = SimpleNamespace(setbuffer=lambda b: actions.append('bind'),
                               refresh=lambda: actions.append('refresh'),
                               getdimensions=lambda: actions.append('ack'), setimage=Mock())
        connection = object()
        with patch('codex_pet.frame_display.tg.Buffer', return_value=buffer) as create:
            display = FrameDisplay(connection, face)
            for frame in (0, 1):
                display.show(appearance_for('akita'), 'running', frame, 1)
                self.assertEqual(buffer.mem, premultiplied_icon('running', frame, 1))
            create.assert_called_once_with(connection, 256, 256)
            self.assertEqual(actions, ['blit', 'bind', 'refresh', 'ack', 'blit', 'refresh', 'ack'])
            face.setimage.assert_not_called()
            display.show(appearance_for('robot'), 'idle', 0, 0)
            face.setimage.assert_called_once()
            display.show(appearance_for('akita'), 'idle', 0, 0)
            self.assertEqual(actions[-4:], ['blit', 'bind', 'refresh', 'ack'])
            display.close()
            display.close()
            buffer.remove.assert_called_once()

    def test_disconnect_still_closes_the_local_mapping_and_descriptor(self) -> None:
        buffer = SimpleNamespace(mem=Mock(), fd=123,
                                 remove=Mock(side_effect=OSError('disconnected')))
        display = FrameDisplay(object(), object())
        display.buffer = buffer
        with patch('codex_pet.frame_display.os.close') as close:
            with self.assertRaises(OSError):
                display.close()
            buffer.mem.close.assert_called_once()
            close.assert_called_once_with(123)
        self.assertIsNone(display.buffer)


if __name__ == '__main__':
    unittest.main()
