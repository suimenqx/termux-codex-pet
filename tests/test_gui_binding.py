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
    text_updates: list[str] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.id = FakeView.next_id
        FakeView.next_id += 1
        self.activity = args[0]
        self.touch_enabled = False
        self.visible = kwargs.get("visibility", gui.tg.View.VISIBLE) == gui.tg.View.VISIBLE
        self.image = b""
        self.margins: list[tuple[int, str]] = []
        self.dimensions: list[tuple[object, ...]] = []
        self.text_sizes: list[int] = []
        self.gravities: list[tuple[int, int]] = []

    def setdimensions(self, *args: object) -> None:
        self.dimensions.append(args)

    def setbackgroundcolor(self, *args: object) -> None:
        pass

    def settextsize(self, *args: object) -> None:
        self.text_sizes.extend(args)

    def setgravity(self, horizontal: int, vertical: int) -> None:
        self.gravities.append((horizontal, vertical))

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
        self.assertIs(pet.face.activity, pet.pet)
        self.assertIs(pet.detail_left.activity, pet.bubble_overlay)
        self.assertNotEqual(pet.pet.aid, pet.bubble_overlay.aid)

    def test_bubble_visibility_never_repositions_robot_activity(self) -> None:
        FakeView.next_id = 1
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(gui.tg, "LinearLayout", FakeView), \
             patch.object(gui.tg, "TextView", FakeView), \
             patch.object(gui.tg, "ImageView", FakeView):
            pet = gui.OverlayUI(connection, Path(directory) / "config.json")
            pet.render({"state": "needs_input", "running_count": 0,
                        "project": "repo", "elapsed": 0, "message": "Allow this action"})
            pet._set_bubble(False)

        robot_positions = [message for message in connection.messages
                           if message["method"] == "setPosition" and
                           message["params"]["aid"] == pet.pet.aid]
        bubble_positions = [message for message in connection.messages
                            if message["method"] == "setPosition" and
                            message["params"]["aid"] == pet.bubble_overlay.aid]
        self.assertEqual(len(robot_positions), 1)
        self.assertTrue(bubble_positions)

    def test_needs_input_card_has_project_status_and_summary(self) -> None:
        FakeView.next_id = 1
        FakeView.text_updates = []
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(gui.tg, "LinearLayout", FakeView), \
             patch.object(gui.tg, "TextView", FakeView), \
             patch.object(gui.tg, "ImageView", FakeView):
            pet = gui.OverlayUI(connection, Path(directory) / "config.json")
            pet.render({"state": "needs_input", "running_count": 0,
                        "project": "repo", "elapsed": 0,
                        "message": "Review this permission"})

        self.assertIn("repo", FakeView.text_updates)
        self.assertIn("Needs input", FakeView.text_updates)
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
            pet.render({"state": "needs_input", "running_count": 0,
                        "project": "repo", "elapsed": 0,
                        "message": "Allow this action"})
            tail_px = round(gui.BUBBLE_TAIL_WIDTH_DP * pet.density)
            card_px = round(gui.BUBBLE_WIDTH_DP * pet.density)
            self.assertTrue(pet.left_tail.visible)
            self.assertEqual(pet.bubble_x + card_px + tail_px, pet.x)
            self.assertIn((38, "top"), pet.left_tail.margins)

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

    def test_activity_card_is_compact_and_text_faces_the_pet(self) -> None:
        FakeView.next_id = 1
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(gui.tg, "LinearLayout", FakeView), \
             patch.object(gui.tg, "TextView", FakeView), \
             patch.object(gui.tg, "ImageView", FakeView):
            pet = gui.OverlayUI(connection, Path(directory) / "config.json")

        self.assertEqual(pet.detail_left.dimensions[0], (116, gui.tg.View.WRAP_CONTENT))
        self.assertEqual(pet.detail_right.dimensions[0], (116, gui.tg.View.WRAP_CONTENT))
        self.assertEqual(
            [message["params"]["padding"] for message in connection.messages
             if message["method"] == "setPadding"],
            [6, 6],
        )
        self.assertEqual(
            [field.gravities for field in pet.detail_left_fields],
            [[(2, 0)], [(2, 0)], [(2, 0)]],
        )
        self.assertEqual(
            [field.gravities for field in pet.detail_right_fields],
            [[(0, 0)], [(0, 0)], [(0, 0)]],
        )
        self.assertEqual([field.text_sizes for field in pet.detail_left_fields], [[11], [15], [11]])


if __name__ == "__main__":
    unittest.main()
