"""A vanished Termux:GUI service must recover without a new Codex event."""

import threading
import unittest
from unittest.mock import patch

from codex_pet import gui


class GuiRecoveryTests(unittest.TestCase):
    def test_gui_worker_retries_after_two_failed_connections(self) -> None:
        attempts = 0
        third_attempt = threading.Event()

        def unavailable_connection() -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 3:
                third_attempt.set()
            raise ConnectionError("GUI is temporarily unavailable")

        worker = gui.GuiWorker(None, lambda: {}, lambda ready, error: None)
        with patch.object(gui, "Connection", side_effect=unavailable_connection), \
             patch.object(gui, "RECONNECT_DELAYS", (0.0, 0.02, 0.05), create=True), \
             patch.object(gui.LOG, "exception"):
            worker.start()
            try:
                self.assertTrue(third_attempt.wait(0.5))
            finally:
                worker.stop()


if __name__ == "__main__":
    unittest.main()
