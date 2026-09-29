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
        self.root = tg.LinearLayout(self.pet, vertical=True)
        self.root.setdimensions(76, 76)
        self.root.setbackgroundcolor(0)
        self.face = tg.ImageView(self.pet, self.root)
        self.face.setdimensions(56, 56)
        self.face.setmargin(10, "left")
        self.caption = tg.TextView(self.pet, "Codex", self.root)
        self.caption.setdimensions(76, 20)
        self.caption.setgravity(1, 1)
        self.caption.settextsize(12)
        self.caption.settextcolor(0xFFFFFFFF)
        self.caption.setbackgroundcolor(0xCC27313D)
        self.root.sendtouchevent(True)
        self.pet.sendoverlayevents(True)
        self.pet.setposition(self.x, self.y)
        self.bubble: tg.Activity | None = None
        self.detail: tg.TextView | None = None
        self.expanded = False
        self.manual_expand = False
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
        # The measured 76 dp native View provides the density without Android APIs.
        time.sleep(0.12)
        old_timeout = self.c._main.gettimeout()
        try:
            self.c._main.settimeout(1.5)
            width = self.root.getdimensions()[0]
            if width > 0:
                self.density = width / 76
        except (OSError, ValueError):
            LOG.warning("Could not measure overlay density; using 3.0")
        finally:
            self.c._main.settimeout(old_timeout)

    def _set_bubble(self, show: bool) -> None:
        if show and self.bubble is None:
            self.bubble = _overlay(self.c)
            self.detail = tg.TextView(self.bubble, "", None)
            self.detail.setdimensions(218, 100)
            self.detail.settextsize(14)
            self.detail.settextcolor(0xFFFFFFFF)
            self.detail.setbackgroundcolor(0xE02A2A2A)
            self.detail.setmargin(8)
            self.detail.sendtouchevent(True)
            self._position_bubble()
        elif not show and self.bubble is not None:
            self.bubble.finish()
            self.bubble = None
            self.detail = None
        self.expanded = show

    def _position_bubble(self) -> None:
        if self.bubble is not None:
            self.bubble.setposition(max(0, self.x - int(230 * self.density)), self.y)

    def render(self, snapshot: dict[str, Any], frame: int = 0) -> None:
        state = snapshot["state"]
        if state in ("approval", "done") and state != self.last_state and not self.manual_expand:
            self._set_bubble(True)
        elif state == "idle" and self.last_state in ("approval", "done", "interrupted") and not self.manual_expand:
            self._set_bubble(False)
        self.last_state = state
        self.face.setimage(icon(state, frame))
        captions = {
            "idle": "Codex Pet", "working": "Working", "approval": "Approve",
            "done": "Done", "interrupted": "Paused", "error": "Error",
        }
        count = snapshot["working_count"]
        caption = f"Working {count}" if state == "working" and count > 1 else captions[state]
        self.caption.settext(caption)
        colors = {
            "idle": 0xFFEAEAEA, "working": 0xFFFFC477, "approval": 0xFF65C0FF,
            "done": 0xFF92E689, "interrupted": 0xFFFFBFAE, "error": 0xFF7777FF,
        }
        self.caption.settextcolor(colors[state])
        if self.detail is not None:
            labels = {
                "idle": "Ready", "working": f"Working · {snapshot['elapsed']}s",
                "approval": "Codex needs approval", "done": "Done",
                "interrupted": "Interrupted", "error": "Error",
            }
            message = snapshot["message"]
            project = snapshot["project"]
            if len(project) > 24:
                project = project[:23] + "…"
            content = f"Codex · {project}\n{labels[state]}"
            if message:
                content += "\n" + message[:72]
            self.detail.settext(content)

    def handle(self, event: tg.Event) -> bool:
        if not isinstance(event.value, dict):
            return False
        if event.type == tg.Event.touch:
            if self.bubble is not None and event.value.get("aid") == self.bubble.aid:
                self.manual_expand = True
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
            self.down = (xy[0], xy[1], time.monotonic(), self.x, self.y)
            self.dragged = False
        elif action == "move" and self.down is not None:
            dx, dy = xy[0] - self.down[0], xy[1] - self.down[1]
            slop = 12 * self.density
            if dx * dx + dy * dy > slop * slop:
                self.dragged = True
            if self.dragged:
                self.x = max(0, self.down[3] + int(dx))
                self.y = max(0, self.down[4] + int(dy))
                self.pet.setposition(self.x, self.y)
                self._position_bubble()
        elif action in ("up", "cancel") and self.down is not None:
            if self.dragged:
                self._save_position()
            elif action == "up" and time.monotonic() - self.down[2] < 0.7:
                self.manual_expand = not self.expanded
                self._set_bubble(not self.expanded)
                self.down = None
                return True
            self.down = None
        return False

    def close(self) -> None:
        if self.bubble is not None:
            self.bubble.finish()
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
        retry_once = True
        while not self.stopping:
            connection: tg.Connection | None = None
            try:
                connection = tg.Connection()
                self.ui = OverlayUI(connection, self.config_path)
                self.on_status(True, "")
                self._loop(connection)
            except Exception as exc:
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
            # A lost GUI connection gets one immediate retry. Further retries
            # wait for a Codex event or an explicit start command.
            if not self.stopping:
                if retry_once:
                    retry_once = False
                    continue
                select.select([self.read_wake], [], [])
                self.read_wake.recv(4096)
                retry_once = True

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
