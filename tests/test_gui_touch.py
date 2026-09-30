"""Touch behavior for the icon-only Termux:GUI overlay."""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import termuxgui as tg

from codex_pet.gui import OverlayUI


class PetView:
    def __init__(self, view_id: int = 1) -> None:
        self.id = view_id
        self.positions: list[tuple[int, int]] = []
        self.images: list[bytes] = []

    def setposition(self, x: int, y: int) -> None:
        self.positions.append((x, y))

    def setimage(self, image: bytes) -> None:
        self.images.append(image)


def touch(action: str, x: int, y: int, aid: int | None = 1) -> SimpleNamespace:
    value = {"action": action, "x": x, "y": y}
    if aid is not None:
        value["aid"] = aid
    return SimpleNamespace(type=tg.Event.overlaytouch, value=value)


class GuiTouchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ui = OverlayUI.__new__(OverlayUI)
        self.ui.pet = PetView()
        self.ui.pet.aid = 1
        self.ui.face = PetView(5)
        self.ui.x, self.ui.y = 700, 420
        self.ui.density = 3.0
        self.ui.image_size_px = 256
        self.ui.down = None
        self.ui.dragged = False
        self.ui.touch_count = 0
        self.ui.last_touch = ""
        self.saved: list[tuple[int, int]] = []
        self.ui._save_position = lambda: self.saved.append((self.ui.x, self.ui.y))

    def face_down(self, x: int, y: int, pointers: list | None = None) -> None:
        self.ui.handle(touch("down", x, y))
        value = {"aid": 1, "id": self.ui.face.id, "action": "down"}
        if pointers is not None:
            value["pointers"] = pointers
        self.ui.handle(SimpleNamespace(type=tg.Event.touch, value=value))

    def test_tap_has_no_action(self) -> None:
        self.face_down(730, 460)
        self.assertFalse(self.ui.handle(touch("up", 730, 460)))

        self.assertEqual(self.ui.pet.positions, [])
        self.assertEqual(self.saved, [])

    def test_overlay_touch_alone_can_start_drag(self) -> None:
        self.ui.handle(touch("down", 790, 510))
        self.ui.handle(touch("move", 830, 540))
        self.ui.handle(touch("up", 830, 540))
        self.assertEqual(self.saved, [(740, 450)])

    def test_events_for_another_overlay_are_ignored(self) -> None:
        self.ui.handle(touch("down", 790, 510, aid=2))
        self.ui.handle(SimpleNamespace(type=tg.Event.touch, value={
            "aid": 1, "id": self.ui.face.id, "action": "down",
        }))
        self.assertFalse(self.ui.handle(touch("up", 850, 560, aid=2)))
        self.assertEqual(self.ui.touch_count, 0)
        self.assertEqual(self.ui.pet.positions, [])

    def test_overlay_touch_without_activity_id_is_supported(self) -> None:
        self.face_down(790, 510)
        self.ui.handle(touch("move", 830, 540, aid=None))
        self.ui.handle(touch("up", 830, 540, aid=None))
        self.assertEqual(self.saved, [(740, 450)])

    def test_view_down_before_overlay_down_still_starts_drag(self) -> None:
        # Android reports the targeted View touch and overlay-wide touch via
        # separate event paths; either one can reach the GUI worker first.
        self.ui.handle(SimpleNamespace(type=tg.Event.touch, value={
            "aid": 1, "id": self.ui.face.id, "action": "down",
        }))
        self.ui.handle(touch("down", 790, 510))
        self.ui.handle(touch("move", 830, 540))
        self.ui.handle(touch("up", 830, 540))

        self.assertEqual(self.saved, [(740, 450)])

    def test_drag_moves_and_saves_position(self) -> None:
        self.face_down(790, 510)
        self.ui.handle(touch("move", 830, 540))
        self.ui.handle(touch("move", 840, 550))
        self.ui.handle(touch("up", 840, 550))

        self.assertEqual(self.ui.pet.positions, [(740, 450), (750, 460)])
        self.assertEqual(self.saved, [(750, 460)])
        self.assertEqual(self.ui.last_touch, "up")

    def test_nested_image_pointer_keeps_grab_aligned_after_window_clamp(self) -> None:
        self.face_down(500, 460, pointers=[[{"x": 80, "y": 128, "id": 0}]])
        self.ui.handle(touch("move", 550, 500))
        self.ui.handle(touch("up", 550, 500))
        self.assertEqual(self.saved, [(490, 404)])

    def test_drag_can_start_near_the_edge_of_the_icon(self) -> None:
        self.face_down(710, 430)
        self.ui.handle(touch("move", 760, 480))
        self.ui.handle(touch("up", 760, 480))
        self.assertEqual(self.saved, [(750, 470)])
        self.assertEqual(self.ui.pet.positions[-1], (750, 470))

    def test_movement_between_six_and_twelve_dp_starts_drag(self) -> None:
        self.face_down(790, 510)
        self.ui.handle(touch("move", 814, 528))
        self.ui.handle(touch("up", 814, 528))
        self.assertEqual(self.saved, [(724, 438)])
        self.assertEqual(self.ui.pet.positions[-1], (724, 438))

    def test_movement_below_six_dp_does_not_move_or_save(self) -> None:
        self.face_down(790, 510)
        self.ui.handle(touch("move", 799, 519))
        self.ui.handle(touch("up", 799, 519))
        self.assertEqual(self.saved, [])
        self.assertEqual(self.ui.pet.positions, [])

    def test_cancelled_drag_returns_to_its_start_without_saving(self) -> None:
        self.face_down(790, 510)
        self.ui.handle(touch("move", 840, 550))
        self.ui.handle(touch("cancel", 840, 550))
        self.assertEqual(self.saved, [])
        self.assertEqual((self.ui.x, self.ui.y), (700, 420))
        self.assertEqual(self.ui.pet.positions[-1], (700, 420))

    def test_drag_saves_only_the_pet_position_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.ui.config_path = Path(directory) / "config.json"
            self.ui._save_position = OverlayUI._save_position.__get__(self.ui)
            self.face_down(790, 510)
            self.ui.handle(touch("move", 830, 540))
            self.ui.handle(touch("up", 830, 540))
            content = self.ui.config_path.read_text()

        self.assertIn('"x": 740', content)
        self.assertIn('"y": 450', content)


if __name__ == "__main__":
    unittest.main()
