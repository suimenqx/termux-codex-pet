"""Termux:GUI pixels, window and native input; no business snapshots."""
from __future__ import annotations
import logging
import math
import time
from typing import Any
import termuxgui as tg
from ..image_codec import encode_png
from .protocol import RgbaFrame, TouchInput
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
        point = float(value["x"]), float(value["y"])
        return point if all(math.isfinite(v) for v in point) else None
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
    def __init__(self, connection: Connection, position: tuple[int, int] = (700, 420)) -> None:
        self.c = connection
        self.x, self.y = position
        self.display_px = (192, 192)
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
        self.touch_count = 0
        self.last_touch = ""
        self._measure_density()

    def _measure_density(self) -> None:
        # The native layout size supplies density; getConfiguration is not
        # reliable for this overlay. A failed transaction discards the connection.
        deadline = time.monotonic() + 1.5
        timeout = self.c.timeout
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Overlay layout did not acquire dimensions')
                self.c.timeout = min(timeout, remaining)
                width, height = self.root.getdimensions()
                if width > 0 and height > 0:
                    self.display_px = width, height
                    self.density = width / PET_SIZE_DP
                    return
                time.sleep(min(.02, max(0, deadline - time.monotonic())))
        finally:
            self.c.timeout = timeout

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

    def input(self, event: tg.Event) -> TouchInput | None:
        if event.type == tg.Event.screen_off:
            return TouchInput('screen_off')
        if not isinstance(event.value, dict):
            return None
        value = event.value
        aid = value.get('aid')
        if aid is not None and aid != self.pet.aid:
            return None
        action = value.get('action')
        if event.type == tg.Event.touch:
            if value.get('id') != self.face.id:
                return None
            if action == 'cancel':
                return TouchInput('cancel')
            if action == 'down':
                local = _first_pointer(value.get('pointers'))
                if (local is not None and 0 <= local[0] <= self.image_width
                        and 0 <= local[1] <= self.image_height):
                    return TouchInput('anchor', (local[0] * self.display_px[0] / self.image_width,
                                                 local[1] * self.display_px[1] / self.image_height))
            return None
        if event.type == tg.Event.overlaytouch:
            self.touch_count += 1
            self.last_touch = str(action)
            if action in ('down', 'move', 'up', 'cancel'):
                return TouchInput(action, _point(value))
        return None

    def close(self) -> None:
        self.pet.finish()


