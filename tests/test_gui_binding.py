"""Check the single icon-only Termux:GUI overlay boundary."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_pet import gui
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


class GuiBindingTests(unittest.TestCase):
    def test_running_count_changes_do_not_restart_other_state_animations(self) -> None:
        first = {"appearance": "akita", "state": "idle", "running_count": 1}
        later = {"appearance": "akita", "state": "idle", "running_count": 4}
        self.assertEqual(gui._visual_key(first), gui._visual_key(later))
        self.assertNotEqual(
            gui._visual_key({**first, "state": "running"}),
            gui._visual_key({**later, "state": "running"}),
        )

    def test_only_one_overlay_and_no_text_views_are_created(self) -> None:
        FakeView.next_id = 1
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(gui.tg, "LinearLayout", FakeView), \
             patch.object(gui.tg, "ImageView", FakeView), \
             patch.object(gui.tg, "TextView", side_effect=AssertionError("text UI is not allowed")):
            pet = gui.OverlayUI(connection, Path(directory) / "config.json")

        self.assertEqual(connection.next_aid, 2)
        self.assertTrue(pet.face.touch_enabled)
        self.assertIs(pet.face.activity, pet.pet)
        self.assertEqual(pet.face.dimensions, [(gui.PET_SIZE_DP, gui.PET_SIZE_DP)])

    def test_each_activity_state_is_rendered_as_its_icon(self) -> None:
        FakeView.next_id = 1
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(gui.tg, "LinearLayout", FakeView), \
             patch.object(gui.tg, "ImageView", FakeView), \
             patch.object(gui.tg, "TextView", side_effect=AssertionError("text UI is not allowed")), \
             patch.object(gui.tg, "Buffer", side_effect=AssertionError("raw-alpha buffer is unsafe")):
            pet = gui.OverlayUI(connection, Path(directory) / "config.json")
            for appearance in APPEARANCES:
                for state in ("idle", "running", "needs_input", "ready", "blocked"):
                    pet.render({"state": state, "running_count": 2,
                                "appearance": appearance.id, "project": "repo",
                                "elapsed": 10, "message": "hidden detail"})
                    self.assertEqual(pet.face.image,
                                     icon(state, 0, 2, appearance.id))
                    self.assertEqual(pet.image_size_px, appearance.image_size_px)
            self.assertEqual(len(pet.face.image_updates), len(APPEARANCES) * 5)
            pet.render({"state": "running", "running_count": 2, "appearance": "akita"})
            self.assertEqual(pet.face.image, icon("running", 0, 2))
            pet.close()

        self.assertEqual(connection.next_aid, 2)

    def test_akita_animation_frames_use_png_decoding_for_alpha_compositing(self) -> None:
        FakeView.next_id = 1
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(gui.tg, "LinearLayout", FakeView), \
             patch.object(gui.tg, "ImageView", FakeView), \
             patch.object(gui.tg, "Buffer", side_effect=AssertionError("raw-alpha buffer is unsafe")):
            pet = gui.OverlayUI(connection, Path(directory) / "config.json")
            pet.render({"state": "running", "running_count": 1, "appearance": "akita"}, frame=3)
            pet.render({"state": "running", "running_count": 1, "appearance": "akita"}, frame=4)

        self.assertEqual(
            pet.face.image_updates,
            [icon("running", 3, 1), icon("running", 4, 1)],
        )


if __name__ == "__main__":
    unittest.main()
