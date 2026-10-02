"""Touch behavior for the icon-only Termux:GUI overlay."""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import json
from codex_pet.gui import GuiWorker
from codex_pet.touch import DragController
import unittest

import termuxgui as tg

from codex_pet.renderer.termux_gui import TermuxGuiRenderer as OverlayUI


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
        self.ui.image_width = self.ui.image_height = 256
        self.ui.display_px = (192, 192)
        self.ui.touch_count = 0
        self.ui.last_touch = ""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = Path(self.directory.name) / 'config.json'
        self.worker = GuiWorker(self.config, lambda: {}, lambda *_: None)
        self.addCleanup(self.worker.stop)
        self.worker.ui = self.ui
        self.worker.drag = DragController((700,420), 3)

    @property
    def saved(self):
        if not self.config.exists():
            return []
        data = json.loads(self.config.read_text()).get('position')
        return [(data['x'], data['y'])] if data else []

    def handle(self, event):
        normalized = self.ui.input(event)
        if normalized is not None:
            self.worker.handle_input(normalized)
        return False

    def face_down(self, x: int, y: int, pointers: list | None = None) -> None:
        self.handle(touch("down", x, y))
        value = {"aid": 1, "id": self.ui.face.id, "action": "down"}
        if pointers is not None:
            value["pointers"] = pointers
        self.handle(SimpleNamespace(type=tg.Event.touch, value=value))

    def test_tap_has_no_action(self) -> None:
        self.face_down(730, 460)
        self.assertFalse(self.handle(touch("up", 730, 460)))

        self.assertEqual(self.ui.pet.positions, [])
        self.assertEqual(self.saved, [])

    def test_overlay_touch_alone_can_start_drag(self) -> None:
        self.handle(touch("down", 790, 510))
        self.handle(touch("move", 830, 540))
        self.handle(touch("up", 830, 540))
        self.assertEqual(self.saved, [(740, 450)])

    def test_events_for_another_overlay_are_ignored(self) -> None:
        self.handle(touch("down", 790, 510, aid=2))
        self.handle(SimpleNamespace(type=tg.Event.touch, value={
            "aid": 1, "id": self.ui.face.id, "action": "down",
        }))
        self.assertFalse(self.handle(touch("up", 850, 560, aid=2)))
        self.assertEqual(self.ui.touch_count, 0)
        self.assertEqual(self.ui.pet.positions, [])

    def test_overlay_touch_without_activity_id_is_supported(self) -> None:
        self.face_down(790, 510)
        self.handle(touch("move", 830, 540, aid=None))
        self.handle(touch("up", 830, 540, aid=None))
        self.assertEqual(self.saved, [(740, 450)])

    def test_view_down_before_overlay_down_still_starts_drag(self) -> None:
        # Android reports the targeted View touch and overlay-wide touch via
        # separate event paths; either one can reach the GUI worker first.
        self.handle(SimpleNamespace(type=tg.Event.touch, value={
            "aid": 1, "id": self.ui.face.id, "action": "down",
        }))
        self.handle(touch("down", 790, 510))
        self.handle(touch("move", 830, 540))
        self.handle(touch("up", 830, 540))

        self.assertEqual(self.saved, [(740, 450)])

    def test_drag_moves_and_saves_position(self) -> None:
        self.face_down(790, 510)
        self.handle(touch("move", 830, 540))
        self.handle(touch("move", 840, 550))
        self.handle(touch("up", 840, 550))

        self.assertEqual(self.ui.pet.positions, [(740, 450), (750, 460)])
        self.assertEqual(self.saved, [(750, 460)])
        self.assertEqual(self.ui.last_touch, "up")

    def test_nested_image_pointer_keeps_grab_aligned_after_window_clamp(self) -> None:
        self.face_down(500, 460, pointers=[[{"x": 80, "y": 128, "id": 0}]])
        self.handle(touch("move", 550, 500))
        self.handle(touch("up", 550, 500))
        self.assertEqual(self.saved, [(490, 404)])

    def test_drag_can_start_near_the_edge_of_the_icon(self) -> None:
        self.face_down(710, 430)
        self.handle(touch("move", 760, 480))
        self.handle(touch("up", 760, 480))
        self.assertEqual(self.saved, [(750, 470)])
        self.assertEqual(self.ui.pet.positions[-1], (750, 470))

    def test_movement_between_six_and_twelve_dp_starts_drag(self) -> None:
        self.face_down(790, 510)
        self.handle(touch("move", 814, 528))
        self.handle(touch("up", 814, 528))
        self.assertEqual(self.saved, [(724, 438)])
        self.assertEqual(self.ui.pet.positions[-1], (724, 438))

    def test_movement_below_six_dp_does_not_move_or_save(self) -> None:
        self.face_down(790, 510)
        self.handle(touch("move", 799, 519))
        self.handle(touch("up", 799, 519))
        self.assertEqual(self.saved, [])
        self.assertEqual(self.ui.pet.positions, [])

    def test_cancelled_drag_returns_to_its_start_without_saving(self) -> None:
        self.face_down(790, 510)
        self.handle(touch("move", 840, 550))
        self.handle(touch("cancel", 840, 550))
        self.assertEqual(self.saved, [])
        self.assertEqual((self.ui.x, self.ui.y), (700, 420))
        self.assertEqual(self.ui.pet.positions[-1], (700, 420))

    def test_targeted_cancel_without_coordinates_restores_start(self):
        self.face_down(790, 510)
        self.handle(touch("move", 840, 550))
        self.handle(SimpleNamespace(type=tg.Event.touch, value={
            "aid":1, "id":5, "action":"cancel"}))
        self.assertEqual((self.ui.x, self.ui.y), (700,420))
        self.assertEqual(self.saved, [])

    def test_early_targeted_anchor_uses_both_source_dimensions(self):
        self.ui.image_width, self.ui.image_height = 384, 416
        self.handle(SimpleNamespace(type=tg.Event.touch, value={
            "aid":1, "id":5, "action":"down", "pointers":[[{"x":192,"y":104}]]}))
        self.handle(touch('down', 500,460))
        self.handle(touch('move', 550,500))
        self.handle(touch('up', 550,500))
        self.assertEqual(self.saved, [(454,452)])

    def test_screen_off_cancels_unfinished_drag(self):
        self.face_down(790,510)
        self.handle(touch('move',840,550))
        self.handle(SimpleNamespace(type=tg.Event.screen_off, value={}))
        self.assertEqual((self.ui.x,self.ui.y), (700,420))
        self.assertEqual(self.saved, [])

    def test_secondary_pointer_does_not_replace_the_original_grab(self):
        self.face_down(790,510)
        self.handle(touch('pointer_down',300,200))
        self.handle(touch('move',830,540))
        self.handle(touch('pointer_up',300,200))
        self.handle(touch('up',830,540))
        self.assertEqual(self.saved, [(740,450)])

    def test_drag_saves_only_the_pet_position_configuration(self):
        self.config.write_text(json.dumps({'appearance':'robot','unrelated':True}))
        self.face_down(790,510)
        self.handle(touch('move',830,540))
        self.handle(touch('up',830,540))
        self.assertEqual(json.loads(self.config.read_text()),
                         {'appearance':'robot','unrelated':True,'position':{'x':740,'y':450}})


if __name__ == "__main__":
    unittest.main()
