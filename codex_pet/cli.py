"""Human CLI and silent, fail-open Codex hook helper."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from typing import Any

from . import daemon
from .pets import APPEARANCES, APPEARANCE_BY_ID, DEFAULT_APPEARANCE
from .preferences import save_appearance, selected_appearance
from .runtime import CONFIG, LOG, SOCKET, _daemon_lock_held, directories, notification, request, start_daemon
from .state import STATES, direct_event, event_from_hook


def _send(event: dict[str, Any], quick: bool = False) -> bool:
    try:
        reply = request({"action": "event", "event": event}, 0.2 if quick else 0.5)
        if reply.get("ok"):
            return True
    except (OSError, ValueError, ConnectionError):
        pass
    start_daemon(0.65 if quick else 1.2)
    try:
        reply = request({"action": "event", "event": event}, 0.2 if quick else 0.5)
        return bool(reply.get("ok"))
    except (OSError, ValueError, ConnectionError):
        return False


def _log_hook_error(exc: BaseException) -> None:
    try:
        directories()
        with open(LOG, "a", encoding="utf-8") as file:
            file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} hook helper: {exc!r}\n")
            traceback.print_exception(exc, file=file)
    except OSError:
        pass


def event_main() -> None:
    parser = argparse.ArgumentParser(prog="codex-pet-event")
    parser.add_argument("--state", choices=sorted(STATES - {"end"}))
    parser.add_argument("--session-id", default="manual")
    parser.add_argument("--project", default="Codex")
    parser.add_argument("--message", default="")
    args = parser.parse_args()
    try:
        if args.state:
            event = direct_event({"state": args.state, "session_id": args.session_id,
                                  "project": args.project, "message": args.message})
        else:
            raw = sys.stdin.buffer.read(65537)
            if len(raw) > 65536:
                return
            event = event_from_hook(json.loads(raw)) if raw.strip() else None
        if event is None:
            return
        if not _send(event, quick=True):
            notification(event["state"], event["project"], event["message"])
    except Exception as exc:
        _log_hook_error(exc)
        if "event" in locals() and event is not None:
            notification(event["state"], event["project"], event["message"])


def _status() -> dict[str, Any] | None:
    try:
        return request({"action": "status"}, 0.3)
    except (OSError, ValueError, ConnectionError):
        return None


def _start() -> int:
    result = start_daemon(4.0)
    if result is None:
        print(f"Codex Pet did not start; see {LOG}", file=sys.stderr)
        return 1
    if not result.get("gui_ready") and result.get("gui_error") != "starting":
        try:
            result = request({"action": "reconnect"}, 0.3)
        except (OSError, ValueError, ConnectionError):
            result = _status() or result
    deadline = time.monotonic() + 9
    while not result.get("gui_ready") and result.get("gui_error") == "starting" and time.monotonic() < deadline:
        time.sleep(0.2)
        result = _status() or result
    state = result.get("state", "idle")
    if result.get("gui_ready"):
        print(f"Codex Pet running (pid {result['pid']}, GUI ready, {state})")
        return 0
    print(f"Codex Pet running (pid {result['pid']}, GUI unavailable: {result.get('gui_error')})")
    return 1


def _stop() -> int:
    current = _status()
    if current:
        try:
            request({"action": "stop"}, 0.4)
        except (OSError, ValueError, ConnectionError):
            pass
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline and _daemon_lock_held():
            time.sleep(0.1)
    if not _daemon_lock_held() and _status() is None:
        try:
            SOCKET.unlink()
        except FileNotFoundError:
            pass
        print("Codex Pet stopped")
        return 0
    print("Codex Pet did not stop; see log", file=sys.stderr)
    return 1


def _test() -> int:
    if _start() != 0:
        return 1
    sequence = [
        ("idle", 1.4), ("running", 3.0), ("needs_input", 3.0),
        ("ready", 7.0), ("blocked", 2.5),
    ]
    sid = f"pet-test-{os.getpid()}"
    for state, seconds in sequence:
        event = direct_event({"state": state, "session_id": sid,
                              "project": "Pet test", "message": "The test status is visible here."})
        assert event is not None
        if not _send(event):
            print(f"IPC failed at {state}", file=sys.stderr)
            return 1
        time.sleep(0.25)
        observed = _status()
        if observed is None or not observed.get("gui_ready"):
            print(f"GUI failed at {state}; see {LOG}", file=sys.stderr)
            return 1
        if observed["session_count"] == 1 and observed["state"] != state:
            print(f"Unexpected state at {state}: {observed['state']}", file=sys.stderr)
            return 1
        if not isinstance(observed.get("overlay"), dict):
            print(f"Overlay was not created at {state}", file=sys.stderr)
            return 1
        if state == "ready":
            print(f"{state} icon (persistent until the next event)", flush=True)
            time.sleep(seconds)
            after = _status()
            if after is not None and after["session_count"] == 1 and after["state"] != "ready":
                print("Ready did not remain visible through the test interval", file=sys.stderr)
                return 1
            continue
        print(f"{state} ({seconds:g}s)", flush=True)
        time.sleep(seconds)
    end = direct_event({"state": "end", "session_id": sid})
    assert end is not None
    _send(end)
    final = _status()
    if final is None or not final.get("gui_ready"):
        print("GUI unavailable after test", file=sys.stderr)
        return 1
    print("Test complete; Pet returned to idle")
    return 0


def _pet_list() -> int:
    selected = selected_appearance(CONFIG)
    print("Supported pet appearances:")
    for appearance in APPEARANCES:
        marker = "*" if appearance.id == selected else " "
        default = "; default" if appearance.id == DEFAULT_APPEARANCE else ""
        print(f"{marker} {appearance.id} — {appearance.name}{default}: {appearance.description}")
    return 0


def _pet_use(appearance: str) -> int:
    if appearance not in APPEARANCE_BY_ID:
        available = ", ".join(item.id for item in APPEARANCES)
        print(f"Unknown pet appearance '{appearance}'. Available: {available}", file=sys.stderr)
        return 2

    try:
        result = request({"action": "set_appearance", "appearance": appearance}, 0.5)
    except (OSError, ValueError, ConnectionError):
        result = None
    if result is not None and result.get("ok"):
        print(f"Pet appearance set to {APPEARANCE_BY_ID[appearance].name} ({appearance}).")
        return 0

    try:
        save_appearance(CONFIG, appearance)
    except OSError as exc:
        print(f"Could not save pet appearance: {exc}", file=sys.stderr)
        return 1
    if _status() is None:
        print(f"Pet appearance saved as {appearance}; it will be used next time Pet starts.")
    else:
        print(f"Pet appearance saved as {appearance}; run 'codex-pet restart' to apply it.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="codex-pet")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("start", "stop", "restart", "status", "test", "daemon"):
        commands.add_parser(command)
    pet_parser = commands.add_parser("pet", help="list or switch pet appearances")
    pet_commands = pet_parser.add_subparsers(dest="pet_action", required=True)
    pet_commands.add_parser("list", help="list supported pet appearances")
    use_parser = pet_commands.add_parser("use", help="select a pet appearance")
    use_parser.add_argument("appearance")
    args = parser.parse_args()
    if args.command == "pet":
        code = _pet_list() if args.pet_action == "list" else _pet_use(args.appearance)
        raise SystemExit(code)
    if args.command == "daemon":
        daemon.main()
        return
    if args.command == "start":
        code = _start()
    elif args.command == "stop":
        code = _stop()
    elif args.command == "restart":
        code = _stop() or _start()
    elif args.command == "test":
        code = _test()
    else:
        result = _status()
        if result is None:
            print("Codex Pet stopped")
            code = 1
        else:
            gui = "ready" if result["gui_ready"] else f"unavailable ({result['gui_error']})"
            running_count = result.get("running_count", result.get("working_count", 0))
            print(f"Codex Pet running; pid={result['pid']}; GUI={gui}; state={result['state']}; "
                  f"pet={result.get('appearance', DEFAULT_APPEARANCE)}; "
                  f"project={result['project']}; sessions={result['session_count']}; "
                  f"running={running_count}")
            code = 0
    raise SystemExit(code)
