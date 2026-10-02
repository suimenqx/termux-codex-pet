"""Termux:GUI pixels, window and native input; no business snapshots."""
from __future__ import annotations
import logging
from pathlib import Path
import time
from typing import Any
import termuxgui as tg
from ..preferences import read_config, save_position
from ..image_codec import encode_png
from .protocol import RgbaFrame
from .transport import Connection

LOG = logging.getLogger(__name__)
PET_SIZE_DP = 64
DRAG_SLOP_DP = 6

def _overlay(connection: tg.Connection) -> tg.Activity:
    # termuxgui 0.1.6 unpacks (aid, tid), while overlays return only aid.
    aid = connection.send_read_msg({"method": "newActivity", "params": {"overlay": True}})
    if not isinstance(aid, int) or aid < 0:
        raise RuntimeError("Termux:GUI could not create overlay; check Display over other apps")
    activity = tg.Activity.__new__(tg.Activity)
    activity.c = connection
    activity.aid = aid
    activity.t = None
    return activity


def _point(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, dict):
        return None
    try:
        return float(value["x"]), float(value["y"])
    except (KeyError, TypeError, ValueError):
        return None


def _first_pointer(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, list) or not value:
        return None
    first = value[0]
    if isinstance(first, list):
        first = first[0] if first else None
    return _point(first)


class TermuxGuiRenderer:
    def __init__(self, connection: tg.Connection, config_path: Path) -> None:
        self.c = connection
        self.config_path = config_path
        self.x, self.y = self._load_position()
        self.density = 3.0
        self.pet = _overlay(connection)
        self.root = tg.LinearLayout(self.pet, vertical=False)
        self.root.setdimensions(tg.View.WRAP_CONTENT, tg.View.WRAP_CONTENT)
        self.root.setbackgroundcolor(0)
        self.face = tg.ImageView(self.pet, self.root)
        self.face.setdimensions(PET_SIZE_DP, PET_SIZE_DP)
        self.face.sendtouchevent(True)
        self.last_key: tuple | None = None
        self.image_width = self.image_height = 256
        self._encoded: dict[tuple, bytes] = {}
        self.root.sendtouchevent(True)
        self.pet.sendoverlayevents(True)
        self.pet.setposition(self.x, self.y)
        # Screen down, corrected drag anchor, original logical position.
        self.down: tuple[float, float, int, int, int, int] | None = None
        self.dragged = False
        self.touch_count = 0
        self.last_touch = ""
        self._measure_density()

    def _load_position(self) -> tuple[int, int]:
        try:
            pos = read_config(self.config_path).get("position", {})
            return max(0, int(pos["x"])), max(0, int(pos["y"]))
        except (KeyError, TypeError, ValueError):
            return 700, 420

    def _save_position(self) -> None:
        save_position(self.config_path, self.x, self.y)

    def _measure_density(self) -> None:
        # getConfiguration never replies for an overlay on this binding/device.
        # The measured native View provides the density without Android APIs.
        time.sleep(0.12)
        old_timeout = self.c._main.gettimeout()
        try:
            self.c._main.settimeout(1.5)
            width = self.root.getdimensions()[0]
            if width > 0:
                self.density = width / PET_SIZE_DP
        except (OSError, ValueError):
            LOG.warning("Could not measure overlay density; using 3.0")
        finally:
            self.c._main.settimeout(old_timeout)

    def present(self, frame: RgbaFrame) -> None:
        self.image_width, self.image_height = frame.width, frame.height
        if frame.key == self.last_key:
            return
        image = self._encoded.get(frame.key)
        if image is None:
            image = encode_png(frame.width, frame.height, frame.pixels)
            if len(self._encoded) >= 80:
                self._encoded.clear()
            self._encoded[frame.key] = image
        self.face.setimage(image)
        self.last_key = frame.key

    def move(self, x: int, y: int) -> None:
        self.pet.setposition(x, y)
        self.x, self.y = x, y

    def handle(self, event: tg.Event) -> bool:
        if not isinstance(event.value, dict):
            return False
        if event.type == tg.Event.touch:
            if (event.value.get("aid") == self.pet.aid and
                event.value.get("id") == self.face.id and
                event.value.get("action") == "down" and self.down is not None):
                local_px = _first_pointer(event.value.get("pointers"))
                if (local_px is not None and
                    0 <= local_px[0] <= self.image_width and
                    0 <= local_px[1] <= self.image_height):
                    # ImageView pointer coordinates use source-image pixels.
                    # Normalize them to the 64 dp view before correcting a
                    # system-clamped overlay position.
                    local_x = local_px[0] * PET_SIZE_DP / self.image_width
                    local_y = local_px[1] * PET_SIZE_DP / self.image_height
                    raw_x, raw_y, _, _, origin_x, origin_y = self.down
                    anchor_x = max(0, round(raw_x - local_x * self.density))
                    anchor_y = max(0, round(raw_y - local_y * self.density))
                    self.down = (raw_x, raw_y, anchor_x, anchor_y, origin_x, origin_y)
            return False
        if event.type != tg.Event.overlaytouch:
            return False
        # Termux:GUI may omit the Activity ID from overlay-wide touch events.
        aid = event.value.get("aid")
        if aid is not None and aid != self.pet.aid:
            return False
        self.touch_count += 1
        self.last_touch = str(event.value.get("action", ""))
        xy = _point(event.value)
        if xy is None:
            return False
        action = event.value.get("action")
        if action == "down":
            # overlayTouch is the gesture source. View touch events are only
            # an optional source of a more precise anchor near screen edges.
            # They arrive on a separate event path, so requiring both downs
            # makes drag behavior depend on event ordering.
            self.down = (xy[0], xy[1], self.x, self.y, self.x, self.y)
            self.dragged = False
        elif action == "move" and self.down is not None:
            dx, dy = xy[0] - self.down[0], xy[1] - self.down[1]
            slop = DRAG_SLOP_DP * self.density
            if dx * dx + dy * dy > slop * slop:
                self.dragged = True
            if self.dragged:
                self.x = max(0, self.down[2] + round(dx))
                self.y = max(0, self.down[3] + round(dy))
                self.pet.setposition(self.x, self.y)
        elif action in ("up", "cancel") and self.down is not None:
            if action == "cancel":
                if self.dragged:
                    self.x, self.y = self.down[4], self.down[5]
                    self.pet.setposition(self.x, self.y)
                self.down = None
                return False
            if self.dragged:
                self._save_position()
            self.down = None
        elif action in ("up", "cancel"):
            self.down = None
        return False

    def close(self) -> None:
        self.pet.finish()


