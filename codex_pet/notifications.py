"""One bounded notification worker; IPC never waits for Android commands."""
from __future__ import annotations

import threading
import time
from typing import Callable


class NotificationDispatcher:
    def __init__(self, send: Callable[[str, str, str], None]) -> None:
        self.send = send
        self.condition = threading.Condition()
        self.pending: tuple[str, str, str] | None = None
        self.busy = False
        self.stopping = False
        self.thread: threading.Thread | None = None

    def submit(self, value: tuple[str, str, str]) -> None:
        with self.condition:
            if self.stopping:
                return
            self.pending = value
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, name='codex-pet-notify', daemon=True)
                self.thread.start()
            self.condition.notify_all()

    def clear(self) -> None:
        with self.condition:
            self.pending = None

    def _run(self) -> None:
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.pending is not None or self.stopping)
                if self.stopping:
                    return
                value, self.pending = self.pending, None
                self.busy = True
            try:
                if value is not None:
                    self.send(*value)
            finally:
                with self.condition:
                    self.busy = False
                    self.condition.notify_all()

    def flush(self, timeout: float = 2.5) -> bool:
        with self.condition:
            return self.condition.wait_for(lambda: self.pending is None and not self.busy, timeout)

    def stop(self) -> None:
        with self.condition:
            self.pending = None
            self.stopping = True
            self.condition.notify_all()
        if self.thread is not None:
            self.thread.join(timeout=2.5)
