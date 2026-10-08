"""Runtime paths, bounded Unix socket requests, and fail-open daemon startup."""

from __future__ import annotations

import fcntl
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from typing import Any

HOME = Path.home()
PROJECT = Path(__file__).resolve().parent.parent
RUNTIME = HOME / ".cache" / "codex-pet"
CONFIG = HOME / ".config" / "codex-pet" / "config.json"
SOCKET = RUNTIME / "pet.sock"
LOG = RUNTIME / "pet.log"
START_LOCK = RUNTIME / "start.lock"
DAEMON_LOCK = RUNTIME / "daemon.lock"
EVENT_WAKE = RUNTIME / 'events.sock'


def directories() -> None:
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
    CONFIG.parent.mkdir(mode=0o700, parents=True, exist_ok=True)


def request(payload: dict[str, Any], timeout: float = 0.25) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        def remaining() -> None:
            budget = deadline - time.monotonic()
            if budget <= 0:
                raise TimeoutError("IPC request deadline exceeded")
            connection.settimeout(budget)

        remaining()
        connection.connect(str(SOCKET))
        remaining()
        connection.sendall(data)
        response = bytearray()
        while len(response) < 65536:
            remaining()
            part = connection.recv(min(4096, 65536 - len(response)))
            if not part:
                break
            response.extend(part)
            if b"\n" in part:
                break
    if not response:
        raise ConnectionError("daemon returned no response")
    return json.loads(response.split(b"\n", 1)[0])


def send_event(event: dict[str, Any], quick: bool = False) -> bool:
    from .adapters.codex import direct_event
    from .delivery import EventJournal
    normalized = direct_event(event)
    if normalized is None:
        return False
    # Publication precedes the wake/request. A timed-out caller never owns the
    # only copy, and both attempts retain exactly the same identity and time.
    journal = EventJournal(RUNTIME)
    journal.publish(normalized)
    event = normalized

    def committed() -> bool:
        # The final SessionEnd can be committed through the datagram wake and
        # close IPC before its sender gets a reply. Its durable receipt is also
        # an acknowledgment; do not resurrect the daemon just to retry it.
        try:
            _, receipts = journal.load()
            return event['event_id'] in receipts
        except (OSError, ValueError, TypeError):
            return False

    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as wake:
        wake.setblocking(False)
        try:
            wake.sendto(b'x', str(EVENT_WAKE))
        except OSError:
            pass
    timeout = 0.2 if quick else 0.5
    try:
        reply = request({"action": "event", "event": event}, timeout)
        if reply.get("ok"):
            return True
    except (OSError, ValueError, ConnectionError):
        pass

    if committed():
        return True
    start_daemon(0.65 if quick else 1.2)
    if committed():
        return True
    try:
        reply = request({"action": "event", "event": event}, timeout)
        return bool(reply.get("ok"))
    except (OSError, ValueError, ConnectionError):
        return committed()


def _daemon_lock_held() -> bool:
    if not RUNTIME.exists():
        return False
    with open(DAEMON_LOCK, "a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(lock, fcntl.LOCK_UN)
    return False


def start_daemon(wait: float = 0.8) -> dict[str, Any] | None:
    deadline = time.monotonic() + wait
    directories()
    with open(START_LOCK, "a+b") as lock:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(min(0.01, remaining))
        try:
            spawned = False
            while time.monotonic() < deadline:
                try:
                    result = request({"action": "status"},
                                     min(0.15, deadline - time.monotonic()))
                    if not result.get('stopping'):
                        return result
                except (OSError, ValueError, ConnectionError):
                    pass
                if time.monotonic() >= deadline:
                    return None
                if not spawned and not _daemon_lock_held():
                    try:
                        SOCKET.unlink()
                    except FileNotFoundError:
                        pass
                    with open(LOG, "ab", buffering=0) as log:
                        subprocess.Popen(
                            [sys.executable, str(PROJECT / "bin" / "codex-pet"), "daemon"],
                            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                            cwd=str(PROJECT), start_new_session=True, close_fds=True,
                        )
                    spawned = True
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(min(0.04, remaining))
            return None
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def notification(state: str, project: str, message: str = "") -> None:
    if state == 'clear':
        command = shutil.which('termux-notification-remove')
        if command is not None:
            try:
                subprocess.run([command, '99177'], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=2, check=False)
            except (OSError, subprocess.TimeoutExpired):
                pass
        return
    command = shutil.which("termux-notification")
    if command is None or state not in ("needs_input", "ready"):
        return
    title = "Codex approval requested" if state == "needs_input" else "Codex turn stopped"
    content = project + (" · " + message[:90] if message else "")
    try:
        subprocess.run(
            [command, "--id", "99177", "--title", title, "--content", content],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
