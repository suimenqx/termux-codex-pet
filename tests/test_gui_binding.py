"""Check the Termux:GUI boundary that makes image touches observable."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_pet import gui


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

    def send_read_msg(self, message: dict) -> int:
        assert message["method"] == "newActivity"
        return 1

    def send_msg(self, message: dict) -> None:
        self.messages.append(message)


class FakeView:
    next_id = 1

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.id = FakeView.next_id
        FakeView.next_id += 1
        self.touch_enabled = False

    def setdimensions(self, *args: object) -> None:
        pass

    def setbackgroundcolor(self, *args: object) -> None:
        pass

    def settextsize(self, *args: object) -> None:
        pass

    def settextcolor(self, *args: object) -> None:
        pass

    def setmargin(self, *args: object) -> None:
        pass

    def sendtouchevent(self, enabled: bool) -> None:
        self.touch_enabled = enabled

    def getdimensions(self) -> tuple[int, int]:
        return 192, 192


class GuiBindingTests(unittest.TestCase):
    def test_robot_image_emits_touch_events(self) -> None:
        FakeView.next_id = 1
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(gui.tg, "LinearLayout", FakeView), \
             patch.object(gui.tg, "TextView", FakeView), \
             patch.object(gui.tg, "ImageView", FakeView):
            pet = gui.OverlayUI(connection, Path(directory) / "config.json")

        self.assertTrue(pet.face.touch_enabled)
        self.assertTrue(pet.detail_left.touch_enabled)
        self.assertTrue(pet.detail_right.touch_enabled)


if __name__ == "__main__":
    unittest.main()
