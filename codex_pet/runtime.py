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


def directories() -> None:
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
    CONFIG.parent.mkdir(mode=0o700, parents=True, exist_ok=True)


def request(payload: dict[str, Any], timeout: float = 0.25) -> dict[str, Any]:
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(str(SOCKET))
        connection.sendall(data)
        response = bytearray()
        while len(response) < 65536:
            part = connection.recv(4096)
            if not part:
                break
            response.extend(part)
            if b"\n" in part:
                break
    if not response:
        raise ConnectionError("daemon returned no response")
    return json.loads(response.split(b"\n", 1)[0])


def send_event(event: dict[str, Any], quick: bool = False) -> bool:
    timeout = 0.2 if quick else 0.5
    try:
        reply = request({"action": "event", "event": event}, timeout)
        if reply.get("ok"):
            return True
    except (OSError, ValueError, ConnectionError):
        pass

    start_daemon(0.65 if quick else 1.2)
    try:
        reply = request({"action": "event", "event": event}, timeout)
        return bool(reply.get("ok"))
    except (OSError, ValueError, ConnectionError):
        return False


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
    directories()
    with open(START_LOCK, "a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            try:
                return request({"action": "status"}, 0.2)
            except (OSError, ValueError, ConnectionError):
                pass
            deadline = time.monotonic() + wait
            spawned = False
            while time.monotonic() < deadline:
                try:
                    return request({"action": "status"}, 0.15)
                except (OSError, ValueError, ConnectionError):
                    pass
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
                time.sleep(0.04)
            return None
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def notification(state: str, project: str, message: str = "") -> None:
    command = shutil.which("termux-notification")
    if command is None or state not in ("needs_input", "ready"):
        return
    title = "Codex needs input" if state == "needs_input" else "Codex ready"
    content = project + (" · " + message[:90] if message else "")
    try:
        subprocess.run(
            [command, "--id", "99177", "--title", title, "--content", content],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
