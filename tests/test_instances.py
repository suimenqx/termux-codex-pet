"""Independent CLI processes may share a Codex thread, never lifecycle state."""
import unittest
import errno
import os
import select
import subprocess
import sys
from unittest.mock import patch

from codex_pet.adapters.codex import direct_event, event_from_hook
from codex_pet.state import SessionStore
from codex_pet.processes import ProcessIdentity, ProcessWatcher, discover_owner, process_stat
from codex_pet.adapters.codex import BOOT_ID


def event(name, owner, turn='turn', session='shared', **fields):
    value = event_from_hook({'hook_event_name': name, 'session_id': session,
                             'turn_id': turn, 'instance_id': owner, **fields})
    assert value is not None
    return value


class InstanceStateTests(unittest.TestCase):
    def test_session_end_removes_only_the_process_that_emitted_it(self):
        store = SessionStore()
        store.apply(event('UserPromptSubmit', 'a', 'turn-a'))
        store.apply(event('UserPromptSubmit', 'b', 'turn-b'))
        store.apply(event('SessionEnd', 'a', ''))
        snapshot = store.snapshot()
        self.assertEqual(snapshot['state'], 'running')
        self.assertEqual(snapshot['turn_id'], 'turn-b')
        self.assertEqual(snapshot['instance_count'], 1)

    def test_approval_completion_in_another_process_cannot_clear_waiting(self):
        store = SessionStore()
        store.apply(event('UserPromptSubmit', 'a'))
        store.apply(event('UserPromptSubmit', 'b'))
        store.apply(event('PermissionRequest', 'a', tool_name='Bash', tool_input={'command': 'true'}))
        store.apply(event('PostToolUse', 'b', tool_name='Bash', tool_input={'command': 'true'}))
        self.assertEqual(store.snapshot()['state'], 'needs_input')
        self.assertEqual(store.snapshot()['running_count'], 1)

    def test_unqualified_end_cannot_delete_a_process_qualified_session(self):
        store = SessionStore()
        store.apply(event('UserPromptSubmit', 'a'))
        store.apply(event('SessionEnd', '', ''))
        self.assertEqual(store.snapshot()['state'], 'running')

    def test_closed_process_cannot_be_resurrected_by_a_delayed_hook(self):
        store = SessionStore()
        store.apply(event('UserPromptSubmit', 'a'))
        store.apply(event('PermissionRequest', 'a'))
        store.apply(event('UserPromptSubmit', 'b', 'other'))
        store.close_instance('a')
        self.assertEqual(store.snapshot()['state'], 'running')
        self.assertFalse(store.apply(event('PostToolUse', 'a')))
        self.assertFalse(store.apply(event('UserPromptSubmit', 'a', 'late')))
        self.assertEqual(store.snapshot()['instance_count'], 1)

    def test_approval_totals_and_per_instance_details_have_separate_scope(self):
        store = SessionStore()
        for owner in ('a', 'b'):
            store.apply(event('UserPromptSubmit', owner))
            store.apply(event('PermissionRequest', owner))
        snapshot = store.snapshot()
        self.assertEqual(snapshot['pending_approvals'], 2)
        self.assertEqual(snapshot['selected_pending_approvals'], 1)
        self.assertEqual(snapshot['session_count'], 1)
        self.assertEqual(snapshot['instance_count'], 2)
        self.assertEqual(len(snapshot['instances']), 2)
        self.assertEqual({row['instance_id'] for row in snapshot['instances']}, {'a', 'b'})

    def test_a_legacy_session_name_is_not_a_process_identity(self):
        store = SessionStore()
        store.apply(event('UserPromptSubmit', 'same-name'))
        store.apply(event('UserPromptSubmit', '', session='same-name'))
        self.assertEqual(store.snapshot()['instance_count'], 2)

    def test_checkpoint_retains_instance_isolation_and_closed_owners(self):
        store = SessionStore()
        store.apply(event('UserPromptSubmit', 'a', 'turn-a'))
        store.apply(event('UserPromptSubmit', 'b', 'turn-b'))
        store.close_instance('a')
        restored = SessionStore.restore(store.checkpoint())
        self.assertFalse(restored.apply(event('PostToolUse', 'a', 'turn-a')))
        self.assertTrue(restored.apply(event('PostToolUse', 'b', 'turn-b')))
        self.assertEqual(restored.snapshot()['instance_count'], 1)

    def test_normalization_preserves_owner_evidence_on_ipc_retry(self):
        original = event('UserPromptSubmit', 'owner', producer_pid=123,
                         producer_start_ticks=456, producer_boot_id='boot')
        copied = direct_event(original)
        for key in ('instance_id', 'producer_pid', 'producer_start_ticks', 'producer_boot_id'):
            self.assertEqual(copied[key], original[key])

    def test_legacy_checkpoint_is_upgraded_without_a_ghost_session(self):
        old = SessionStore()
        old.apply(event('UserPromptSubmit', ''))
        saved = old.checkpoint()
        saved['format'] = 1
        for key in ('session_id', 'instance_id', 'producer_pid', 'producer_start_ticks', 'producer_boot_id', 'monitor_error'):
            saved['sessions']['shared'].pop(key)
        restored = SessionStore.restore(saved)
        restored.apply(event('PostToolUse', 'real-owner'))
        self.assertEqual(restored.snapshot()['entry_count'], 1)
        self.assertEqual(restored.snapshot()['state'], 'running')
        self.assertEqual(restored.snapshot()['instance_id'], 'real-owner')

    def test_an_old_qualified_event_cannot_claim_a_legacy_checkpoint(self):
        old = SessionStore()
        original = event('UserPromptSubmit', '')
        old.apply(original)
        restored = SessionStore.restore(old.checkpoint())
        stale = event('PostToolUse', 'wrong-owner')
        stale['emitted_monotonic_ns'] = original['emitted_monotonic_ns'] - 1
        self.assertFalse(restored.apply(stale))
        self.assertEqual(restored.snapshot()['instance_id'], '')

    def test_detail_limit_preserves_complete_totals_and_the_ipc_byte_budget(self):
        import json
        store = SessionStore()
        for index in range(80):
            store.apply(event('UserPromptSubmit', str(index), project='宠物' * 30, session='会话' * 60))
        snapshot = store.snapshot()
        self.assertEqual(snapshot['running_count'], 80)
        self.assertEqual(snapshot['instance_count'], 80)
        self.assertTrue(snapshot['instances_truncated'])
        self.assertLess(len(json.dumps(snapshot).encode()), 60000)


