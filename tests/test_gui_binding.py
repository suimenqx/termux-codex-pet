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
    text_updates: list[str] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.id = FakeView.next_id
        FakeView.next_id += 1
        self.touch_enabled = False
        self.visible = kwargs.get("visibility", gui.tg.View.VISIBLE) == gui.tg.View.VISIBLE
        self.image = b""
        self.margins: list[tuple[int, str]] = []

    def setdimensions(self, *args: object) -> None:
        pass

    def setbackgroundcolor(self, *args: object) -> None:
        pass

    def settextsize(self, *args: object) -> None:
        pass

    def settextcolor(self, *args: object) -> None:
        pass

    def setmargin(self, *args: object) -> None:
        if len(args) == 2:
            self.margins.append((args[0], args[1]))

    def sendtouchevent(self, enabled: bool) -> None:
        self.touch_enabled = enabled

    def setvisibility(self, value: int) -> None:
        self.visible = value == gui.tg.View.VISIBLE

    def settext(self, value: str) -> None:
        FakeView.text_updates.append(value)

    def setimage(self, value: bytes) -> None:
        self.image = value

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

    def test_approval_card_has_separate_project_status_and_summary(self) -> None:
        FakeView.next_id = 1
        FakeView.text_updates = []
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(gui.tg, "LinearLayout", FakeView), \
             patch.object(gui.tg, "TextView", FakeView), \
             patch.object(gui.tg, "ImageView", FakeView):
            pet = gui.OverlayUI(connection, Path(directory) / "config.json")
            pet.render({"state": "approval", "working_count": 0,
                        "project": "repo", "elapsed": 0,
                        "message": "Review this permission"})

        self.assertIn("repo", FakeView.text_updates)
        self.assertIn("Needs approval", FakeView.text_updates)
        self.assertIn("Review this permission", FakeView.text_updates)
        self.assertFalse(any("\n" in value for value in FakeView.text_updates))

    def test_activity_card_tail_touches_the_robot_on_either_side(self) -> None:
        FakeView.next_id = 1
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(gui.tg, "LinearLayout", FakeView), \
             patch.object(gui.tg, "TextView", FakeView), \
             patch.object(gui.tg, "ImageView", FakeView):
            pet = gui.OverlayUI(connection, Path(directory) / "config.json")
            pet.x, pet.y = 700, 420
            pet.render({"state": "approval", "working_count": 0,
                        "project": "repo", "elapsed": 0,
                        "message": "Allow this action"})
            tail_px = round(gui.BUBBLE_TAIL_WIDTH_DP * pet.density)
            card_px = round(gui.BUBBLE_WIDTH_DP * pet.density)
            self.assertTrue(pet.left_tail.visible)
            self.assertEqual(pet.bubble_x + card_px + tail_px, pet.x)
            self.assertIn((37, "top"), pet.left_tail.margins)

            pet.x = 100
            self.assertTrue(pet._choose_bubble_side())
            self.assertTrue(pet.right_tail.visible)
            self.assertEqual(
                pet.bubble_x,
                pet.x + round((gui.PET_SIZE_DP + gui.BUBBLE_TAIL_WIDTH_DP) * pet.density),
            )
            self.assertTrue(pet.left_tail.image.startswith(b"\x89PNG"))
            self.assertTrue(pet.right_tail.image.startswith(b"\x89PNG"))
            self.assertNotEqual(pet.left_tail.image, pet.right_tail.image)


if __name__ == "__main__":
    unittest.main()
