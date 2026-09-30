"""Native Termux:GUI overlay. All GUI calls stay on the daemon's GUI thread."""

from __future__ import annotations

import logging
from pathlib import Path
import select
import socket
import threading
import time
from typing import Any, Callable

import termuxgui as tg

from .art import SIZE, AKITA_SIZE, advance_animation, animation_interval, icon, rgba_icon
from .pets import DEFAULT_APPEARANCE
from .preferences import read_config, save_position

LOG = logging.getLogger(__name__)
PET_SIZE_DP = 64
DRAG_SLOP_DP = 6
RECONNECT_DELAYS = (0.0, 5.0, 20.0, 60.0)


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


def _visual_key(snapshot: dict[str, Any]) -> tuple[Any, Any, int]:
    state = snapshot["state"]
    running_count = int(snapshot.get("running_count", 0)) if state == "running" else 0
    return snapshot.get("appearance", DEFAULT_APPEARANCE), state, running_count


class AnimationClock:
    """Keep frame changes on a monotonic schedule instead of render completion."""

    def __init__(self, appearance: str, state: str, frame: int, now: float) -> None:
        self.deadline: float | None = None
        self.reset(appearance, state, frame, now)

    def reset(self, appearance: str, state: str, frame: int, now: float) -> None:
        interval = animation_interval(appearance, state, frame)
        self.deadline = now + interval if interval is not None else None

    def timeout(self, now: float) -> float | None:
        if self.deadline is None:
            return None
        return max(0.0, self.deadline - now)

    def due(self, now: float) -> bool:
        return self.deadline is not None and now >= self.deadline

    def advance(self, appearance: str, state: str, frame: int, now: float) -> int:
        """Advance to the frame due now, skipping missed frames without a burst."""
        if not self.due(now):
            return frame

        assert self.deadline is not None
        next_deadline = self.deadline
        while True:
            frame = advance_animation(appearance, state, frame)
            interval = animation_interval(appearance, state, frame)
            if interval is None:
                self.deadline = None
                return frame

            next_deadline += interval
            if next_deadline > now:
                self.deadline = next_deadline
                return frame


class OverlayUI:
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
        self.image_size_px = AKITA_SIZE
        self.image_buffer: tg.Buffer | None = None
        self.buffer_bound = False
        self.buffer_unavailable = False
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

    def render(self, snapshot: dict[str, Any], frame: int = 0) -> None:
        state = snapshot["state"]
        appearance = snapshot.get("appearance", DEFAULT_APPEARANCE)
        self.image_size_px = SIZE if appearance == "robot" else AKITA_SIZE
        count = snapshot["running_count"]
        image = icon(state, frame, count, appearance)
        if appearance == "robot":
            self.buffer_bound = False
            self.face.setimage(image)
            return
        self._render_akita(state, frame, count, image)

    def _render_akita(self, state: str, frame: int, count: int, image: bytes) -> None:
        if not self.buffer_unavailable:
            if self.image_buffer is None:
                try:
                    self.image_buffer = tg.Buffer(self.c, AKITA_SIZE, AKITA_SIZE)
                except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
                    self.buffer_unavailable = True
                    LOG.warning("Termux:GUI shared image buffer unavailable; using PNG frames: %s", exc)
            if self.image_buffer is not None:
                try:
                    pixels = rgba_icon(state, frame, count)
                    if len(pixels) != len(self.image_buffer.mem):
                        raise ValueError("Termux:GUI shared image buffer has an unexpected size")
                    if not self.buffer_bound:
                        self.face.setbuffer(self.image_buffer)
                        self.buffer_bound = True
                    self.image_buffer.mem[:] = pixels
                    self.image_buffer.blit()
                    self.face.refresh()
                    return
                except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
                    self.buffer_unavailable = True
                    self.buffer_bound = False
                    LOG.warning("Termux:GUI shared image buffer failed; using PNG frames: %s", exc)
        self.face.setimage(image)

    def handle(self, event: tg.Event) -> bool:
        if not isinstance(event.value, dict):
            return False
        if event.type == tg.Event.touch:
            if (event.value.get("aid") == self.pet.aid and
                event.value.get("id") == self.face.id and
                event.value.get("action") == "down" and self.down is not None):
                local_px = _first_pointer(event.value.get("pointers"))
                if (local_px is not None and
                    0 <= local_px[0] <= self.image_size_px and
                    0 <= local_px[1] <= self.image_size_px):
                    # ImageView pointer coordinates use source-image pixels.
                    # Normalize them to the 64 dp view before correcting a
                    # system-clamped overlay position.
                    local_x = local_px[0] * PET_SIZE_DP / self.image_size_px
                    local_y = local_px[1] * PET_SIZE_DP / self.image_size_px
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
        try:
            if self.image_buffer is not None and self.buffer_bound:
                try:
                    self.face.setimage(icon("idle"))
                except OSError:
                    LOG.debug("Could not detach Pet image buffer before closing")
                self.buffer_bound = False
            self.pet.finish()
        finally:
            if self.image_buffer is not None:
                try:
                    self.image_buffer.remove()
                except (AttributeError, OSError, RuntimeError) as exc:
                    LOG.debug("Could not remove Pet image buffer: %s", exc)
                self.image_buffer = None


