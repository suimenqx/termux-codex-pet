"""Check the single icon-only Termux:GUI overlay boundary."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_pet import gui
from codex_pet.art import icon


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
        self.dimensions: list[tuple[object, ...]] = []

    def setdimensions(self, *args: object) -> None:
        self.dimensions.append(args)

    def setbackgroundcolor(self, *_args: object) -> None:
        pass

    def sendtouchevent(self, enabled: bool) -> None:
        self.touch_enabled = enabled

    def setimage(self, value: bytes) -> None:
        self.image = value

    def getdimensions(self) -> tuple[int, int]:
        return 192, 192


class GuiBindingTests(unittest.TestCase):
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
             patch.object(gui.tg, "TextView", side_effect=AssertionError("text UI is not allowed")):
            pet = gui.OverlayUI(connection, Path(directory) / "config.json")
            for state in ("idle", "running", "needs_input", "ready", "blocked"):
                pet.render({"state": state, "running_count": 2,
                            "project": "repo", "elapsed": 10, "message": "hidden detail"})
                self.assertEqual(pet.face.image, icon(state, 0, 2))

        self.assertEqual(connection.next_aid, 2)


if __name__ == "__main__":
    unittest.main()
