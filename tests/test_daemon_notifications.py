from contextlib import contextmanager
import tempfile
import threading
from pathlib import Path
import unittest
from unittest.mock import patch

from codex_pet import daemon
from codex_pet.adapters.codex import direct_event


class FakeGui:
    overlay_status = None

    def wake(self) -> None:
        pass


@contextmanager
def isolated_daemon():
    with tempfile.TemporaryDirectory() as directory:
        config = Path(directory) / "config.json"
        with patch.object(daemon, "CONFIG", config), \
             patch.object(daemon, "GuiWorker", return_value=FakeGui()):
            instance = daemon.Daemon()
        try:
            yield instance
        finally:
            instance.signal_read.close()
            instance.signal_write.close()


def needs_input_event():
    event = direct_event({
        "state": "needs_input",
        "session_id": "s1",
        "project": "repo",
        "message": "Approve this",
    })
    assert event is not None
    return event


class DaemonNotificationTests(unittest.TestCase):
    def test_concurrent_fallback_for_the_same_state_sends_once(self) -> None:
        notification_started = threading.Event()
        release_notification = threading.Event()
        calls: list[tuple[str, str, str]] = []
        calls_lock = threading.Lock()

        def delayed_notification(state: str, project: str, message: str) -> None:
            with calls_lock:
                calls.append((state, project, message))
            notification_started.set()
            release_notification.wait(timeout=2)

        with isolated_daemon() as instance, \
             patch.object(daemon, "notification", side_effect=delayed_notification):
            with instance.lock:
                instance.gui_ready = False
                instance.gui_error = "disconnected"
            instance.sessions.apply(needs_input_event())

            first = threading.Thread(target=instance._fallback, daemon=True)
            second = threading.Thread(target=instance._fallback, daemon=True)
            first.start()
            self.assertTrue(notification_started.wait(timeout=1))
            second.start()
            second.join(timeout=1)
            second_completed_before_release = not second.is_alive()
            release_notification.set()
            first.join(timeout=1)
            second.join(timeout=1)

            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertTrue(second_completed_before_release)
            self.assertEqual(calls, [("needs_input", "repo", "Approve this")])

    def test_gui_recovery_clears_the_notification_deduplication_key(self) -> None:
        with isolated_daemon() as instance, patch.object(daemon, "notification") as notification:
            instance.sessions.apply(needs_input_event())
            instance.gui_status(False, "disconnected")
            instance.gui_status(True, "")
            instance.gui_status(False, "disconnected")

            self.assertEqual(notification.call_count, 2)
            self.assertEqual(instance.last_notification,
                             ("needs_input", "repo", "Approve this"))

    def test_stale_fallback_is_ignored_after_gui_recovery(self) -> None:
        with isolated_daemon() as instance, patch.object(daemon, "notification") as notification:
            instance.sessions.apply(needs_input_event())
            instance.gui_status(True, "")
            instance._fallback()

        notification.assert_not_called()


if __name__ == "__main__":
    unittest.main()