class GuiWorker:
    def __init__(self, config_path: Path, snapshot: Callable[[], dict[str, Any]],
                 on_status: Callable[[bool, str], None]) -> None:
        self.config_path = config_path
        self.snapshot = snapshot
        self.on_status = on_status
        self.read_wake, self.write_wake = socket.socketpair()
        self.stopping = False
        self.thread = threading.Thread(target=self._run, name="codex-pet-gui", daemon=True)
        self.ui: OverlayUI | None = None

    def start(self) -> None:
        self.thread.start()

    def wake(self) -> None:
        try:
            self.write_wake.send(b"x")
        except OSError:
            pass

    def stop(self) -> None:
        self.stopping = True
        self.wake()
        if self.thread.ident is not None:
            self.thread.join(timeout=8)
        self.read_wake.close()
        self.write_wake.close()

    def _run(self) -> None:
        failures = 0
        while not self.stopping:
            connection: tg.Connection | None = None
            try:
                connection = tg.Connection()
                connection._main.settimeout(4.0)
                self.ui = OverlayUI(connection, self.config_path)
                self.on_status(True, "")
                failures = 0
                self._loop(connection)
            except Exception as exc:
                failures += 1
                LOG.exception("Termux:GUI connection or overlay failed")
                self.on_status(False, str(exc)[:180])
            finally:
                if self.ui is not None:
                    try:
                        self.ui.close()
                    except OSError:
                        LOG.exception("Could not close overlay")
                    self.ui = None
                if connection is not None:
                    connection.close()
            # Keep retrying a lost GUI connection at a low rate; a Codex event
            # wakes the worker immediately rather than waiting for the timer.
            if not self.stopping:
                delay = RECONNECT_DELAYS[min(max(0, failures - 1), len(RECONNECT_DELAYS) - 1)]
                readable, _, _ = select.select([self.read_wake], [], [], delay)
                if readable:
                    self.read_wake.recv(4096)
                    failures = 0

    def _loop(self, connection: tg.Connection) -> None:
        assert self.ui is not None
        frame = 0
        current = self.snapshot()
        appearance = current.get("appearance", DEFAULT_APPEARANCE)
        state = current["state"]
        visual = _visual_key(current)
        self.ui.render(current, frame)
        clock = AnimationClock(appearance, state, frame, time.monotonic())
        while not self.stopping:
            timeout = clock.timeout(time.monotonic())
            readable, _, _ = select.select([connection._event, self.read_wake], [], [], timeout)
            if self.read_wake in readable:
                self.read_wake.recv(4096)
                if self.stopping:
                    break
                current = self.snapshot()
                appearance = current.get("appearance", DEFAULT_APPEARANCE)
                state = current["state"]
                next_visual = _visual_key(current)
                if next_visual != visual:
                    frame = 0
                    visual = next_visual
                    clock.reset(appearance, state, frame, time.monotonic())
                self.ui.render(current, frame)
            if connection._event in readable:
                if not connection._event.recv(1, socket.MSG_PEEK):
                    raise ConnectionError("Termux:GUI disconnected")
                event = connection.checkevent()
                if event is not None:
                    if self.ui.handle(event):
                        self.ui.render(self.snapshot(), frame)
            now = time.monotonic()
            if clock.due(now):
                current = self.snapshot()
                next_visual = _visual_key(current)
                if next_visual != visual:
                    appearance = current.get("appearance", DEFAULT_APPEARANCE)
                    state = current["state"]
                    visual = next_visual
                    frame = 0
                    clock.reset(appearance, state, frame, now)
                else:
                    frame = clock.advance(appearance, state, frame, now)
                self.ui.render(current, frame)