class ProcessOwnershipTests(unittest.TestCase):
    def test_discovery_selects_cli_client_instead_of_app_server_or_hook_helper(self):
        stats = {30: (20, 300, 'S'), 20: (10, 200, 'S'), 10: (1, 100, 'S')}
        def executable(path):
            return '/bin/codex.bin' if str(path).split('/')[-2] in ('20', '10') else '/bin/python'
        def cmdline(path):
            return b'codex\0app-server\0' if '/20/' in str(path) else b'codex\0resume\0'
        with patch('codex_pet.processes.os.getppid', return_value=30), \
                patch('codex_pet.processes.process_stat', side_effect=lambda pid: stats[pid]), \
                patch('codex_pet.processes.os.readlink', side_effect=executable), \
                patch('codex_pet.processes.Path.read_bytes', cmdline):
            found = discover_owner()
        self.assertEqual(found['producer_pid'], 10)
        self.assertEqual(found['producer_start_ticks'], 100)

    def test_orphan_server_does_not_become_a_new_cli_instance(self):
        with patch('codex_pet.processes.os.getppid', return_value=20), \
                patch('codex_pet.processes.process_stat', return_value=(1, 200, 'S')), \
                patch('codex_pet.processes.os.readlink', return_value='/bin/codex.bin'), \
                patch('codex_pet.processes.Path.read_bytes', return_value=b'codex\0app-server\0'):
            found = discover_owner()
        self.assertEqual(found, {'instance_tracking': 'orphan'})
        store = SessionStore()
        self.assertFalse(store.apply(event('PostToolUse', '', **found)))
        self.assertEqual(store.snapshot()['entry_count'], 0)

    def test_real_pidfd_wakes_for_a_killed_process_without_a_hook(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        watcher = ProcessWatcher()
        try:
            _, ticks, _ = process_stat(child.pid)
            identity = ProcessIdentity(child.pid, ticks, BOOT_ID)
            closed, errors = watcher.sync({identity.instance_id: identity})
            self.assertEqual((closed, errors), ({}, {}))
            self.assertEqual(len(watcher.descriptors), 1)
            child.kill()
            child.wait(timeout=3)
            self.assertTrue(select.select(watcher.descriptors, [], [], 1)[0])
            closed, errors = watcher.sync({identity.instance_id: identity})
            self.assertIn(identity.instance_id, closed)
            self.assertEqual(watcher.descriptors, [])
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)
            watcher.close()

    def test_pid_reuse_between_probe_and_fd_open_is_fenced_and_fd_closed(self):
        read_fd, write_fd = os.pipe()
        watcher = ProcessWatcher()
        identity = ProcessIdentity(123, 456, BOOT_ID)
        try:
            with patch('codex_pet.processes.process_alive', side_effect=[True, False]), \
                    patch('codex_pet.processes.open_pidfd', return_value=read_fd):
                closed, errors = watcher.sync({'owner': identity})
            self.assertIn('owner', closed)
            self.assertEqual(watcher.descriptors, [])
            with self.assertRaises(OSError):
                os.fstat(read_fd)
        finally:
            os.close(write_fd)
            watcher.close()

    def test_unavailable_exit_monitor_is_explicit_unknown_and_can_recover(self):
        from test_daemon_notifications import isolated_daemon
        _, ticks, _ = process_stat(os.getpid())
        owner = ProcessIdentity(os.getpid(), ticks, BOOT_ID)
        with isolated_daemon() as daemon:
            with patch('codex_pet.processes.open_pidfd', side_effect=OSError(errno.ENOSYS, 'unsupported')):
                daemon.process({'action': 'event', 'event': event('UserPromptSubmit', owner.instance_id, **owner.fields())})
                snapshot = daemon.status()
                self.assertEqual(snapshot['state'], 'unknown')
                self.assertEqual(snapshot['confidence'], 'uncertain')
                self.assertIn('exit monitoring unavailable', snapshot['state_reason'])
            self.assertEqual(daemon.process({'action': 'status'})['state'], 'running')

    def test_daemon_retires_only_dead_owner_and_persists_the_exit_fence(self):
        from pathlib import Path
        import tempfile
        from codex_pet.delivery import EventJournal
        from test_daemon_notifications import isolated_daemon
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        try:
            _, ticks, _ = process_stat(child.pid)
            owner = ProcessIdentity(child.pid, ticks, BOOT_ID)
            with tempfile.TemporaryDirectory() as directory, isolated_daemon() as daemon:
                daemon.journal = EventJournal(Path(directory))
                for name in ('UserPromptSubmit', 'PermissionRequest'):
                    raw = event(name, owner.instance_id, **owner.fields())
                    daemon.process({'action': 'event', 'event': raw})
                daemon.process({'action': 'event', 'event': event('UserPromptSubmit', 'live', 'other')})
                child.kill()
                child.wait(timeout=3)
                self.assertEqual(daemon.process({'action': 'status'})['state'], 'running')
                saved, _ = daemon.journal.load()
                restored = SessionStore.restore(saved)
                self.assertFalse(restored.apply(raw))
                self.assertEqual(restored.snapshot()['instance_count'], 1)
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)

    def test_failed_exit_checkpoint_retains_evidence_and_retries_without_resurrection(self):
        from pathlib import Path
        import tempfile
        from codex_pet.delivery import EventJournal
        from test_daemon_notifications import isolated_daemon
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        try:
            _, ticks, _ = process_stat(child.pid)
            owner = ProcessIdentity(child.pid, ticks, BOOT_ID)
            with tempfile.TemporaryDirectory() as directory, isolated_daemon() as daemon:
                daemon.journal = EventJournal(Path(directory))
                raw = event('UserPromptSubmit', owner.instance_id, **owner.fields())
                daemon.process({'action': 'event', 'event': raw})
                child.kill()
                child.wait(timeout=3)
                with patch.object(daemon.journal, 'commit', side_effect=OSError('full disk')):
                    self.assertEqual(daemon.process({'action': 'status'})['state'], 'unknown')
                    self.assertEqual(len(daemon.journal.pending()), 1)
                self.assertEqual(daemon.process({'action': 'status'})['state'], 'idle')
                saved, _ = daemon.journal.load()
                self.assertFalse(SessionStore.restore(saved).apply(raw))
                self.assertEqual(daemon.journal.pending(), [])
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)


if __name__ == '__main__':
    unittest.main()
