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
        self.texts: list[str] = []

    def setposition(self, x: int, y: int) -> None:
        self.positions.append((x, y))

    def setvisibility(self, value: int) -> None:
        self.visibility.append(value)

    def setmargin(self, value: int, side: str) -> None:
        self.margins.append((value, side))

    def settext(self, value: str) -> None:
        self.texts.append(value)

    def settextcolor(self, value: int) -> None:
        pass


def touch(action: str, x: int, y: int, aid: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        type=tg.Event.overlaytouch,
        value={"aid": aid, "action": action, "x": x, "y": y},
    )


class GuiTouchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ui = OverlayUI.__new__(OverlayUI)
        self.ui.pet = PetView()
        self.ui.pet.aid = 1
        self.ui.bubble_overlay = PetView()
        self.ui.bubble_overlay.aid = 2
        self.ui.face = PetView(5)
        self.ui.face.setimage = lambda data: None
        self.ui.root = SimpleNamespace(id=2)
        self.ui.detail_left = PetView(3)
        self.ui.detail_right = PetView(4)
        self.ui.left_tail = PetView(12)
        self.ui.right_tail = PetView(13)
        self.ui.detail_left_fields = (PetView(6), PetView(7), PetView(8))
        self.ui.detail_right_fields = (PetView(9), PetView(10), PetView(11))
        self.ui.bubble = None
        self.ui.detail_fields = None
        self.ui.detail_content = None
        self.ui.detail_state = ""
        self.ui.detail_has_message = False
        self.ui.last_state = "idle"
        self.ui.x, self.ui.y = 700, 420
        self.ui.density = 3.0
        self.ui.bubble_width_px = 0
        self.ui.pending_down = None
        self.ui.down = None
        self.ui.dragged = False
        self.ui.drag_enabled = False
        self.ui.expanded = False
        self.ui.manual_expand = False
        self.ui.touch_count = 0
        self.ui.last_touch = ""
        self.saved: list[tuple[int, int]] = []
        self.ui._save_position = lambda: self.saved.append((self.ui.x, self.ui.y))
        self.ui._position_bubble = lambda: None
        def set_bubble(show: bool) -> None:
            self.ui.expanded = show
            self.ui.bubble = self.ui.detail_left if show else None
            self.ui.detail_fields = self.ui.detail_left_fields if show else None
            self.ui.detail_content = None
            self.ui.detail_state = ""
        self.ui._set_bubble = set_bubble

    def render(self, state: str) -> None:
        self.ui.render({"state": state, "working_count": 0,
                        "project": "repo", "elapsed": 0, "message": ""})

    def face_down(self, x: int, y: int) -> None:
        self.ui.handle(touch("down", x, y))
        self.ui.handle(SimpleNamespace(
            type=tg.Event.touch,
            value={"aid": 1, "id": self.ui.face.id, "action": "down"},
        ))

    def test_tap_opens_and_closes_details(self) -> None:
        self.face_down(730, 460)
        self.ui.handle(touch("move", 750, 475))
        self.assertTrue(self.ui.handle(touch("up", 750, 475)))
        self.assertTrue(self.ui.expanded)
        self.assertEqual(self.ui.pet.positions, [])
        self.face_down(730, 460)
        self.assertTrue(self.ui.handle(touch("up", 730, 460)))
        self.assertFalse(self.ui.expanded)

    def test_toggling_bubble_keeps_robot_window_stationary(self) -> None:
        self.ui._set_bubble = OverlayUI._set_bubble.__get__(self.ui)
        self.ui._choose_bubble_side = OverlayUI._choose_bubble_side.__get__(self.ui)
        self.ui._position_bubble = OverlayUI._position_bubble.__get__(self.ui)
        for expanded in (True, False, True):
            self.face_down(730, 460)
            self.assertTrue(self.ui.handle(touch("up", 730, 460)))
            self.assertEqual(self.ui.expanded, expanded)
            self.assertEqual(self.ui.pet.positions, [])

    def test_face_tap_survives_android_overlay_coordinate_shift(self) -> None:
        self.face_down(500, 460)
        self.assertTrue(self.ui.handle(touch("up", 500, 460)))
        self.assertTrue(self.ui.expanded)

    def test_taps_after_drag_keep_pet_position_when_touch_coordinates_shift(self) -> None:
        self.ui._set_bubble = OverlayUI._set_bubble.__get__(self.ui)
        self.ui._choose_bubble_side = OverlayUI._choose_bubble_side.__get__(self.ui)
        self.ui._position_bubble = OverlayUI._position_bubble.__get__(self.ui)
        self.face_down(790, 510)
        self.ui.handle(touch("move", 830, 540))
        self.ui.handle(touch("up", 830, 540))
        self.assertEqual((self.ui.x, self.ui.y), (740, 450))

        for expanded in (True, False, True):
            self.ui.handle(touch("down", 790, 490))
            self.ui.handle(SimpleNamespace(type=tg.Event.touch, value={
                "aid": 1, "id": self.ui.face.id, "action": "down",
                "pointers": [[{"x": 20, "y": 32, "id": 0}]],
            }))
            self.assertTrue(self.ui.handle(touch("up", 790, 490)))
            self.assertEqual(self.ui.expanded, expanded)
            self.assertEqual((self.ui.x, self.ui.y), (740, 450))
            self.assertEqual(self.ui.pet.positions, [(740, 450)])
            if expanded:
                self.assertEqual(self.ui.bubble_overlay.positions[-1], (377, 450))
        self.assertEqual(self.saved, [(740, 450)])

    def test_nested_image_pointer_keeps_grab_aligned_after_window_clamp(self) -> None:
        self.ui.handle(touch("down", 500, 460))
        self.ui.handle(SimpleNamespace(type=tg.Event.touch, value={
            "aid": 1, "id": self.ui.face.id, "action": "down",
            "pointers": [[{"x": 20, "y": 32, "id": 0}]],
        }))
        self.ui.handle(touch("move", 550, 500))
        self.ui.handle(touch("up", 550, 500))
        self.assertEqual(self.saved, [(490, 404)])

    def test_overlay_touch_without_face_touch_does_not_activate_pet(self) -> None:
        self.ui.handle(touch("down", 730, 460))
        self.assertFalse(self.ui.handle(touch("up", 730, 460)))
        self.assertFalse(self.ui.expanded)
        self.assertEqual(self.saved, [])

    def test_pet_overlay_touch_without_activity_id_still_toggles_bubble(self) -> None:
        self.ui.handle(SimpleNamespace(type=tg.Event.overlaytouch,
                                       value={"action": "down", "x": 730, "y": 460}))
        self.ui.handle(SimpleNamespace(type=tg.Event.touch,
                                       value={"aid": 1, "id": self.ui.face.id,
                                              "action": "down"}))
        self.assertTrue(self.ui.handle(SimpleNamespace(
            type=tg.Event.overlaytouch,
            value={"action": "up", "x": 730, "y": 460},
        )))
        self.assertTrue(self.ui.expanded)

    def test_drag_moves_and_saves_position(self) -> None:
        self.face_down(790, 510)
        self.ui.handle(touch("move", 830, 540))
        self.ui.handle(touch("move", 840, 550))
        self.ui.handle(touch("up", 840, 550))
        self.assertEqual(self.ui.pet.positions, [(740, 450), (750, 460)])
        self.assertEqual(self.saved, [(750, 460)])
        self.assertFalse(self.ui.expanded)
        self.assertEqual(self.ui.last_touch, "up")

    def test_drag_with_open_bubble_moves_both_windows(self) -> None:
        self.ui._set_bubble = OverlayUI._set_bubble.__get__(self.ui)
        self.ui._choose_bubble_side = OverlayUI._choose_bubble_side.__get__(self.ui)
        self.ui._position_bubble = OverlayUI._position_bubble.__get__(self.ui)
        self.ui._set_bubble(True)
        self.face_down(790, 510)
        self.ui.handle(touch("move", 830, 540))
        self.ui.handle(touch("up", 830, 540))
        self.assertEqual(self.ui.pet.positions, [(740, 450)])
        self.assertEqual(self.ui.bubble_overlay.positions[-1], (377, 450))
        self.assertEqual(self.saved, [(740, 450)])

    def test_center_grab_keeps_the_contact_point_while_moving(self) -> None:
        self.face_down(760, 480)
        self.ui.handle(touch("move", 810, 530))
        self.ui.handle(touch("up", 810, 530))
        self.assertEqual(self.saved, [(750, 470)])

    def test_outer_image_touch_cannot_start_a_drag(self) -> None:
        self.face_down(710, 430)
        self.ui.handle(touch("move", 760, 480))
        self.ui.handle(touch("up", 760, 480))
        self.assertEqual(self.saved, [])
        self.assertEqual(self.ui.pet.positions, [])

    def test_drag_can_start_near_the_edge_of_the_robot_face(self) -> None:
        self.face_down(874, 516)  # 26 dp from center, inside the enlarged grab zone.
        self.ui.handle(touch("move", 916, 516))
        self.ui.handle(touch("up", 916, 516))
        self.assertEqual(self.saved, [(742, 420)])

    def test_cancelled_drag_returns_to_its_start_without_saving(self) -> None:
        self.ui.handle(touch("down", 790, 510))
        self.ui.handle(SimpleNamespace(type=tg.Event.touch, value={
            "aid": 1, "id": self.ui.face.id, "action": "down",
            "pointers": [[{"x": 20, "y": 32, "id": 0}]],
        }))
        self.ui.handle(touch("move", 840, 550))
        self.ui.handle(touch("cancel", 840, 550))
        self.assertEqual(self.saved, [])
        self.assertEqual((self.ui.x, self.ui.y), (700, 420))
        self.assertEqual(self.ui.pet.positions[-1], (700, 420))

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
        self.ui.handle(SimpleNamespace(type=tg.Event.touch,
                                       value={"aid": 2, "id": 3}))
        self.render("idle")
        self.assertTrue(self.ui.expanded)
        self.face_down(730, 460)
        self.ui.handle(touch("up", 730, 460))
        self.assertFalse(self.ui.expanded)

    def test_touching_card_text_keeps_auto_detail_open(self) -> None:
        self.render("done")
        self.ui.handle(SimpleNamespace(
            type=tg.Event.touch,
            value={"aid": 2, "id": self.ui.detail_left_fields[1].id,
                   "action": "down"},
        ))
        self.render("idle")
        self.assertTrue(self.ui.expanded)

    def test_touching_speech_tail_keeps_auto_detail_open(self) -> None:
        self.render("done")
        self.ui.handle(SimpleNamespace(
            type=tg.Event.touch,
            value={"aid": 2, "id": self.ui.left_tail.id, "action": "down"},
        ))
        self.render("idle")
        self.assertTrue(self.ui.expanded)

    def test_manual_dismissal_does_not_reopen_same_approval(self) -> None:
        self.render("approval")
        self.face_down(730, 460)
        self.ui.handle(touch("up", 730, 460))
        self.render("approval")
        self.assertFalse(self.ui.expanded)

    def test_bubble_switches_sides_near_left_edge(self) -> None:
        self.ui._position_bubble = OverlayUI._position_bubble.__get__(self.ui)
        self.ui.bubble_width_px = 363  # 121 dp card and tail at 3x density
        self.ui.detail_has_message = True
        self.ui.bubble = self.ui.detail_left
        self.ui.x, self.ui.y = 1000, 500
        self.ui._position_bubble()
        self.assertEqual(self.ui.bubble_overlay.positions[-1], (637, 464))
        self.assertEqual((self.ui.bubble_x, self.ui.bubble_y), (637, 464))
        self.ui.bubble = self.ui.detail_right
        self.ui.x, self.ui.y = 100, 10
        self.ui._position_bubble()
        self.assertEqual(self.ui.bubble_overlay.positions[-1], (292, 1))
        self.assertEqual((self.ui.bubble_x, self.ui.bubble_y), (307, 1))
        self.assertEqual(self.ui.pet.positions, [])

    def test_detail_touch_does_not_move_pet(self) -> None:
        self.ui.x, self.ui.y = 100, 10
        self.ui.bubble = self.ui.detail_right
        self.ui.expanded = True
        self.ui.handle(touch("down", 330, 40, aid=2))
        self.ui.handle(touch("move", 370, 80, aid=2))
        self.ui.handle(touch("up", 370, 80, aid=2))
        self.assertEqual((self.ui.x, self.ui.y), (100, 10))
        self.assertEqual(self.saved, [])

    def test_detail_touch_over_old_pet_coordinates_does_not_close_it(self) -> None:
        self.ui.bubble = self.ui.detail_left
        self.ui.expanded = True
        self.ui.detail_left.id = self.ui.face.id
        self.ui.handle(touch("down", 730, 460))
        self.ui.handle(SimpleNamespace(
            type=tg.Event.touch,
            value={"aid": 2, "id": self.ui.detail_left.id, "action": "down"},
        ))
        self.assertTrue(self.ui.manual_expand)
        self.assertFalse(self.ui.handle(touch("up", 730, 460)))
        self.assertTrue(self.ui.expanded)

    def test_detail_uses_separate_overlay_without_moving_pet(self) -> None:
        self.ui._set_bubble = OverlayUI._set_bubble.__get__(self.ui)
        self.ui._choose_bubble_side = OverlayUI._choose_bubble_side.__get__(self.ui)
        self.ui._position_bubble = OverlayUI._position_bubble.__get__(self.ui)
        self.ui.x, self.ui.y = 700, 420
        self.ui._set_bubble(True)
        self.assertIs(self.ui.bubble, self.ui.detail_left)
        self.assertEqual(self.ui.bubble_overlay.positions[-1], (337, 420))
        self.assertEqual((self.ui.x, self.ui.y), (700, 420))
        self.ui._set_bubble(False)
        self.assertEqual(self.ui.pet.positions, [])
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
        self.assertEqual(self.ui.bubble_overlay.positions[-1], (292, 420))
        self.assertEqual(self.ui.bubble_x, 307)

    def test_detail_render_does_not_query_native_dimensions(self) -> None:
        self.ui.bubble = SimpleNamespace(id=3)
        self.ui.expanded = True
        self.ui.manual_expand = True

        def unavailable_dimensions() -> tuple[int, int]:
            raise RuntimeError("native layout query is unavailable")

        self.ui.detail_fields = self.ui.detail_left_fields
        for field in self.ui.detail_fields:
            field.getdimensions = unavailable_dimensions
        self.render("idle")
        self.assertEqual(self.ui.detail_fields[0].texts, ["repo"])
        time.sleep(0.17)
        self.render("idle")
        self.assertEqual(self.ui.detail_fields[0].texts, ["repo"])


if __name__ == "__main__":
    unittest.main()
