"""Touch payloads produced by Termux:GUI's JSON binding."""

from __future__ import annotations

from types import SimpleNamespace
import time
import unittest

import termuxgui as tg

from codex_pet.gui import OverlayUI


class PetView:
    def __init__(self, id: int = 1) -> None:
        self.id = id
        self.positions: list[tuple[int, int]] = []
        self.visibility: list[int] = []
        self.margins: list[tuple[int, str]] = []

    def setposition(self, x: int, y: int) -> None:
        self.positions.append((x, y))

    def setvisibility(self, value: int) -> None:
        self.visibility.append(value)

    def setmargin(self, value: int, side: str) -> None:
        self.margins.append((value, side))


def touch(action: str, x: int, y: int) -> SimpleNamespace:
    return SimpleNamespace(
        type=tg.Event.overlaytouch,
        value={"action": action, "x": x, "y": y},
    )


class GuiTouchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ui = OverlayUI.__new__(OverlayUI)
        self.ui.pet = PetView()
        self.ui.face = PetView()
        self.ui.face.setimage = lambda data: None
        self.ui.root = SimpleNamespace(id=2)
        self.ui.detail_left = PetView(3)
        self.ui.detail_right = PetView(4)
        self.ui.bubble = None
        self.ui.detail = None
        self.ui.detail_content = ""
        self.ui.bubble_measure_due = None
        self.ui.last_state = "idle"
        self.ui.x, self.ui.y = 700, 420
        self.ui.density = 3.0
        self.ui.face_top_margin_dp = 0
        self.ui.bubble_width_px = 0
        self.ui.bubble_height_px = 0
        self.ui.down = None
        self.ui.dragged = False
        self.ui.expanded = False
        self.ui.manual_expand = False
        self.ui.touch_count = 0
        self.ui.last_touch = ""
        self.saved: list[tuple[int, int]] = []
        self.ui._save_position = lambda: self.saved.append((self.ui.x, self.ui.y))
        self.ui._position_bubble = lambda: None
        def set_bubble(show: bool) -> None:
            self.ui.expanded = show
            self.ui.bubble = SimpleNamespace(id=3) if show else None
        self.ui._set_bubble = set_bubble

    def render(self, state: str) -> None:
        self.ui.render({"state": state, "working_count": 0,
                        "project": "repo", "elapsed": 0, "message": ""})

    def test_tap_opens_and_closes_details(self) -> None:
        self.ui.handle(touch("down", 730, 460))
        self.ui.handle(touch("move", 750, 475))
        self.assertTrue(self.ui.handle(touch("up", 750, 475)))
        self.assertTrue(self.ui.expanded)
        self.assertEqual(self.ui.pet.positions, [])
        self.ui.handle(touch("down", 730, 460))
        self.assertTrue(self.ui.handle(touch("up", 730, 460)))
        self.assertFalse(self.ui.expanded)

    def test_drag_moves_and_saves_position(self) -> None:
        self.ui.handle(touch("down", 730, 460))
        self.ui.handle(touch("move", 770, 490))
        self.ui.handle(touch("move", 780, 500))
        self.ui.handle(touch("up", 780, 500))
        self.assertEqual(self.ui.pet.positions, [(740, 450), (750, 460)])
        self.assertEqual(self.saved, [(750, 460)])
        self.assertFalse(self.ui.expanded)
        self.assertEqual(self.ui.last_touch, "up")

    def test_auto_detail_closes_when_approval_resolves(self) -> None:
        self.render("approval")
        self.assertTrue(self.ui.expanded)
        self.render("working")
        self.assertFalse(self.ui.expanded)
        self.render("done")
        self.assertTrue(self.ui.expanded)
        self.render("idle")
        self.assertFalse(self.ui.expanded)

    def test_touching_auto_detail_keeps_it_open(self) -> None:
        self.render("done")
        self.ui.handle(SimpleNamespace(type=tg.Event.touch, value={"id": 3}))
        self.render("idle")
        self.assertTrue(self.ui.expanded)
        self.ui.handle(touch("down", 730, 460))
        self.ui.handle(touch("up", 730, 460))
        self.assertFalse(self.ui.expanded)

    def test_manual_dismissal_does_not_reopen_same_approval(self) -> None:
        self.render("approval")
        self.ui.handle(touch("down", 730, 460))
        self.ui.handle(touch("up", 730, 460))
        self.render("approval")
        self.assertFalse(self.ui.expanded)

    def test_bubble_switches_sides_near_left_edge(self) -> None:
        self.ui._position_bubble = OverlayUI._position_bubble.__get__(self.ui)
        self.ui.bubble_width_px = 588
        self.ui.bubble_height_px = 210
        self.ui.bubble = self.ui.detail_left
        self.ui.x, self.ui.y = 1000, 500
        self.ui._position_bubble()
        self.assertEqual(self.ui.pet.positions[-1], (388, 482))
        self.assertEqual((self.ui.bubble_x, self.ui.bubble_y), (388, 482))
        self.ui.bubble = self.ui.detail_right
        self.ui.x, self.ui.y = 100, 10
        self.ui._position_bubble()
        self.assertEqual(self.ui.pet.positions[-1], (100, 1))
        self.assertEqual((self.ui.bubble_x, self.ui.bubble_y), (316, 1))

    def test_detail_touch_does_not_move_pet(self) -> None:
        self.ui.x, self.ui.y = 100, 10
        self.ui.bubble = self.ui.detail_right
        self.ui.expanded = True
        self.ui.handle(touch("down", 330, 40))
        self.ui.handle(touch("move", 370, 80))
        self.ui.handle(touch("up", 370, 80))
        self.assertEqual((self.ui.x, self.ui.y), (100, 10))
        self.assertEqual(self.saved, [])

    def test_detail_uses_same_overlay_without_moving_pet(self) -> None:
        self.ui._set_bubble = OverlayUI._set_bubble.__get__(self.ui)
        self.ui._choose_bubble_side = OverlayUI._choose_bubble_side.__get__(self.ui)
        self.ui._position_bubble = OverlayUI._position_bubble.__get__(self.ui)
        self.ui.x, self.ui.y = 700, 420
        self.ui._set_bubble(True)
        self.assertIs(self.ui.bubble, self.ui.detail_left)
        self.assertEqual(self.ui.pet.positions[-1], (88, 420))
        self.assertEqual((self.ui.x, self.ui.y), (700, 420))
        self.ui._set_bubble(False)
        self.assertEqual(self.ui.pet.positions[-1], (700, 420))
        self.assertEqual(self.ui.detail_left.visibility,
                         [tg.View.VISIBLE, tg.View.GONE])

    def test_detail_switches_side_after_drag_release(self) -> None:
        self.ui._choose_bubble_side = OverlayUI._choose_bubble_side.__get__(self.ui)
        self.ui._position_bubble = OverlayUI._position_bubble.__get__(self.ui)
        self.ui.x, self.ui.y = 700, 420
        self.ui._choose_bubble_side()
        self.ui.x = 100
        self.assertTrue(self.ui._choose_bubble_side())
        self.assertIs(self.ui.bubble, self.ui.detail_right)
        self.assertEqual(self.ui.pet.positions[-1], (100, 420))
        self.assertEqual(self.ui.bubble_x, 316)

    def test_bubble_measures_after_text_layout(self) -> None:
        texts: list[str] = []
        self.ui.bubble = SimpleNamespace(id=3)
        self.ui.expanded = True
        self.ui.manual_expand = True
        self.ui.detail = SimpleNamespace(
            settext=texts.append,
            getdimensions=lambda: (637, 240),
        )
        self.ui.bubble_width_px = 637
        self.ui.bubble_height_px = 208
        self.render("idle")
        self.assertEqual(len(texts), 1)
        self.assertEqual(self.ui.bubble_height_px, 208)
        self.assertIsNotNone(self.ui.bubble_measure_due)
        self.ui.bubble_measure_due = time.monotonic() - 1
        self.render("idle")
        self.assertEqual(self.ui.bubble_height_px, 240)
        self.assertIsNone(self.ui.bubble_measure_due)


if __name__ == "__main__":
    unittest.main()
