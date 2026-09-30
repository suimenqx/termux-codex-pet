"""Check the single icon-only Termux:GUI overlay boundary."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_pet import gui
from codex_pet.art import icon, rgba_icon


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


class FakeBuffer:
    def __init__(self, _connection: object, width: int, height: int) -> None:
        self.mem = bytearray(width * height * 4)
        self.blit_count = 0
        self.remove_count = 0

    def blit(self) -> None:
        self.blit_count += 1

    def remove(self) -> None:
        self.remove_count += 1


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
        buffer = FakeBuffer(connection, 256, 256)
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(gui.tg, "LinearLayout", FakeView), \
             patch.object(gui.tg, "ImageView", FakeView), \
             patch.object(gui.tg, "TextView", side_effect=AssertionError("text UI is not allowed")), \
             patch.object(gui.tg, "Buffer", return_value=buffer):
            pet = gui.OverlayUI(connection, Path(directory) / "config.json")
            for appearance in ("akita", "robot"):
                for state in ("idle", "running", "needs_input", "ready", "blocked"):
                    pet.render({"state": state, "running_count": 2,
                                "appearance": appearance, "project": "repo",
                                "elapsed": 10, "message": "hidden detail"})
                    if appearance == "robot":
                        self.assertEqual(pet.face.image, icon(state, 0, 2, appearance))
                    else:
                        self.assertIs(pet.face.buffer, buffer)
                        self.assertEqual(bytes(buffer.mem), rgba_icon(state, 0, 2))
            self.assertEqual(buffer.blit_count, 5)
            self.assertEqual(pet.face.refresh_count, 5)
            self.assertFalse(pet.buffer_bound)
            pet.render({"state": "running", "running_count": 2, "appearance": "akita"})
            self.assertTrue(pet.buffer_bound)
            self.assertEqual(bytes(buffer.mem), rgba_icon("running", 0, 2))
            pet.close()
            self.assertEqual(buffer.remove_count, 1)

        self.assertEqual(connection.next_aid, 2)

    def test_png_frames_are_used_when_the_shared_buffer_is_unavailable(self) -> None:
        FakeView.next_id = 1
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(gui.tg, "LinearLayout", FakeView), \
             patch.object(gui.tg, "ImageView", FakeView), \
             patch.object(gui.tg, "Buffer", side_effect=TypeError("unsupported")) as make_buffer, \
             patch.object(gui.LOG, "warning"):
            pet = gui.OverlayUI(connection, Path(directory) / "config.json")
            pet.render({"state": "running", "running_count": 2, "appearance": "akita"}, frame=3)
            pet.render({"state": "running", "running_count": 2, "appearance": "akita"}, frame=4)

        self.assertEqual(pet.face.image, icon("running", 4, 2))
        self.assertEqual(len(pet.face.image_updates), 2)
        self.assertTrue(pet.buffer_unavailable)
        make_buffer.assert_called_once()


if __name__ == "__main__":
    unittest.main()
