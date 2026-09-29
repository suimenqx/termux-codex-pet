"""Touch payloads produced by Termux:GUI's JSON binding."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

import termuxgui as tg

from codex_pet.gui import OverlayUI


class PetView:
    aid = 1

    def __init__(self) -> None:
        self.positions: list[tuple[int, int]] = []

    def setposition(self, x: int, y: int) -> None:
        self.positions.append((x, y))


def touch(action: str, x: int, y: int) -> SimpleNamespace:
    return SimpleNamespace(
        type=tg.Event.overlaytouch,
        value={"action": action, "x": x, "y": y},
    )


class GuiTouchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ui = OverlayUI.__new__(OverlayUI)
        self.ui.pet = PetView()
        self.ui.root = SimpleNamespace(id=2)
        self.ui.bubble = None
        self.ui.x, self.ui.y = 700, 420
        self.ui.density = 3.0
        self.ui.down = None
        self.ui.dragged = False
        self.ui.expanded = False
        self.ui.manual_expand = False
        self.ui.touch_count = 0
        self.ui.last_touch = ""
        self.saved: list[tuple[int, int]] = []
        self.ui._save_position = lambda: self.saved.append((self.ui.x, self.ui.y))
        self.ui._position_bubble = lambda: None
        self.ui._set_bubble = lambda show: setattr(self.ui, "expanded", show)

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


if __name__ == "__main__":
    unittest.main()
