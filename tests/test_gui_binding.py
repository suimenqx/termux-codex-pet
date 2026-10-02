"""Check the single icon-only Termux:GUI overlay boundary."""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from codex_pet import gui
from codex_pet.renderer import termux_gui as backend
from codex_pet.frames import FrameSource, FrameComposer
from codex_pet.pet_runtime import PetRuntime, PetVisual
from codex_pet.image_codec import decode_png
from codex_pet.animation import AnimationTimeline
from codex_pet.art import icon
from codex_pet.pets import APPEARANCES


class FakeMainSocket:
    timeout: float | None = None

    def gettimeout(self) -> float | None:
        return self.timeout

    def settimeout(self, value: float | None) -> None:
        self.timeout = value


class FakeConnection:
    def __init__(self) -> None:
        self._main = FakeMainSocket()
        self.messages: list[dict] = []
        self.next_aid = 1

    def send_read_msg(self, message: dict) -> int:
        assert message["method"] == "newActivity"
        aid = self.next_aid
        self.next_aid += 1
        return aid

    def send_msg(self, message: dict) -> None:
        self.messages.append(message)


class FakeView:
    next_id = 1

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.id = FakeView.next_id
        FakeView.next_id += 1
        self.activity = args[0]
        self.touch_enabled = False
        self.image = b""
        self.image_updates: list[bytes] = []
        self.buffer = None
        self.refresh_count = 0
        self.dimensions: list[tuple[object, ...]] = []

    def setdimensions(self, *args: object) -> None:
        self.dimensions.append(args)

    def setbackgroundcolor(self, *_args: object) -> None:
        pass

    def sendtouchevent(self, enabled: bool) -> None:
        self.touch_enabled = enabled

    def setimage(self, value: bytes) -> None:
        self.image = value
        self.image_updates.append(value)
        self.buffer = None

    def setbuffer(self, buffer: object) -> None:
        self.buffer = buffer

    def refresh(self) -> None:
        self.refresh_count += 1

    def getdimensions(self) -> tuple[int, int]:
        return 192, 192



def render(renderer, snapshot, frame=0):
    runtime = PetRuntime(PetVisual.from_snapshot(snapshot), 0.0)
    for _ in range(frame):
        runtime.tick(runtime.deadline)
    request = runtime.current()
    source, composer = FrameSource(), FrameComposer()
    renderer.present(composer.compose(source.frame(request.pack_id, request.revision, request.reference), request.count))


class GuiBindingTests(unittest.TestCase):
    def test_hook_wakes_do_not_resend_unchanged_png_frames(self) -> None:
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(backend.tg, "LinearLayout", FakeView), \
             patch.object(backend.tg, "ImageView", FakeView):
            pet = backend.TermuxGuiRenderer(connection, Path(directory) / "config.json")
            snapshot = {"state": "running", "running_count": 1, "appearance": "akita"}
            for _ in range(50):
                render(pet, snapshot, frame=0)
            self.assertEqual(len(pet.face.image_updates), 1)
            render(pet, snapshot, frame=1)
            self.assertEqual(len(pet.face.image_updates), 2)
            render(pet, {**snapshot, "running_count": 2}, frame=1)
            self.assertEqual(len(pet.face.image_updates), 3)
            render(pet, {**snapshot, "state": "ready"}, frame=0)
            self.assertEqual(len(pet.face.image_updates), 4)

    def test_worker_preserves_count_reset_and_interrupts_ready_entry(self):
        snapshot = {"appearance":"akita", "state":"running", "running_count":1}
        rendered = []
        worker = gui.GuiWorker(None, lambda: snapshot, lambda *_: None)
        worker.ui = SimpleNamespace(present=lambda frame: rendered.append(frame.key[2]))
        try:
            worker.refresh(0.0)
            worker.refresh(.09)
            snapshot['running_count'] = 2
            worker.refresh(.1)
            snapshot['state'] = 'ready'
            worker.refresh(1.0)
            worker.refresh(1.120001)
            snapshot['state'] = 'needs_input'
            worker.refresh(1.13)
        finally:
            worker.stop()
        self.assertEqual(rendered, ['running/00', 'running/01', 'running/00',
                                    'ready/05', 'ready/06', 'needs_input/00'])

    def test_only_one_overlay_and_no_text_views_are_created(self) -> None:
        FakeView.next_id = 1
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(backend.tg, "LinearLayout", FakeView), \
             patch.object(backend.tg, "ImageView", FakeView), \
             patch.object(backend.tg, "TextView", side_effect=AssertionError("text UI is not allowed")):
            pet = backend.TermuxGuiRenderer(connection, Path(directory) / "config.json")

        self.assertEqual(connection.next_aid, 2)
        self.assertTrue(pet.face.touch_enabled)
        self.assertIs(pet.face.activity, pet.pet)
        self.assertEqual(pet.face.dimensions, [(backend.PET_SIZE_DP, backend.PET_SIZE_DP)])

    def test_each_activity_state_is_rendered_as_its_icon(self) -> None:
        FakeView.next_id = 1
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(backend.tg, "LinearLayout", FakeView), \
             patch.object(backend.tg, "ImageView", FakeView), \
             patch.object(backend.tg, "TextView", side_effect=AssertionError("text UI is not allowed")), \
             patch.object(backend.tg, "Buffer", side_effect=AssertionError("raw-alpha buffer is unsafe")):
            pet = backend.TermuxGuiRenderer(connection, Path(directory) / "config.json")
            for appearance in APPEARANCES:
                for state in ("idle", "running", "needs_input", "ready", "blocked"):
                    render(pet, {"state": state, "running_count": 2,
                                "appearance": appearance.id, "project": "repo",
                                "elapsed": 10, "message": "hidden detail"})
                    self.assertEqual(decode_png(pet.face.image),
                                     decode_png(icon(state, 0, 2, appearance.id)))
                    self.assertEqual(pet.image_width, appearance.image_size_px)
            self.assertEqual(len(pet.face.image_updates), len(APPEARANCES) * 5)
            render(pet, {"state": "running", "running_count": 2, "appearance": "akita"})
            self.assertEqual(decode_png(pet.face.image), decode_png(icon("running", 0, 2)))
            pet.close()

        self.assertEqual(connection.next_aid, 2)

    def test_akita_animation_frames_use_png_decoding_for_alpha_compositing(self) -> None:
        FakeView.next_id = 1
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(backend.tg, "LinearLayout", FakeView), \
             patch.object(backend.tg, "ImageView", FakeView), \
             patch.object(backend.tg, "Buffer", side_effect=AssertionError("raw-alpha buffer is unsafe")):
            pet = backend.TermuxGuiRenderer(connection, Path(directory) / "config.json")
            render(pet, {"state": "running", "running_count": 1, "appearance": "akita"}, frame=3)
            render(pet, {"state": "running", "running_count": 1, "appearance": "akita"}, frame=4)

        self.assertEqual(
            [decode_png(image) for image in pet.face.image_updates],
            [decode_png(icon("running", 3, 1)), decode_png(icon("running", 4, 1))],
        )


if __name__ == "__main__":
    unittest.main()
