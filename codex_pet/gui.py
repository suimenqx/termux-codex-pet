"""Native Termux:GUI overlay. All GUI calls stay on the daemon's GUI thread."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
import select
import socket
import threading
import time
from typing import Any, Callable

import termuxgui as tg

from .animation import AnimationTimeline
from .art import icon
from .pets import DEFAULT_APPEARANCE, appearance_for
from .preferences import read_config, save_position
from .renderer.transport import Connection

LOG = logging.getLogger(__name__)
PET_SIZE_DP = 64
DRAG_SLOP_DP = 6
RECONNECT_DELAYS = (0.0, 5.0, 20.0, 60.0)


@dataclass(frozen=True)
class OverlayStatus:
    x: int
    y: int
    touch_count: int
    last_touch: str


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
        self.last_image: bytes | None = None
        self.image_size_px = appearance_for(DEFAULT_APPEARANCE).image_size_px
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
        appearance = appearance_for(snapshot.get("appearance", DEFAULT_APPEARANCE))
        self.image_size_px = appearance.image_size_px
        count = snapshot["running_count"]
        image = icon(state, frame, count, appearance.id)
        if image == self.last_image:
            return
        # PNG decoding premultiplies alpha before Android draws it. Termux:GUI's
        # raw shared-buffer copy does not, so straight-alpha PNG pixels sent as
        # RGBA there produce bright colored specks around transparent edges.
        self.face.setimage(image)
        self.last_image = image

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
        self.pet.finish()


class GuiWorker:
    def __init__(self, config_path: Path, snapshot: Callable[[], dict[str, Any]],
                 on_status: Callable[[bool, str], None]) -> None:
        self.config_path = config_path
        self.snapshot = snapshot
        self.on_status = on_status
        self.read_wake, self.write_wake = socket.socketpair()
        self.write_wake.setblocking(False)
        self.read_wake.setblocking(False)
        self.stopping = False
        self.thread = threading.Thread(target=self._run, name="codex-pet-gui", daemon=True)
        self.ui: OverlayUI | None = None
        self.overlay_status: OverlayStatus | None = None

    def start(self) -> None:
        self.thread.start()

    def wake(self) -> None:
        try:
            self.write_wake.send(b"x")
        except OSError:
            pass

    def _drain_wake(self) -> None:
        try:
            while self.read_wake.recv(4096):
                pass
        except BlockingIOError:
            pass

    def _publish_overlay(self) -> None:
        ui = self.ui
        self.overlay_status = (OverlayStatus(ui.x, ui.y, ui.touch_count, ui.last_touch)
                               if ui is not None else None)

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
            connection: Connection | None = None
            try:
                connection = Connection()
                self.ui = OverlayUI(connection, self.config_path)
                self._publish_overlay()
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
                    self.overlay_status = None
                if connection is not None:
                    connection.close()
            # Keep retrying a lost GUI connection at a low rate; a Codex event
            # wakes the worker immediately rather than waiting for the timer.
            if not self.stopping:
                delay = RECONNECT_DELAYS[min(max(0, failures - 1), len(RECONNECT_DELAYS) - 1)]
                readable, _, _ = select.select([self.read_wake], [], [], delay)
                if readable:
                    self._drain_wake()
                    failures = 0

    def _loop(self, connection: tg.Connection) -> None:
        assert self.ui is not None
        current = self.snapshot()
        appearance = current.get("appearance", DEFAULT_APPEARANCE)
        state = current["state"]
        timeline = AnimationTimeline(
            appearance, state, time.monotonic(), current.get("running_count", 0),
        )
        self.ui.render(current, timeline.frame)
        while not self.stopping:
            timeout = timeline.timeout(time.monotonic())
            readable, _, _ = select.select([connection._event, self.read_wake], [], [], timeout)
            if self.read_wake in readable:
                self._drain_wake()
                if self.stopping:
                    break
                self._refresh(timeline, time.monotonic())
            if connection._event in readable:
                if not connection._event.recv(1, socket.MSG_PEEK):
                    raise ConnectionError("Termux:GUI disconnected")
                event = connection.checkevent()
                if event is not None:
                    if self.ui.handle(event):
                        self._refresh(timeline, time.monotonic())
                    self._publish_overlay()
            now = time.monotonic()
            if timeline.due(now):
                self._refresh(timeline, now, advance=True)

    def _refresh(self, timeline: AnimationTimeline, now: float,
                 advance: bool = False) -> None:
        assert self.ui is not None
        current = self.snapshot()
        changed = timeline.sync(
            current.get("appearance", DEFAULT_APPEARANCE),
            current["state"], current.get("running_count", 0), now,
        )
        if advance and not changed:
            timeline.advance(now)
        self.ui.render(current, timeline.frame)
