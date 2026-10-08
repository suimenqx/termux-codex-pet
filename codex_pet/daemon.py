"""One daemon: in-memory sessions, Unix socket server, and native GUI worker."""

from __future__ import annotations

import fcntl
from dataclasses import asdict
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

from .gui import GuiWorker, SubmittedStatus
from .pets import appearance_catalog
from .preferences import save_appearance, selected_appearance
from .runtime import CONFIG, DAEMON_LOCK, LOG, SOCKET, RUNTIME, EVENT_WAKE, directories, notification
from .delivery import EventJournal
from .notifications import NotificationDispatcher
from .processes import ProcessIdentity, ProcessWatcher, discover_clients
from .state import SessionStore
from .adapters.codex import BOOT_ID, SHARED_INSTANCE_PREFIX, direct_event
from .renderer.policy import RendererPolicy

LOGGING = logging.getLogger(__name__)


class Daemon:
    def __init__(self, *, renderer_policy: RendererPolicy | None = None,
                 journal: EventJournal | None = None) -> None:
        self.sessions = SessionStore()
        self.lock = threading.RLock()
        self.gui_ready = False
        self.gui_error = "starting"
        self.stopping = False
        self.observed_lifecycle = False
        self.appearance = selected_appearance(CONFIG)
        # Acquire notification_lock only after lock; never hold either for the command.
        self.notification_lock = threading.Lock()
        self.last_notification: tuple[str, str, str] | None = None
        self.notifications = NotificationDispatcher(lambda *args: notification(*args))
        self.journal = journal
        self.receipts: dict[str, dict[str, Any]] = {}
        self.revision = 0
        self.last_event: dict[str, Any] = {}
        self.received_monotonic = 0.0
        self.delivery_error = ''
        self.delivery_pending = False
        self.processes = ProcessWatcher()
        self.clients = ProcessWatcher()
        self.shared_clients_gone = False
        self.signal_read, self.signal_write = socket.socketpair()
        self.signal_write.setblocking(False)
        self.gui = GuiWorker(CONFIG, self.snapshot, self.gui_status, policy=renderer_policy)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            state = self.sessions.snapshot()
            if self.delivery_error:
                state.update(state='unknown', confidence='uncertain', state_reason=self.delivery_error)
            elif self.delivery_pending:
                state.update(state='unknown', confidence='uncertain', state_reason='retained events are still replaying')
            return {**state, "appearance": self.appearance, 'state_revision': self.revision,
                    'event_id': self.last_event.get('event_id', ''),
                    'event_timestamp': self.last_event.get('timestamp', 0),
                    'event_emitted_monotonic': self.last_event.get('emitted_monotonic_ns', 0) / 1_000_000_000
                    if self.last_event.get('boot_id') == BOOT_ID else 0,
                    'event_received_monotonic': self.received_monotonic}

    def restore_events(self) -> None:
        assert self.journal is not None
        try:
            saved, self.receipts = self.journal.load()
            self.sessions = SessionStore.restore(saved)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.delivery_error = f'session checkpoint unavailable: {exc}'[:180]
            self.receipts = {}
            LOGGING.exception('Session checkpoint could not be restored')
        self.revision = max((receipt.get('revision', 0) for receipt in self.receipts.values()), default=0)
        self.drain_events()

    def _apply_event(self, event: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            applied = self.sessions.apply(event)
            if event['kind'] != 'manual':
                self.observed_lifecycle = True
            self.revision += 1
            self.last_event = event
            self.received_monotonic = time.monotonic()
            receipt = {'applied': applied, 'revision': self.revision}
            self.receipts[event['event_id']] = receipt
        return receipt

    def _should_stop_automatically(self) -> bool:
        with self.lock:
            sessions = self.sessions.sessions.values()
            ended = self.observed_lifecycle and not self.sessions.sessions
            clients_ended = self.shared_clients_gone and all(
                value.instance_id.startswith(SHARED_INSTANCE_PREFIX) for value in sessions)
            return (ended or clients_ended) and not self.delivery_pending and not self.delivery_error

    def _stop_if_sessions_ended(self) -> None:
        if self._should_stop_automatically():
            LOGGING.info('Codex sessions ended or last shared CLI client exited; stopping daemon')
            self.stopping = True
            self._clear_fallback()

    def _reconcile_processes(self) -> None:
        with self.lock:
            owners = {value.instance_id: ProcessIdentity(value.producer_pid, value.producer_start_ticks,
                                                         value.producer_boot_id)
                      for value in self.sessions.sessions.values()
                      if value.instance_id and value.producer_pid and value.producer_start_ticks and value.producer_boot_id}
        closed, errors = self.processes.sync(owners)
        shared = {owner for owner in owners if owner.startswith(SHARED_INSTANCE_PREFIX)}
        clients, client_error = discover_clients() if shared else ({}, '')
        if shared:
            # A transient discovery omission must not discard a verified exit
            # watch for a still-live client. Only its pidfd can retire it.
            clients = {**{owner: identity for owner, (identity, _) in self.clients.watches.items()}, **clients}
        closed_clients, client_errors = self.clients.sync(clients)
        client_error = client_error or next(iter(client_errors.values()), '').replace('producer', 'client')
        changed = False
        with self.lock:
            self.shared_clients_gone = bool(shared) and not (clients.keys() - closed_clients.keys()) and not client_error
            for value in self.sessions.sessions.values():
                error = errors.get(value.instance_id, '') or (client_error if value.instance_id in shared else '')
                changed = changed or value.monitor_error != error
                value.monitor_error = error
        for owner, identity in closed.items():
            event = direct_event({'kind': 'instance_end', 'state': 'end', 'source': 'process',
                                  'session_id': 'process-exit', 'event_id': 'process-exit:' + identity.instance_id,
                                  **identity.fields(), 'instance_id': owner})
            assert event is not None
            if self.journal is not None:
                if event['event_id'] not in self.receipts:
                    self.journal.publish(event)
                    self.delivery_pending = True
            else:
                self._apply_event(event)
            changed = True
        if changed:
            self.gui.wake()
            self._fallback()

    def drain_events(self) -> None:
        if self.journal is None:
            self._reconcile_processes()
            return
        try:
            self._reconcile_processes()
            was_pending = self.delivery_pending
            pending = self.journal.pending()
            self.delivery_pending = len(pending) == 256
            if not pending:
                if was_pending:
                    self.gui.wake()
                return
            for raw in pending:
                event = direct_event(raw)
                if event is None:
                    raise ValueError('Invalid retained event')
                if event['event_id'] not in self.receipts:
                    self._apply_event(event)
            self.journal.commit(self.sessions.checkpoint(), self.receipts)
            # A crash between commit and unlink is fenced by persisted receipts.
            for event in pending:
                self.journal.remove(event)
            self.receipts = dict(list(self.receipts.items())[-2048:])
            self.delivery_error = ''
            self._reconcile_processes()
            self.gui.wake()
            self._fallback()
        except (OSError, ValueError, TypeError) as exc:
            error = f'event delivery awaiting recovery: {exc}'[:180]
            if error != self.delivery_error:
                LOGGING.exception('Could not checkpoint retained events')
            self.delivery_error = error
            self.delivery_pending = True
            self.gui.wake()
            self._fallback()

    def gui_status(self, ready: bool, error: str) -> None:
        with self.lock:
            self.gui_ready = ready
            self.gui_error = error
            if ready:
                self._clear_fallback()
                self.notifications.submit(('clear', '', ''))
        if ready:
            LOGGING.info("Termux:GUI overlay ready")
        else:
            LOGGING.error("Termux:GUI unavailable: %s", error)
            self._fallback()

    def _fallback(self) -> None:
        with self.lock:
            if self.gui_ready or self.gui_error == "starting" or self._should_stop_automatically():
                self._clear_fallback()
                return
            snapshot = self.snapshot()
            if snapshot["state"] not in ("needs_input", "ready"):
                self._clear_fallback()
                return
            key = (snapshot["state"], snapshot["project"], snapshot["message"])
            with self.notification_lock:
                if key == self.last_notification:
                    return
                self.last_notification = key
            self.notifications.submit(key)

    def _clear_fallback(self) -> None:
        with self.notification_lock:
            if self.last_notification is None:
                return
            self.last_notification = None
        self.notifications.submit(('clear', '', ''))

    def status(self) -> dict[str, Any]:
        with self.lock:
            state = self.snapshot()
            overlay_status = self.gui.overlay_status
            overlay = asdict(overlay_status) if overlay_status is not None else None
            submitted: SubmittedStatus | None = getattr(self.gui, 'submitted_status', None)
            return {"ok": True, "pid": os.getpid(), "gui_ready": self.gui_ready,
                    "stopping": self.stopping or self._should_stop_automatically(),
                    "overlay": overlay, "renderer": asdict(self.gui.renderer_status),
                    "gui_error": self.gui_error, **state,
                    'submitted': asdict(submitted) if submitted is not None else None,
                    'last_event_applied': self.receipts.get(self.last_event.get('event_id', ''), {}).get('applied'),
                    'delivery_pending': self.delivery_pending, 'delivery_error': self.delivery_error}

    def process(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {"ok": False, "error": "invalid request"}
        action = payload.get("action")
        self.drain_events()
        if action == "status":
            return self.status()
        if action == "reconnect":
            with self.lock:
                if not self.gui_ready:
                    self.gui_error = "starting"
                    self.gui.wake()
            return self.status()
        if action == "set_appearance":
            appearance = payload.get("appearance")
            catalog = appearance_catalog()
            if not isinstance(appearance, str) or appearance not in catalog:
                return {"ok": False, "error": "unknown appearance",
                        "available": list(catalog)}
            try:
                save_appearance(CONFIG, appearance)
            except OSError as exc:
                return {"ok": False, "error": f"could not save appearance: {exc}"}
            with self.lock:
                self.appearance = appearance
            self.gui.wake()
            return {"ok": True, "appearance": appearance,
                    "name": catalog[appearance].name}
        if action == "stop":
            self._signal(0, None)
            return {"ok": True}
        if action == "event":
            event = direct_event(payload.get("event"))
            if event is None:
                return {"ok": False, "error": "invalid event"}
            if self.journal is not None:
                self.journal.publish(event)
                self.drain_events()
                receipt = self.receipts.get(event['event_id'])
                if receipt is None or self.delivery_error:
                    return {'ok': False, 'error': self.delivery_error or 'event retained for retry'}
            else:
                receipt = self.receipts.get(event['event_id']) or self._apply_event(event)
                self._reconcile_processes()
            self.gui.wake()
            self._fallback()
            return {"ok": True, **receipt, 'event_id': event['event_id'],
                    "gui_ready": self.gui_ready, "state": self.snapshot()['state']}
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
            event_wake = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            inode = None
            try:
                listener.bind(str(SOCKET))
                listener.listen(16)
                inode = SOCKET.stat().st_ino
                EVENT_WAKE.unlink(missing_ok=True)
                event_wake.bind(str(EVENT_WAKE))
                event_wake.setblocking(False)
                if self.journal is None:
                    self.journal = EventJournal(RUNTIME)
                self.restore_events()
                self._stop_if_sessions_ended()
                if self.stopping:
                    return
                signal.signal(signal.SIGTERM, self._signal)
                signal.signal(signal.SIGINT, self._signal)
                self.gui.start()
                LOGGING.info("Daemon started pid=%s", os.getpid())
                while not self.stopping:
                    readable, _, _ = select.select([listener, self.signal_read, event_wake,
                                                    *self.processes.descriptors, *self.clients.descriptors], [], [],
                                                    (1.0 if self.delivery_error else 0.0) if self.delivery_pending else None)
                    if event_wake in readable:
                        try:
                            while event_wake.recv(4096):
                                pass
                        except BlockingIOError:
                            pass
                    self.drain_events()
                    if listener in readable:
                        self._serve_one(listener)
                    if self.signal_read in readable:
                        self.signal_read.recv(4096)
                    # Reply to any accepted request and finish durable replay
                    # before deciding whether the final session has ended.
                    self._stop_if_sessions_ended()
            finally:
                self.stopping = True
                self.gui.stop()
                self._clear_fallback()
                self.notifications.flush()
                self.notifications.stop()
                self.processes.close()
                self.clients.close()
                listener.close()
                event_wake.close()
                EVENT_WAKE.unlink(missing_ok=True)
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


def main(*, renderer_policy: RendererPolicy | None = None) -> None:
    directories()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[RotatingFileHandler(LOG, maxBytes=512_000, backupCount=2)])
    try:
        Daemon(renderer_policy=renderer_policy).run()
    except Exception:
        LOGGING.exception("Daemon crashed")
        raise
