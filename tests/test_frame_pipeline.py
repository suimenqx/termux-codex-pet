"""Visible state to image output through the real runtime and asset pipeline."""
import unittest
from codex_pet.pet_runtime import PetRuntime, PetVisual
from codex_pet.frames import FrameSource, FrameComposer
from codex_pet.renderer.protocol import RgbaFrame
from test_daemon_notifications import isolated_daemon


class FramePipelineTests(unittest.TestCase):
    def test_hook_state_selects_a_frame_without_a_native_renderer(self):
        with isolated_daemon() as daemon:
            daemon.process({'action':'event','event':{'state':'running','session_id':'one'}})
            runtime = PetRuntime(PetVisual.from_snapshot(daemon.snapshot()), 0.0)
            request = runtime.current()
            source = FrameSource()
            composer = FrameComposer()
            frame = composer.compose(source.frame(request.pack_id, request.revision, request.reference), request.count)
            self.assertEqual((frame.width, frame.height), (256,256))
            self.assertEqual(len(frame.pixels),256*256*4)
            self.assertAlmostEqual(runtime.deadline, .04)
            self.assertEqual(runtime.current(), request)

    def test_frame_rejects_mutable_or_incorrect_length_pixels(self):
        for pixels in (b'123', bytearray(4)):
            with self.assertRaises(ValueError):
                RgbaFrame(('test',), 1, 1, pixels)


if __name__ == '__main__':
    unittest.main()
