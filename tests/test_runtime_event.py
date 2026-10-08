import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from codex_pet import runtime
from codex_pet.adapters.codex import event_from_hook
from codex_pet.delivery import EventJournal
from codex_pet.state import SessionStore


class RuntimeEventSendTests(unittest.TestCase):
    def test_start_waits_past_a_daemon_that_is_automatically_stopping(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime, 'START_LOCK', Path(directory) / 'start.lock'), \
             patch.object(runtime, 'directories'), \
             patch.object(runtime, '_daemon_lock_held', return_value=True), \
             patch.object(runtime, 'request', side_effect=[
                 {'ok': True, 'pid': 1, 'stopping': True}, {'ok': True, 'pid': 2}]):
            self.assertEqual(runtime.start_daemon(1)['pid'], 2)

    def test_committed_final_event_does_not_restart_a_stopped_daemon(self):
        event = event_from_hook({'hook_event_name': 'SessionEnd', 'session_id': 'last'})
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime, 'RUNTIME', Path(directory)), \
             patch.object(runtime, 'request', side_effect=OSError('stopped')) as request, \
             patch.object(runtime, 'start_daemon') as start:
            journal = EventJournal(Path(directory))
            journal.commit(SessionStore().checkpoint(), {
                event['event_id']: {'applied': True, 'revision': 1}})
            self.assertTrue(runtime.send_event(event, quick=True))
            start.assert_not_called()
            request.assert_called_once()

    def test_startup_replay_can_acknowledge_and_exit_before_ipc_retry(self):
        event = event_from_hook({'hook_event_name': 'SessionEnd', 'session_id': 'last'})
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime, 'RUNTIME', Path(directory)), \
             patch.object(runtime, 'request', side_effect=OSError('stopped')) as request:
            def replay(_wait):
                journal = EventJournal(Path(directory))
                journal.commit(SessionStore().checkpoint(), {
                    event['event_id']: {'applied': True, 'revision': 1}})
            with patch.object(runtime, 'start_daemon', side_effect=replay):
                self.assertTrue(runtime.send_event(event, quick=True))
            request.assert_called_once()

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
