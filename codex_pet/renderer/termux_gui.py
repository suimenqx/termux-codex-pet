"""Termux:GUI pixels, window and native input; no business snapshots."""
from __future__ import annotations
import logging
import math
import time
from typing import Any
import termuxgui as tg
from ..image_codec import encode_png, premultiply
from ..frame_cache import FrameCache
from .protocol import RgbaFrame, TouchInput
from .transport import Connection
from .shared_buffer import SharedFramebuffer
from .policy import RendererPolicy
from ..image_contract import DISPLAY_DP

LOG = logging.getLogger(__name__)
PET_SIZE_DP = DISPLAY_DP[0]
DRAG_SLOP_DP = 6


class RebuildRenderer(Exception):
    """A new canvas must retire the entire old native resource group."""


class SharedFailure(ConnectionError):
    """A suspect connection must be discarded before PNG fallback."""


def _overlay(connection: tg.Connection) -> tg.Activity:
    # termuxgui 0.1.6 unpacks (aid, tid), while overlays return only aid.
    aid = connection.send_read_msg(
        {"method": "newActivity", "params": {"overlay": True}})
    if type(aid) is not int or aid < 0:
        raise RuntimeError(
            "Termux:GUI could not create overlay; check Display over other apps")
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
    def __init__(self, connection: Connection, position: tuple[int, int] = (700, 420),
                 *, cache: FrameCache | None = None, transport: str = "auto",
                 policy: RendererPolicy | None = None) -> None:
        if transport not in ('auto', 'png', 'shared'):
            raise ValueError('Unknown renderer transport')
        self.c = connection
        self.requested_transport = transport
        self.transport = 'pending'
        self.policy = policy if policy is not None else RendererPolicy.installed()
        self.policy_reason = 'starting'
        self.closed = False
        self._buffer: SharedFramebuffer | None = None
        self._attached = False
        self.plugin_version: int | None = None
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
        self.cache = cache if cache is not None else FrameCache()
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
                    raise TimeoutError(
                        'Overlay layout did not acquire dimensions')
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
        if self.closed:
            raise RuntimeError('Renderer is closed')
        if self.plugin_version is None:
            self.plugin_version = self.c.getversion()
        selected, reason = self.policy.choose(
            (frame.width, frame.height), self.plugin_version)
        if self.requested_transport != 'auto':
            selected, reason = self.requested_transport, 'explicit internal selection'
        if self.transport not in ('pending', selected):
            self.close()
            raise RebuildRenderer('Renderer transport changed')
        self.transport, self.policy_reason = selected, reason
        if self._buffer is not None and self._buffer.dimensions != (frame.width, frame.height):
            self.close()
            raise RebuildRenderer('Framebuffer dimensions changed')
        self.image_width, self.image_height = frame.width, frame.height
        if frame.key == self.last_key:
            return
        if self.transport == 'shared':
            try:
                self._present_shared(frame)
            except Exception as exc:
                self.close()
                raise SharedFailure(f'Shared transport failed: {exc}') from exc
        else:
            image = self.cache.get(('png', frame.key))
            if image is None:
                image = encode_png(frame.width, frame.height, frame.pixels)
                self.cache.put(('png', frame.key), image)
            self.face.setimage(image)
        self.last_key = frame.key

    def _present_shared(self, frame: RgbaFrame) -> None:
        if self.plugin_version != 7:
            raise ValueError(
                'No verified staging-consumption fence for this plugin version')
        if self._buffer is None:
            self._buffer = SharedFramebuffer(self.c, frame.width, frame.height)
        pixels = self.cache.get(('premult', frame.key))
        if pixels is None:
            pixels = premultiply(frame.width, frame.height, frame.pixels)
            self.cache.put(('premult', frame.key), pixels)
        self._buffer.write(pixels)
        self.c.send_msg(
            {'method': 'blitBuffer', 'params': {'bid': self._buffer.bid}})
        if not self._attached:
            self.face.setbuffer(self._buffer)
        self.face.refresh()
        # Verified APK 7 dispatches these operations serially. This confirms
        # staging consumption, not Android screen presentation. Never reuse
        # staging before this bounded response; flush/sleep are not fences.
        if self.c.getversion() != self.plugin_version:
            raise ValueError('Plugin version changed during presentation')
        self._attached = True

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
        if self.closed:
            return
        self.closed = True
        self.last_key = None
        try:
            self.pet.finish()
        except OSError:
            pass
        finally:
            try:
                self.c.close()
            finally:
                if self._buffer is not None:
                    self._buffer.close()
                    self._buffer = None
                self.cache.discard_encoding('png')
                self.cache.discard_encoding('premult')
