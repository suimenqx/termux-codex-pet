import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from codex_pet import runtime


class RuntimeEventSendTests(unittest.TestCase):
    def test_send_event_starts_daemon_and_retries_with_quick_deadlines(self) -> None:
        event = {"state": "running", "session_id": "s1"}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime, 'RUNTIME', Path(directory)), \
             patch.object(runtime, "request", side_effect=[OSError("stopped"), {"ok": True}]) as request, \
             patch.object(runtime, "start_daemon") as start_daemon:
            self.assertTrue(runtime.send_event(event, quick=True))

        first, second = request.call_args_list
        self.assertEqual(first.args[0]['event']['state'], 'running')
        self.assertEqual(first.args, second.args)
        self.assertEqual(first.args[1], 0.2)
        start_daemon.assert_called_once_with(0.65)


if __name__ == "__main__":
    unittest.main()
