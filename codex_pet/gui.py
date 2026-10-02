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


from .pet_runtime import PetRuntime, PetVisual
from .frames import FrameSource, FrameComposer
from .touch import DragController
from .renderer.protocol import TouchInput
from .preferences import read_config, save_position
from .renderer.termux_gui import TermuxGuiRenderer
from .renderer.transport import Connection

LOG = logging.getLogger(__name__)
RECONNECT_DELAYS = (0.0, 5.0, 20.0, 60.0)


@dataclass(frozen=True)
class OverlayStatus:
    x: int
    y: int
    touch_count: int
    last_touch: str


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
        self.ui: TermuxGuiRenderer | None = None
        self.overlay_status: OverlayStatus | None = None
        self.runtime: PetRuntime | None = None
        self.source = FrameSource()
        self.composer = FrameComposer()
        self.drag: DragController | None = None

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
                saved = read_config(self.config_path).get("position", {})
                try:
                    position = max(0, int(saved["x"])), max(0, int(saved["y"]))
                except (KeyError, TypeError, ValueError):
                    position = (700, 420)
                self.ui = TermuxGuiRenderer(connection, position)
                self.drag = DragController(position, self.ui.density)
                self._publish_overlay()
                self.on_status(True, "")
                failures = 0
                self._loop(connection)
            except Exception as exc:
                failures += 1
                LOG.exception("Termux:GUI connection or overlay failed")
                self.on_status(False, str(exc)[:180])
            finally:
                if self.drag is not None:
                    self.drag.handle(TouchInput("cancel"))
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

    def _loop(self, connection: Connection) -> None:
        assert self.ui is not None
        self.runtime = None
        self.refresh(time.monotonic())
        assert self.runtime is not None
        while not self.stopping:
            timeout = self.runtime.timeout(time.monotonic())
            readable, _, _ = select.select([connection._event, self.read_wake], [], [], timeout)
            if self.read_wake in readable:
                self._drain_wake()
                if self.stopping:
                    break
                self.refresh(time.monotonic())
            if connection._event in readable:
                event = connection.checkevent()
                if event is not None:
                    normalized = self.ui.input(event)
                    if normalized is not None:
                        self.handle_input(normalized)
                    self._publish_overlay()
            now = time.monotonic()
            if self.runtime.deadline is not None and now >= self.runtime.deadline:
                self.refresh(now)

    def refresh(self, now: float) -> None:
        """Resolve the latest visible state and submit only its current frame."""
        assert self.ui is not None
        visual = PetVisual.from_snapshot(self.snapshot())
        if self.runtime is None:
            self.runtime = PetRuntime(visual, now)
        else:
            self.runtime.sync(visual, now)
        self.runtime.tick(now)
        request = self.runtime.current()
        base = self.source.frame(request.pack_id, request.revision, request.reference)
        self.ui.present(self.composer.compose(base, request.count))

    def handle_input(self, event: TouchInput) -> None:
        """Apply normalized input to position and persistence, on the GUI owner."""
        assert self.ui is not None and self.drag is not None
        result = self.drag.handle(event)
        if result.position is not None:
            if (self.ui.x, self.ui.y) != result.position:
                self.ui.move(*result.position)
            if result.commit:
                save_position(self.config_path, *result.position)
