"""Actual offline entrypoints share runtime pixels, count variants and timing."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from tools.preview_animation import _timeline
from codex_pet.pet_runtime import PetRuntime, PetVisual
from codex_pet.frames import FrameSource, FrameComposer
from codex_pet.image_codec import decode_png


class OfflinePipelineTests(unittest.TestCase):
    def test_preview_matches_live_requests_for_all_pets_and_transition(self):
        for pet in ('akita', 'robot', 'pixel_dog'):
            for state, old in [('idle', None), ('running', None), ('needs_input', None),
                               ('ready', None), ('ready', 'running'), ('blocked', None)]:
                with self.subTest(pet=pet, state=state, source=old):
                    rows = _timeline(state, 1, old, appearance=pet, count=10)
                    runtime = PetRuntime(PetVisual(pet, old or state, 10), 0)
                    if old:
                        runtime.sync(PetVisual(pet, state, 10), 0)
                    source, composer = FrameSource(), FrameComposer()
                    now = 0
                    for row in rows:
                        runtime.tick(now)
                        request = runtime.current()
                        frame = composer.compose(source.frame(
                            request.pack_id, request.revision, request.reference), request.count)
                        png = base64.b64decode(row['src'].split(',', 1)[1])
                        w, h, actual = decode_png(png)
                        self.assertEqual(
                            (w, h, bytes(actual)), (frame.width, frame.height, frame.pixels))
                        self.assertEqual(row['reference'], request.reference)
                        now += row['seconds']

    def test_tool_commands_export_all_pets_badges_and_holds(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for pet, state in [('robot', 'running'), ('robot', 'blocked'), ('akita', 'ready'),
                               ('pixel_dog', 'running'), ('pixel_dog', 'ready')]:
                target = folder/f'{pet}-{state}'
                command = [sys.executable, str(root/'tools/audit_animation.py'), '--pet', pet, '--state', state,
                           '--cycles', '1', '--density', '1', '--count', '10', '--output', str(target)]
                if state == 'ready':
                    command += ['--from-state', 'running']
                result = subprocess.run(
                    command, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0,
                                 result.stderr+result.stdout)
                report = json.loads((target/'audit.json').read_text())
                rows = _timeline(state, 1, 'running' if state ==
                                 'ready' else None, appearance=pet, count=10)
                self.assertEqual([(r['reference'], r['delay_seconds']) for r in report['frames']],
                                 [(r['reference'], r['seconds']) for r in rows])
                self.assertTrue((target/'contact-sheet.png').is_file())
                preview = target/'preview.html'
                result = subprocess.run([sys.executable, str(root/'tools/preview_animation.py'),
                                         '--pet', pet, '--state', state, '--count', '10', '--cycles', '1',
                                         '--output', str(preview)], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('data:image/png;base64,', preview.read_text())


if __name__ == '__main__':
    unittest.main()
