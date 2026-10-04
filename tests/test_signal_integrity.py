"""Wrong activity signals must fail at the real normalization/state seam."""
import tempfile
from pathlib import Path
import unittest
import threading
import time
from unittest.mock import patch

from codex_pet.adapters.codex import direct_event, event_from_hook
from codex_pet.state import SessionStore


def hook(name, turn='t1', session='s1', timestamp=None, **fields):
    event = event_from_hook({'hook_event_name': name, 'session_id': session,
                             'turn_id': turn, **fields})
    assert event is not None
    if timestamp is not None:
        event['timestamp'] = timestamp
        event['emitted_monotonic_ns'] = int(timestamp * 1_000_000_000)
    return event


class SignalIntegrityTests(unittest.TestCase):
    def test_clock_correction_does_not_discard_a_fresh_stop(self):
        store = SessionStore()
        start = hook('UserPromptSubmit', timestamp=100)
        start['emitted_monotonic_ns'] = 1_000_000_000
        stop = hook('Stop', timestamp=90)
        stop['emitted_monotonic_ns'] = 2_000_000_000
        store.apply(start)
        store.apply(stop)
        self.assertEqual(store.snapshot()['state'], 'ready')

    def test_delayed_approval_is_not_lost_behind_an_independent_completion(self):
        store = SessionStore()
        store.apply(hook('UserPromptSubmit', timestamp=1))
        store.apply(hook('PostToolUse', timestamp=3, tool_name='Bash', tool_input={'command': 'b'}))
        store.apply(hook('PermissionRequest', timestamp=2, tool_name='Bash', tool_input={'command': 'a'}))
        self.assertEqual(store.snapshot()['state'], 'needs_input')

    def test_completion_received_before_its_approval_does_not_create_a_phantom_wait(self):
        store = SessionStore()
        store.apply(hook('UserPromptSubmit', timestamp=1))
        store.apply(hook('PostToolUse', timestamp=3, tool_name='Bash', tool_input={'command': 'a'}))
        store.apply(hook('PermissionRequest', timestamp=2, tool_name='Bash', tool_input={'command': 'a'}))
        self.assertEqual(store.snapshot()['state'], 'running')

    def test_normalization_preserves_delivery_identity_time_and_tool_correlation(self):
        original = hook('PermissionRequest', tool_name='Bash',
                        tool_input={'command': 'sensitive-value', 'description': 'approval reason'})
        copied = direct_event(original)
        for key in ('event_id', 'timestamp', 'emitted_monotonic_ns', 'tool_key'):
            self.assertEqual(copied[key], original[key])
        completion = hook('PostToolUse', tool_name='Bash', tool_input={'command': 'sensitive-value'})
        self.assertEqual(completion['tool_key'], original['tool_key'])
        self.assertNotIn('sensitive-value', str(original))

    def test_another_tool_cannot_clear_an_outstanding_permission(self):
        store = SessionStore()
        store.apply(hook('UserPromptSubmit'))
        store.apply(hook('PermissionRequest', tool_name='Bash',
                         tool_input={'command': 'needs-approval'}))
        self.assertEqual(store.snapshot()['confidence'], 'requested')
        store.apply(hook('PostToolUse', tool_name='Bash',
                         tool_input={'command': 'independent-command'}))
        self.assertEqual(store.snapshot()['state'], 'needs_input')
        store.apply(hook('PostToolUse', tool_name='Bash',
                         tool_input={'command': 'needs-approval'}))
        self.assertEqual(store.snapshot()['state'], 'running')
        self.assertEqual(store.snapshot()['confidence'], 'observed')

    def test_two_permissions_need_two_matching_completions(self):
        store = SessionStore()
        store.apply(hook('UserPromptSubmit'))
        for command in ('first', 'second'):
            store.apply(hook('PermissionRequest', tool_name='Bash',
                             tool_input={'command': command}))
        store.apply(hook('PostToolUse', tool_name='Bash', tool_input={'command': 'first'}))
        self.assertEqual(store.snapshot()['state'], 'needs_input')
        store.apply(hook('PostToolUse', tool_name='Bash', tool_input={'command': 'second'}))
        self.assertEqual(store.snapshot()['state'], 'running')

    def test_duplicate_tool_completion_cannot_consume_a_second_identical_approval(self):
        store = SessionStore()
        store.apply(hook('UserPromptSubmit'))
        for _ in range(2):
            store.apply(hook('PermissionRequest', tool_name='Bash', tool_input={'command': 'a'}))
        done = hook('PostToolUse', tool_name='Bash', tool_input={'command': 'a'}, tool_use_id='one')
        store.apply(done)
        store.apply(hook('PostToolUse', tool_name='Bash', tool_input={'command': 'a'}, tool_use_id='one'))
        self.assertEqual(store.snapshot()['state'], 'needs_input')
        store.apply(hook('PostToolUse', tool_name='Bash', tool_input={'command': 'a'}, tool_use_id='two'))
        self.assertEqual(store.snapshot()['state'], 'running')

    def test_missing_turn_id_cannot_finish_a_known_new_turn(self):
        store = SessionStore()
        store.apply(hook('UserPromptSubmit', 't1'))
        store.apply(hook('UserPromptSubmit', 't2'))
        self.assertFalse(store.apply(hook('Stop', '')))
        self.assertEqual(store.snapshot()['state'], 'unknown')
        self.assertEqual(store.sessions['s1'].state, 'running')
        store.apply(hook('PostToolUse', 't2'))
        self.assertEqual(store.snapshot()['state'], 'running')

    def test_late_start_and_end_do_not_overwrite_newer_evidence(self):
        store = SessionStore()
        store.apply(hook('UserPromptSubmit', 't1', timestamp=10))
        store.apply(hook('UserPromptSubmit', 't2', timestamp=20))
        for name in ('UserPromptSubmit', 'SessionStart', 'SessionEnd'):
            self.assertFalse(store.apply(hook(name, 't1', timestamp=15, source='resume')))
        self.assertEqual(store.snapshot()['state'], 'running')
        self.assertEqual(store.snapshot()['turn_id'], 't2')

    def test_repeated_session_start_does_not_reset_running(self):
        store = SessionStore()
        store.apply(hook('UserPromptSubmit'))
        store.apply(hook('SessionStart', '', source='startup'))
        self.assertEqual(store.snapshot()['state'], 'running')

    def test_running_session_wins_over_another_sessions_completion(self):
        store = SessionStore()
        store.apply(hook('UserPromptSubmit', session='done'))
        store.apply(hook('Stop', session='done'))
        store.apply(hook('UserPromptSubmit', session='active'))
        self.assertEqual(store.snapshot()['state'], 'running')
        self.assertEqual(store.snapshot()['ready_count'], 1)

    def test_checkpoint_retains_pending_permissions_and_marks_recovery_unknown(self):
        store = SessionStore()
        store.apply(hook('UserPromptSubmit'))
        store.apply(hook('PermissionRequest', tool_name='Bash', tool_input={'command': 'a'}))
        restored = SessionStore.restore(store.checkpoint())
        self.assertEqual(restored.snapshot()['state'], 'unknown')
        restored.apply(hook('PostToolUse', tool_name='Bash', tool_input={'command': 'b'}))
        self.assertEqual(restored.snapshot()['state'], 'needs_input')

    def test_replaying_checkpoint_evidence_cannot_confirm_a_recovered_session(self):
        store = SessionStore()
        start = hook('UserPromptSubmit')
        store.apply(start)
        restored = SessionStore.restore(store.checkpoint())
        self.assertFalse(restored.apply(start))
        self.assertEqual(restored.snapshot()['state'], 'unknown')


