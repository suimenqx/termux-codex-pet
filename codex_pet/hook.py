"""Bounded, fail-open entrypoint for Codex lifecycle hooks."""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback

from .runtime import LOG, directories, notification, send_event
from .state import STATES, direct_event, event_from_hook


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
        if not send_event(event, quick=True):
            notification(event["state"], event["project"], event["message"])
    except Exception as exc:
        _log_hook_error(exc)
        if "event" in locals() and event is not None:
            notification(event["state"], event["project"], event["message"])
