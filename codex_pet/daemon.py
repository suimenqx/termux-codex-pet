"""One daemon: in-memory sessions, Unix socket server, and native GUI worker."""

from __future__ import annotations

import fcntl
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import select
import signal
import socket
import threading
import time
from typing import Any

from .gui import GuiWorker
from .runtime import CONFIG, DAEMON_LOCK, LOG, SOCKET, directories, notification
from .state import SessionStore, direct_event

LOGGING = logging.getLogger(__name__)


class Daemon:
    def __init__(self) -> None:
        self.sessions = SessionStore()
        self.lock = threading.RLock()
        self.gui_ready = False
        self.gui_error = "starting"
        self.stopping = False
        self.signal_read, self.signal_write = socket.socketpair()
        self.gui = GuiWorker(CONFIG, self.snapshot, self.gui_status)
        self.last_notification: tuple[str, str, str] | None = None

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return self.sessions.snapshot()

    def gui_status(self, ready: bool, error: str) -> None:
        with self.lock:
            self.gui_ready = ready
            self.gui_error = error
            snapshot = self.sessions.snapshot()
        if ready:
            LOGGING.info("Termux:GUI overlay ready")
            self.last_notification = None
        else:
            LOGGING.error("Termux:GUI unavailable: %s", error)
            self._fallback(snapshot)

    def _fallback(self, snapshot: dict[str, Any]) -> None:
        if snapshot["state"] not in ("approval", "done"):
            return
        key = (snapshot["state"], snapshot["project"], snapshot["message"])
        if key != self.last_notification:
            notification(*key)
            self.last_notification = key

    def status(self) -> dict[str, Any]:
        with self.lock:
            state = self.sessions.snapshot()
            ui = self.gui.ui
            overlay = ({"x": ui.x, "y": ui.y, "expanded": ui.expanded,
                        "touch_count": ui.touch_count, "last_touch": ui.last_touch,
                        "bubble": ({"x": ui.bubble_x, "y": ui.bubble_y,
                                    "width": ui.bubble_width_px, "height": ui.bubble_height_px}
                                   if ui.bubble is not None else None)}
                       if ui is not None else None)
            return {"ok": True, "pid": os.getpid(), "gui_ready": self.gui_ready,
                    "overlay": overlay,
                    "gui_error": self.gui_error, **state}

    def process(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {"ok": False, "error": "invalid request"}
        action = payload.get("action")
        if action == "status":
            return self.status()
        if action == "reconnect":
            with self.lock:
                if not self.gui_ready:
                    self.gui_error = "starting"
                    self.gui.wake()
            return self.status()
        if action == "stop":
            self.stopping = True
            self.signal_write.send(b"s")
            return {"ok": True}
        if action == "event":
            event = direct_event(payload.get("event"))
            if event is None:
                return {"ok": False, "error": "invalid event"}
            with self.lock:
                self.sessions.apply(event)
                snapshot = self.sessions.snapshot()
                ready = self.gui_ready
                error = self.gui_error
            self.gui.wake()
            if not ready and error != "starting":
                self._fallback(snapshot)
            return {"ok": True, "gui_ready": ready, "state": snapshot["state"]}
        return {"ok": False, "error": "unknown action"}

    def _serve_one(self, listener: socket.socket) -> None:
        connection, _ = listener.accept()
        with connection:
            connection.settimeout(0.25)
            try:
                data = bytearray()
                while len(data) < 65536 and b"\n" not in data:
                    part = connection.recv(4096)
                    if not part:
                        break
                    data.extend(part)
                payload = json.loads(data.split(b"\n", 1)[0])
                response = self.process(payload)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                LOGGING.warning("Bad IPC request: %s", exc)
                response = {"ok": False, "error": "bad request"}
            try:
                connection.sendall((json.dumps(response) + "\n").encode())
            except OSError:
                pass

    def run(self) -> None:
        directories()
        os.umask(0o077)
        with open(DAEMON_LOCK, "a+b") as daemon_lock:
            try:
                fcntl.flock(daemon_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            try:
                SOCKET.unlink()
            except FileNotFoundError:
                pass
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            inode = None
            try:
                listener.bind(str(SOCKET))
                listener.listen(16)
                inode = SOCKET.stat().st_ino
                signal.signal(signal.SIGTERM, self._signal)
                signal.signal(signal.SIGINT, self._signal)
                self.gui.start()
                LOGGING.info("Daemon started pid=%s", os.getpid())
                while not self.stopping:
                    with self.lock:
                        deadline = self.sessions.next_deadline()
                    timeout = max(0, deadline - time.monotonic()) if deadline is not None else None
                    readable, _, _ = select.select([listener, self.signal_read], [], [], timeout)
                    if listener in readable:
                        self._serve_one(listener)
                    if self.signal_read in readable:
                        self.signal_read.recv(4096)
                    with self.lock:
                        expired = self.sessions.expire()
                    if expired:
                        self.gui.wake()
            finally:
                self.stopping = True
                self.gui.stop()
                listener.close()
                try:
                    if inode is not None and SOCKET.stat().st_ino == inode:
                        SOCKET.unlink()
                except FileNotFoundError:
                    pass
                self.signal_read.close()
                self.signal_write.close()
                LOGGING.info("Daemon stopped")

    def _signal(self, _number: int, _frame: Any) -> None:
        self.stopping = True
        try:
            self.signal_write.send(b"s")
        except OSError:
            pass


def main() -> None:
    directories()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[RotatingFileHandler(LOG, maxBytes=512_000, backupCount=2)])
    try:
        Daemon().run()
    except Exception:
        LOGGING.exception("Daemon crashed")
        raise
