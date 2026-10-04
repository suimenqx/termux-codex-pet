"""Native Termux:GUI overlay. All GUI calls stay on the daemon's GUI thread."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path
import select
import socket
import threading
import time
from typing import Any, Callable


from .pet_runtime import PetRuntime, PetVisual
from .frames import FrameSource, FrameComposer
from .frame_cache import FrameCache
from .touch import DragController
from .renderer.protocol import TouchInput
from .preferences import read_config, save_position
from .renderer.termux_gui import TermuxGuiRenderer, RebuildRenderer, SharedFailure
from .renderer.transport import Connection
from .renderer.policy import RendererPolicy, RendererStatus

LOG = logging.getLogger(__name__)
RECONNECT_DELAYS = (0.0, 5.0, 20.0, 60.0)


@dataclass(frozen=True)
class OverlayStatus:
    x: int
    y: int
    touch_count: int
    last_touch: str


@dataclass(frozen=True)
class SubmittedStatus:
    revision: int
    event_id: str
    state: str
    submitted_at: float
    ingest_to_submit_ms: float | None
    source_to_submit_ms: float | None


class GuiWorker:
    def __init__(self, config_path: Path, snapshot: Callable[[], dict[str, Any]],
                 on_status: Callable[[bool, str], None], *, transport: str = "auto",
                 policy: RendererPolicy | None = None) -> None:
        self.transport = transport
        self.policy = policy if policy is not None else RendererPolicy.installed()
        self.renderer_status = RendererStatus(
            binding_version=self.policy.binding_version)
        self.shared_failure = ""
        self.config_path = config_path
        self.snapshot = snapshot
        self.on_status = on_status
        self.read_wake, self.write_wake = socket.socketpair()
        self.write_wake.setblocking(False)
        self.read_wake.setblocking(False)
        self.stopping = False
        self.thread = threading.Thread(
            target=self._run, name="codex-pet-gui", daemon=True)
        self.ui: TermuxGuiRenderer | None = None
        self.overlay_status: OverlayStatus | None = None
        self.submitted_status: SubmittedStatus | None = None
        self.runtime: PetRuntime | None = None
        self.cache = FrameCache()
        self.source = FrameSource(self.cache)
        self.composer = FrameComposer(self.cache)
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

    def _remember_shared_failure(self, error: Exception) -> None:
        self.shared_failure = str(error)[:180]
        self.renderer_status = replace(self.renderer_status,
                                       fallback_reason=self.shared_failure,
                                       last_connection_error=self.shared_failure)
        LOG.warning(
            'Discarding shared connection; switching to fresh PNG: %s', error)
        self.on_status(False, self.shared_failure)

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
                self.ui = TermuxGuiRenderer(connection, position, cache=self.cache,
                                            transport='png' if self.shared_failure else self.transport,
                                            policy=self.policy)
                self.drag = DragController(position, self.ui.density)
                self._publish_overlay()
                failures = 0
                self._loop(connection)
            except RebuildRenderer:
                failures = 0
                self.on_status(False, 'starting')
            except SharedFailure as exc:
                failures = 0
                self._remember_shared_failure(exc)
            except Exception as exc:
                if (self.ui is not None and self.ui.transport == 'shared'
                        and connection is not None and connection.closed):
                    # Event reads and moves use this connection too. Every
                    # failed native transaction closes it; these failures must
                    # remember the same fallback as a failed frame submission.
                    failures = 0
                    self._remember_shared_failure(exc)
                else:
                    failures += 1
                    self.renderer_status = replace(
                        self.renderer_status, last_connection_error=str(exc)[:180])
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
                    self.submitted_status = None
                if connection is not None:
                    connection.close()
            # Keep retrying a lost GUI connection at a low rate; a Codex event
            # wakes the worker immediately rather than waiting for the timer.
            if not self.stopping:
                delay = RECONNECT_DELAYS[min(
                    max(0, failures - 1), len(RECONNECT_DELAYS) - 1)]
                readable, _, _ = select.select([self.read_wake], [], [], delay)
                if readable:
                    self._drain_wake()
                    failures = 0

        self.cache.clear()

    def _loop(self, connection: Connection) -> None:
        assert self.ui is not None
        self.refresh(time.monotonic())
        self.renderer_status = RendererStatus(
            self.policy.binding_version, self.ui.plugin_version, self.ui.transport,
            'shared disabled after failure' if self.shared_failure else self.ui.policy_reason,
            self.shared_failure, self.renderer_status.last_connection_error)
        LOG.info('Renderer binding=%s plugin=%s transport=%s reason=%s fallback=%s',
                 self.renderer_status.binding_version, self.renderer_status.plugin_version,
                 self.renderer_status.transport, self.renderer_status.reason,
                 self.renderer_status.fallback_reason)
        self.on_status(True, "")
        assert self.runtime is not None
        while not self.stopping:
            timeout = self.runtime.timeout(time.monotonic())
            readable, _, _ = select.select(
                [connection._event, self.read_wake], [], [], timeout)
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
        snapshot = self.snapshot()
        visual = PetVisual.from_snapshot(snapshot)
        if self.runtime is None:
            self.runtime = PetRuntime(visual, now)
        else:
            self.runtime.sync(visual, now)
        self.runtime.tick(now)
        request = self.runtime.current()
        base = self.source.frame(
            request.pack_id, request.revision, request.reference)
        self.ui.present(self.composer.compose(base, request.count, request.marker))
        submitted_at = time.monotonic()
        received = snapshot.get('event_received_monotonic', 0)
        emitted = snapshot.get('event_emitted_monotonic', 0)
        status = SubmittedStatus(
            snapshot.get('state_revision', 0), snapshot.get('event_id', ''), visual.state,
            submitted_at, max(0, (submitted_at - received) * 1000) if received else None,
            max(0, (submitted_at - emitted) * 1000) if emitted else None)
        previous = self.submitted_status
        if previous is None or (previous.revision, previous.state) != (status.revision, status.state):
            self.submitted_status = status
            LOG.info('State submitted revision=%s state=%s ingest_ms=%s source_ms=%s',
                     status.revision, status.state, status.ingest_to_submit_ms, status.source_to_submit_ms)

    def handle_input(self, event: TouchInput) -> None:
        """Apply normalized input to position and persistence, on the GUI owner."""
        assert self.ui is not None and self.drag is not None
        result = self.drag.handle(event)
        if result.position is not None:
            if (self.ui.x, self.ui.y) != result.position:
                self.ui.move(*result.position)
            if result.commit:
                save_position(self.config_path, *result.position)