class DeliveryIntegrityTests(unittest.TestCase):
    def test_status_reads_one_immutable_submission_during_connection_teardown(self):
        from codex_pet.gui import SubmittedStatus
        from test_daemon_notifications import FakeGui, isolated_daemon
        class ClosingGui(FakeGui):
            reads = 0
            @property
            def submitted_status(self):
                self.reads += 1
                return SubmittedStatus(1, 'event', 'running', 1, 0, 0) if self.reads == 1 else None
        with isolated_daemon() as daemon:
            daemon.gui = ClosingGui()
            self.assertEqual(daemon.status()['submitted']['revision'], 1)
            self.assertIsNone(daemon.status()['submitted'])

    def test_inbox_orders_by_source_clock_even_when_wall_clock_moves_backwards(self):
        from codex_pet.delivery import EventJournal
        with tempfile.TemporaryDirectory() as directory:
            journal = EventJournal(Path(directory))
            start, stop = hook('UserPromptSubmit', timestamp=100), hook('Stop', timestamp=90)
            start['emitted_monotonic_ns'], stop['emitted_monotonic_ns'] = 1_000_000_000, 2_000_000_000
            journal.publish(start)
            journal.publish(stop)
            self.assertEqual([value['event_id'] for value in journal.pending()],
                             [start['event_id'], stop['event_id']])

    def test_checkpoint_failure_keeps_the_stop_and_displays_uncertainty_until_recovery(self):
        from codex_pet.delivery import EventJournal
        from test_daemon_notifications import isolated_daemon
        with tempfile.TemporaryDirectory() as directory, isolated_daemon() as daemon:
            daemon.journal = EventJournal(Path(directory))
            start, stop = hook('UserPromptSubmit'), hook('Stop')
            daemon.process({'action': 'event', 'event': start})
            with patch.object(daemon.journal, 'commit', side_effect=OSError('full disk')):
                result = daemon.process({'action': 'event', 'event': stop})
                self.assertFalse(result['ok'])
                self.assertEqual(daemon.status()['state'], 'unknown')
                self.assertEqual(len(daemon.journal.pending()), 1)
            self.assertEqual(daemon.process({'action': 'status'})['state'], 'ready')
            self.assertEqual(daemon.journal.pending(), [])

    def test_checkpoint_failure_clears_a_stale_fallback_notification(self):
        from codex_pet import daemon as module
        from codex_pet.delivery import EventJournal
        from test_daemon_notifications import isolated_daemon
        with tempfile.TemporaryDirectory() as directory, isolated_daemon() as daemon, \
                patch.object(module, 'notification') as notice:
            daemon.journal = EventJournal(Path(directory))
            daemon.gui_error = 'disconnected'
            daemon.process({'action': 'event', 'event': hook('UserPromptSubmit')})
            daemon.process({'action': 'event', 'event': hook('PermissionRequest')})
            self.assertTrue(daemon.notifications.flush(1))
            self.assertEqual(notice.call_args.args[0], 'needs_input')
            with patch.object(daemon.journal, 'commit', side_effect=OSError('full disk')):
                daemon.process({'action': 'event', 'event': hook('Stop')})
                self.assertTrue(daemon.notifications.flush(1))
                self.assertEqual(notice.call_args.args[0], 'clear')
                daemon._fallback()
                self.assertTrue(daemon.notifications.flush(1))
                self.assertEqual(notice.call_args.args[0], 'clear')

    def test_slow_android_notification_does_not_hold_up_a_state_update(self):
        from codex_pet import daemon as module
        from test_daemon_notifications import isolated_daemon
        started, release = threading.Event(), threading.Event()
        def slow_notification(*args):
            started.set()
            release.wait(2)
        with isolated_daemon() as daemon, patch.object(module, 'notification', side_effect=slow_notification):
            daemon.gui_error = 'lost'
            before = time.monotonic()
            try:
                daemon.process({'action': 'event', 'event': hook('UserPromptSubmit')})
                daemon.process({'action': 'event', 'event': hook('PermissionRequest')})
                self.assertTrue(started.wait(.5))
                result = daemon.process({'action': 'event', 'event': hook('PostToolUse')})
                self.assertEqual(result['state'], 'running')
                self.assertLess(time.monotonic() - before, .5)
            finally:
                release.set()
                self.assertTrue(daemon.notifications.flush(1))

    def test_unacknowledged_stop_survives_sender_and_daemon_restart(self):
        from codex_pet.delivery import EventJournal
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = EventJournal(root)
            start, stop = hook('UserPromptSubmit'), hook('Stop')
            journal.publish(start)
            store = SessionStore()
            store.apply(start)
            journal.commit(store.checkpoint(), {start['event_id']: {'applied': True}})
            journal.remove(start)
            journal.publish(stop)
            restarted = EventJournal(root)
            saved, receipts = restarted.load()
            store = SessionStore.restore(saved)
            for event in restarted.pending():
                if event['event_id'] not in receipts:
                    receipts[event['event_id']] = {'applied': store.apply(event)}
            restarted.commit(store.checkpoint(), receipts)
            self.assertEqual(store.snapshot()['state'], 'ready')
            self.assertTrue(receipts[stop['event_id']]['applied'])
            # Crash after checkpoint, before deleting the event, cannot replay it.
            saved_again, receipts_again = restarted.load()
            self.assertIn(stop['event_id'], receipts_again)
            self.assertEqual(saved_again['sessions']['s1']['state'], 'ready')


if __name__ == '__main__':
    unittest.main()
