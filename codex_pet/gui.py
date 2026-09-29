"""Native Termux:GUI overlay. All GUI calls stay on the daemon's GUI thread."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import select
import socket
import threading
import time
from typing import Any, Callable

import termuxgui as tg

from .art import icon

LOG = logging.getLogger(__name__)
PET_SIZE_DP = 64
BUBBLE_WIDTH_DP = 196
BUBBLE_GAP_DP = 8
MESSAGE_MARGIN_DP = 12
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
        self.detail_left = tg.TextView(self.pet, "", self.root, visibility=tg.View.GONE)
        self.face = tg.ImageView(self.pet, self.root)
        self.face.setdimensions(PET_SIZE_DP, PET_SIZE_DP)
        self.detail_right = tg.TextView(self.pet, "", self.root, visibility=tg.View.GONE)
        for detail, side in ((self.detail_left, "right"), (self.detail_right, "left")):
            detail.setdimensions(BUBBLE_WIDTH_DP, tg.View.WRAP_CONTENT)
            detail.settextsize(14)
            detail.settextcolor(0xFFFFFFFF)
            detail.setbackgroundcolor(0xE02A2A2A)
            detail.setmargin(BUBBLE_GAP_DP, side)
            # The binding has no setpadding method, but Termux:GUI supports it.
            self.c.send_msg({"method": "setPadding", "params": {
                "aid": self.pet.aid, "id": detail.id, "padding": 10,
            }})
            detail.sendtouchevent(True)
        self.face.sendtouchevent(True)
        self.root.sendtouchevent(True)
        self.pet.sendoverlayevents(True)
        self.pet.setposition(self.x, self.y)
        self.bubble: tg.TextView | None = None
        self.detail: tg.TextView | None = None
        self.bubble_width_px = 0
        self.bubble_x = 0
        self.bubble_y = 0
        self.detail_content = ""
        self.detail_has_message = False
        self.face_top_margin_dp = 0
        self.expanded = False
        self.manual_expand = False
        self.pending_down: tuple[float, float, float, int, int] | None = None
        self.down: tuple[float, float, float, int, int] | None = None
        self.dragged = False
        self.touch_count = 0
        self.last_touch = ""
        self.last_state = "idle"
        self._measure_density()

    def _load_position(self) -> tuple[int, int]:
        try:
            data = json.loads(self.config_path.read_text())
            pos = data.get("position", {})
            return max(0, int(pos["x"])), max(0, int(pos["y"]))
        except (FileNotFoundError, ValueError, KeyError, TypeError):
            return 700, 420

    def _save_position(self) -> None:
        self.config_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            data = json.loads(self.config_path.read_text())
            if not isinstance(data, dict):
                data = {}
        except (FileNotFoundError, ValueError):
            data = {}
        data["position"] = {"x": self.x, "y": self.y}
        temp = self.config_path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2) + "\n")
        temp.replace(self.config_path)

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

    def _set_bubble(self, show: bool) -> None:
        if show and not self.expanded:
            self.expanded = True
            self._choose_bubble_side()
        elif not show and self.expanded:
            assert self.bubble is not None
            self.bubble.setvisibility(tg.View.GONE)
            self.bubble = None
            self.detail = None
            self.detail_content = ""
            self.detail_has_message = False
            if self.face_top_margin_dp:
                self.face.setmargin(0, "top")
                self.face_top_margin_dp = 0
            self.pet.setposition(self.x, self.y)
            self.expanded = False

    def _choose_bubble_side(self) -> bool:
        width = self.bubble_width_px or int(BUBBLE_WIDTH_DP * self.density)
        gap = int(BUBBLE_GAP_DP * self.density)
        target = self.detail_left if self.x >= width + gap else self.detail_right
        if self.bubble is target:
            return False
        if self.bubble is not None:
            self.bubble.setvisibility(tg.View.GONE)
        target.setvisibility(tg.View.VISIBLE)
        self.bubble = target
        self.detail = target
        self.detail_content = ""
        self.bubble_width_px = int(BUBBLE_WIDTH_DP * self.density)
        self._position_bubble()
        return True

    def _position_bubble(self) -> None:
        if self.bubble is not None:
            gap = int(BUBBLE_GAP_DP * self.density)
            pet_size = int(PET_SIZE_DP * self.density)
            top_margin = min(MESSAGE_MARGIN_DP if self.detail_has_message else 0,
                             int(self.y / self.density))
            if top_margin != self.face_top_margin_dp:
                self.face.setmargin(top_margin, "top")
                self.face_top_margin_dp = top_margin
            window_y = self.y - int(top_margin * self.density)
            if self.bubble is self.detail_left:
                window_x = self.x - self.bubble_width_px - gap
                self.bubble_x = window_x
            else:
                window_x = self.x
                self.bubble_x = window_x + pet_size + gap
            self.bubble_y = window_y
            self.pet.setposition(window_x, window_y)

    def render(self, snapshot: dict[str, Any], frame: int = 0) -> None:
        state = snapshot["state"]
        if state != self.last_state and not self.manual_expand:
            self._set_bubble(state in ("approval", "done"))
        self.last_state = state
        self.face.setimage(icon(state, frame, snapshot["working_count"]))
        if self.detail is not None:
            labels = {
                "idle": "Ready", "working": f"Working · {snapshot['elapsed']}s",
                "approval": "Codex needs approval", "done": "Done",
                "interrupted": "Interrupted", "error": "Error",
            }
            message = " ".join(snapshot["message"].split())
            project = " ".join(snapshot["project"].split())
            if len(project) > 24:
                project = project[:23] + "…"
            content = f"Codex · {project}\n{labels[state]}"
            if message:
                content += "\n" + message[:72]
            if content != self.detail_content:
                # Native WRAP_CONTENT lays out the bubble without a blocking size query.
                self.detail.settext(content)
                self.detail_content = content
                if bool(message) != self.detail_has_message:
                    self.detail_has_message = bool(message)
                    self._position_bubble()

    def handle(self, event: tg.Event) -> bool:
        if not isinstance(event.value, dict):
            return False
        if event.type == tg.Event.touch:
            if event.value.get("id") == self.face.id and event.value.get("action") == "down":
                if self.pending_down is not None:
                    raw_x, raw_y, started, _, _ = self.pending_down
                    pointers = event.value.get("pointers")
                    local = _point(pointers[0]) if isinstance(pointers, list) and pointers else None
                    if local is not None and 0 <= local[0] <= PET_SIZE_DP and 0 <= local[1] <= PET_SIZE_DP:
                        # ImageView touch coordinates are in the 64 px icon, so
                        # re-anchor when Android has clamped the overlay window.
                        self.x = max(0, round(raw_x - local[0] * self.density))
                        self.y = max(0, round(raw_y - local[1] * self.density))
                    self.down = (raw_x, raw_y, started, self.x, self.y)
                self.pending_down = None
                self.dragged = False
            elif self.bubble is not None and event.value.get("id") == self.bubble.id:
                self.manual_expand = True
                self.pending_down = None
            return False
        if event.type != tg.Event.overlaytouch:
            return False
        self.touch_count += 1
        self.last_touch = str(event.value.get("action", ""))
        xy = _point(event.value)
        if xy is None:
            return False
        action = event.value.get("action")
        if action == "down":
            self.pending_down = (xy[0], xy[1], time.monotonic(), self.x, self.y)
            self.down = None
            self.dragged = False
        elif action == "move" and self.down is not None:
            dx, dy = xy[0] - self.down[0], xy[1] - self.down[1]
            slop = 12 * self.density
            if dx * dx + dy * dy > slop * slop:
                self.dragged = True
            if self.dragged:
                self.x = max(0, self.down[3] + int(dx))
                self.y = max(0, self.down[4] + int(dy))
                if self.expanded:
                    self._position_bubble()
                else:
                    self.pet.setposition(self.x, self.y)
        elif action in ("up", "cancel") and self.down is not None:
            self.pending_down = None
            if self.dragged:
                self._save_position()
                self.down = None
                if self.expanded and self._choose_bubble_side():
                    return True
            elif action == "up" and time.monotonic() - self.down[2] < 0.7:
                self.manual_expand = not self.expanded
                self._set_bubble(not self.expanded)
                self.down = None
                return True
            self.down = None
        elif action in ("up", "cancel"):
            self.pending_down = None
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
        self.ui.render(self.snapshot(), frame)
        while not self.stopping:
            state = self.snapshot()["state"]
            timeout = 2.0 if state == "working" else (1.4 if state == "approval" else None)
            readable, _, _ = select.select([connection._event, self.read_wake], [], [], timeout)
            if self.read_wake in readable:
                self.read_wake.recv(4096)
                if self.stopping:
                    break
                frame = 0
                self.ui.render(self.snapshot(), frame)
            if connection._event in readable:
                if not connection._event.recv(1, socket.MSG_PEEK):
                    raise ConnectionError("Termux:GUI disconnected")
                event = connection.checkevent()
                if event is not None:
                    if self.ui.handle(event):
                        self.ui.render(self.snapshot(), frame)
            if not readable:
                frame = 1 - frame
                self.ui.render(self.snapshot(), frame)
