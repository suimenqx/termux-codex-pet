import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest

from codex_pet.art import AKITA_ASSET_DIR
from tools.audit_animation import render_audit, validated_clip, write_audit
from tools.preview_animation import _timeline


class AnimationAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ready = render_audit('ready', cycles=2, density=1)
        cls.running = render_audit('running', cycles=2, density=1)

    def test_audit_uses_production_ready_pixels_and_shared_timing(self) -> None:
        result = self.ready
        preview = _timeline('ready', cycles=2)
        self.assertEqual([frame.frame for frame in result.frames], [frame['frame'] for frame in preview])
        self.assertEqual([frame.delay_seconds for frame in result.frames], [frame['seconds'] for frame in preview])
        self.assertTrue(all(len(frame.rgba) == 64 * 64 * 4 for frame in result.frames))
        self.assertEqual(result.report['duration_seconds'], 8.32)
        self.assertEqual(result.report['frame_count'], 96)
        self.assertTrue(result.report['passed'])
        self.assertEqual(result.report['rig']['scale_range'], [1, 1])
        self.assertEqual(struct.unpack_from('>II', result.contact_sheet, 16), (316, 2268))

    def test_running_audit_tracks_every_paw_and_explicit_occlusion(self) -> None:
        result = self.running
        rig = result.report['rig']
        self.assertTrue(rig['passed'])
        self.assertEqual(result.report['frame_count'], 64)
        self.assertEqual(result.report['duration_seconds'], 1.28)
        self.assertLess(rig['max_bone_length_error_px'], 1e-7)
        self.assertLess(rig['max_contact_height_error_px'], 1e-7)
        self.assertEqual(rig['border_alpha_max'], 0)
        self.assertEqual(set(rig['paws']), {'hind_near', 'hind_far', 'fore_near', 'fore_far'})
        for name, track in rig['paws'].items():
            self.assertEqual(len(track['positions']), 32)
            self.assertGreater(track['horizontal_range_dp'], 0)
            self.assertGreater(track['vertical_range_dp'], 0)
            self.assertGreater(len(track['contact_frames']), 0)
            self.assertLess(len(track['contact_frames']), 32)
            for point in track['positions']:
                self.assertEqual(point['marker_visible'], point['visible_fraction'] >= .5)
        self.assertTrue(any(not p['marker_visible'] for track in rig['paws'].values()
                            for p in track['positions']))

    def test_audit_scales_production_pixels_to_device_density(self) -> None:
        result = render_audit('blocked', density=3)
        self.assertEqual(result.report['display_size_px'], 192)
        self.assertTrue(all(len(frame.rgba) == 192 * 192 * 4 for frame in result.frames))
        self.assertTrue(result.report['passed'])

    def test_stale_frame_and_metadata_cannot_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(AKITA_ASSET_DIR / 'frames/blocked', root / 'frames/blocked')
            source = json.loads((AKITA_ASSET_DIR / 'rig-manifest.json').read_text())
            manifest = root / 'rig-manifest.json'
            manifest.write_text(json.dumps(source))
            path = root / 'frames/blocked/00.png'
            original = path.read_bytes()
            path.write_bytes(original + b'changed')
            with self.assertRaisesRegex(ValueError, 'stale PNG hash'):
                validated_clip('blocked', asset_dir=root)
            path.write_bytes(original)
            source['clips']['blocked']['frames'][0]['head']['scale'] = 1.18
            manifest.write_text(json.dumps(source))
            with self.assertRaisesRegex(ValueError, 'stale pose or timing'):
                validated_clip('blocked', asset_dir=root)

    def test_audit_writes_contact_sheet_and_copies_manifest_before_adding_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = write_audit(self.running, Path(directory))
            manifest = json.loads(manifest_path.read_text())
            self.assertTrue((Path(directory) / 'contact-sheet.png').is_file())
            self.assertEqual(manifest['frames'][6]['file'], 'frames/step-06-frame-06.png')
            self.assertTrue((Path(directory) / manifest['frames'][6]['file']).is_file())
            self.assertNotIn('file', self.running.report['frames'][6])

    def test_stale_native_archive_cannot_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(AKITA_ASSET_DIR / 'frames/blocked', root / 'frames/blocked')
            shutil.copy2(AKITA_ASSET_DIR / 'rig-manifest.json', root / 'rig-manifest.json')
            path = root / 'native-frames.zip'
            path.write_bytes((AKITA_ASSET_DIR / path.name).read_bytes() + b'changed')
            with self.assertRaisesRegex(ValueError, 'stale native archive'):
                validated_clip('blocked', asset_dir=root)


if __name__ == '__main__':
    unittest.main()
