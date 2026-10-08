"""The overlay follows terminal clients even while their shared server survives."""
from contextlib import contextmanager
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest.mock import patch

from codex_pet.adapters.codex import BOOT_ID, event_from_hook
from codex_pet.delivery import EventJournal
from codex_pet.processes import ProcessIdentity, discover_clients, process_stat
from codex_pet.state import SessionStore
from test_daemon_notifications import isolated_daemon


@contextmanager
def codex_clients(*children):
    """Expose real child lifetimes as native Codex clients in a private /proc view."""
    iterdir, read_bytes, readlink = Path.iterdir, Path.read_bytes, os.readlink
    paths = [Path('/proc') / str(child.pid) for child in children]

    def entries(path):
        return iter(paths) if path == Path('/proc') else iterdir(path)

    def executable(path):
        if Path(path).parent in paths and Path(path).name == 'exe':
            return '/bin/codex.bin'
        return readlink(path)

    def cmdline(path):
        if path.parent in paths and path.name == 'cmdline':
            return b'codex\0resume\0'
        return read_bytes(path)

    with patch.object(Path, 'iterdir', entries), \
            patch.object(Path, 'read_bytes', cmdline), \
            patch('codex_pet.processes.os.readlink', side_effect=executable):
        yield


class SharedClientLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.children = []

    def tearDown(self):
        for child in self.children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)

    def child(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        self.children.append(child)
        return child

    def start_session(self, daemon, server):
        _, ticks, _ = process_stat(server.pid)
        owner = ProcessIdentity(server.pid, ticks, BOOT_ID)
        event = event_from_hook({'hook_event_name': 'UserPromptSubmit',
                                 'session_id': 'shared-thread', **owner.fields(shared=True)})
        self.assertTrue(daemon.process({'action': 'event', 'event': event})['ok'])

    def test_last_terminal_exit_stops_pet_while_shared_server_stays_alive(self):
        server, client = self.child(), self.child()
        with codex_clients(client), isolated_daemon() as daemon:
            self.start_session(daemon, server)
            self.assertFalse(daemon._should_stop_automatically())
            self.assertEqual(len(daemon.clients.descriptors), 1)
            client.kill()
            client.wait(timeout=3)
            self.assertTrue(select.select(daemon.clients.descriptors, [], [], 1)[0])
            daemon.drain_events()
            self.assertIsNone(server.poll())
            self.assertTrue(daemon._should_stop_automatically())
            self.assertEqual(daemon.clients.descriptors, [])
            # Closing Pet must not invent SessionEnd or seal the live server.
            self.assertEqual(daemon.sessions.snapshot()['entry_count'], 1)
            self.assertEqual(daemon.sessions.closed_instances, {})

    def test_another_terminal_keeps_pet_alive_then_last_exit_stops_it(self):
        server, first, second = self.child(), self.child(), self.child()
        with codex_clients(first, second), isolated_daemon() as daemon:
            self.start_session(daemon, server)
            self.assertEqual(len(daemon.clients.descriptors), 2)
            first.kill()
            first.wait(timeout=3)
            daemon.drain_events()
            self.assertFalse(daemon._should_stop_automatically())
            self.assertEqual(len(daemon.clients.descriptors), 1)
            second.kill()
            second.wait(timeout=3)
            daemon.drain_events()
            self.assertTrue(daemon._should_stop_automatically())

    def test_recovered_shared_sessions_without_clients_stop_before_gui_start(self):
        server, client = self.child(), self.child()
        with tempfile.TemporaryDirectory() as directory:
            journal = EventJournal(Path(directory))
            with codex_clients(client), isolated_daemon() as original:
                original.journal = journal
                self.start_session(original, server)
            client.kill()
            client.wait(timeout=3)
            with codex_clients(), isolated_daemon() as recovered:
                recovered.journal = journal
                recovered.restore_events()
                recovered._stop_if_sessions_ended()
                self.assertTrue(recovered.stopping)
                self.assertEqual(recovered.sessions.snapshot()['entry_count'], 1)

    def test_a_new_client_can_resume_preserved_shared_evidence(self):
        server, first, second = self.child(), self.child(), self.child()
        with codex_clients(first), isolated_daemon() as original:
            self.start_session(original, server)
            first.kill()
            first.wait(timeout=3)
            original.drain_events()
            self.assertTrue(original._should_stop_automatically())
            saved = original.sessions.checkpoint()
        with codex_clients(second), isolated_daemon() as resumed:
            resumed.sessions = SessionStore.restore(saved)
            resumed.drain_events()
            self.assertFalse(resumed._should_stop_automatically())
            self.start_session(resumed, server)
            self.assertEqual(resumed.status()['state'], 'running')

    def test_background_hook_without_clients_is_committed_before_stop(self):
        server = self.child()
        with tempfile.TemporaryDirectory() as directory, codex_clients(), isolated_daemon() as daemon:
            daemon.journal = EventJournal(Path(directory))
            self.start_session(daemon, server)
            self.assertTrue(daemon._should_stop_automatically())
            saved, receipts = daemon.journal.load()
            self.assertEqual(len(saved['sessions']), 1)
            self.assertTrue(receipts)
            self.assertEqual(daemon.journal.pending(), [])
            self.assertFalse(daemon.stopping)

    def test_client_exit_cannot_close_a_standalone_or_manual_session(self):
        for shared in (False, True):
            with self.subTest(shared=shared):
                server, client = self.child(), self.child()
                with codex_clients(client), isolated_daemon() as daemon:
                    if shared:
                        self.start_session(daemon, server)
                        extra = {'state': 'running', 'session_id': 'manual'}
                    else:
                        _, ticks, _ = process_stat(server.pid)
                        extra = event_from_hook({'hook_event_name': 'UserPromptSubmit',
                                                 'session_id': 'standalone',
                                                 **ProcessIdentity(server.pid, ticks, BOOT_ID).fields()})
                    daemon.process({'action': 'event', 'event': extra})
                    client.kill()
                    client.wait(timeout=3)
                    daemon.drain_events()
                    self.assertFalse(daemon._should_stop_automatically())

    def test_failed_client_discovery_is_unknown_and_does_not_infer_exit(self):
        server = self.child()
        with isolated_daemon() as daemon, \
                patch('codex_pet.daemon.discover_clients', return_value=({}, 'Codex client discovery unavailable')):
            self.start_session(daemon, server)
            self.assertFalse(daemon._should_stop_automatically())
            self.assertEqual(daemon.status()['state'], 'unknown')
            self.assertIn('client discovery', daemon.status()['state_reason'])

    def test_failed_client_monitor_is_unknown_then_recovers_on_a_new_event(self):
        server, client = self.child(), self.child()
        with codex_clients(client), isolated_daemon() as daemon:
            with patch.object(daemon.clients, 'sync', return_value=({}, {'client': 'Codex producer exit monitoring unavailable'})):
                self.start_session(daemon, server)
                self.assertFalse(daemon._should_stop_automatically())
                self.assertEqual(daemon.status()['state'], 'unknown')
                self.assertIn('client exit monitoring unavailable', daemon.status()['state_reason'])
            daemon.drain_events()
            self.assertEqual(daemon.status()['state'], 'running')
            self.assertEqual(len(daemon.clients.descriptors), 1)

    def test_client_exit_waits_for_retained_checkpoint_recovery(self):
        server, client = self.child(), self.child()
        with tempfile.TemporaryDirectory() as directory, codex_clients(client), isolated_daemon() as daemon:
            daemon.journal = EventJournal(Path(directory))
            self.start_session(daemon, server)
            with patch.object(daemon.journal, 'commit', side_effect=OSError('full disk')):
                _, ticks, _ = process_stat(server.pid)
                daemon.process({'action': 'event', 'event': event_from_hook({
                    'hook_event_name': 'Stop', 'session_id': 'shared-thread',
                    **ProcessIdentity(server.pid, ticks, BOOT_ID).fields(shared=True)})})
                client.kill()
                client.wait(timeout=3)
                daemon.drain_events()
                self.assertFalse(daemon._should_stop_automatically())
            daemon.drain_events()
            self.assertTrue(daemon._should_stop_automatically())
            self.assertEqual(daemon.journal.pending(), [])

    def test_discovery_omission_keeps_verified_client_watch_until_exit(self):
        server, client = self.child(), self.child()
        with codex_clients(client), isolated_daemon() as daemon:
            self.start_session(daemon, server)
            with patch('codex_pet.daemon.discover_clients', return_value=({}, '')):
                daemon.drain_events()
                self.assertFalse(daemon._should_stop_automatically())
                self.assertEqual(len(daemon.clients.descriptors), 1)
                client.kill()
                client.wait(timeout=3)
                self.assertTrue(select.select(daemon.clients.descriptors, [], [], 1)[0])
                daemon.drain_events()
                self.assertTrue(daemon._should_stop_automatically())

    def test_discovery_excludes_managed_and_local_app_servers_and_mcp_servers(self):
        server, client = self.child(), self.child()
        for command in (b'codex\0app-server\0--managed-daemon\0',
                        b'codex\0app-server\0', b'codex\0mcp-server\0'):
            with self.subTest(command=command), codex_clients(server, client), \
                    patch.object(Path, 'read_bytes', lambda path: command if path.parent.name == str(server.pid)
                                 else b'codex\0resume\0'):
                clients, error = discover_clients()
                self.assertEqual(error, '')
                self.assertEqual([identity.pid for identity in clients.values()], [client.pid])

    def test_discovery_failure_and_missing_boot_identity_are_explicit(self):
        with patch.object(Path, 'iterdir', side_effect=PermissionError('denied')):
            clients, error = discover_clients()
            self.assertEqual(clients, {})
            self.assertIn('discovery unavailable', error)
        with patch('codex_pet.processes.BOOT_ID', ''):
            clients, error = discover_clients()
            self.assertEqual(clients, {})
            self.assertIn('boot identity', error)

    def test_background_ready_hook_without_clients_does_not_notify(self):
        server = self.child()
        with codex_clients(), isolated_daemon() as daemon:
            daemon.gui_error = 'unavailable'
            _, ticks, _ = process_stat(server.pid)
            with patch('codex_pet.daemon.notification') as notification:
                daemon.process({'action': 'event', 'event': event_from_hook({
                    'hook_event_name': 'Stop', 'session_id': 'shared-thread',
                    **ProcessIdentity(server.pid, ticks, BOOT_ID).fields(shared=True)})})
                self.assertTrue(daemon._should_stop_automatically())
                self.assertTrue(daemon.notifications.flush(1))
                notification.assert_not_called()

    def test_last_client_exit_clears_the_gui_outage_notification(self):
        server, client = self.child(), self.child()
        with codex_clients(client), isolated_daemon() as daemon, \
                patch('codex_pet.daemon.notification') as notification:
            daemon.gui_error = 'unavailable'
            self.start_session(daemon, server)
            _, ticks, _ = process_stat(server.pid)
            daemon.process({'action': 'event', 'event': event_from_hook({
                'hook_event_name': 'Stop', 'session_id': 'shared-thread',
                **ProcessIdentity(server.pid, ticks, BOOT_ID).fields(shared=True)})})
            self.assertTrue(daemon.notifications.flush(1))
            self.assertEqual(notification.call_args.args[0], 'ready')
            client.kill()
            client.wait(timeout=3)
            daemon.drain_events()
            daemon._stop_if_sessions_ended()
            self.assertTrue(daemon.notifications.flush(1))
            self.assertEqual(notification.call_args.args[0], 'clear')

    def test_daemon_select_loop_closes_gui_on_client_exit_without_any_ipc(self):
        server, client = self.child(), self.child()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, server_ticks, _ = process_stat(server.pid)
            _, client_ticks, _ = process_stat(client.pid)
            journal = EventJournal(root)
            journal.publish(event_from_hook({'hook_event_name': 'UserPromptSubmit',
                'session_id': 'shared-thread',
                **ProcessIdentity(server.pid, server_ticks, BOOT_ID).fields(shared=True)}))
            script = textwrap.dedent('''
                from pathlib import Path
                import sys
                from types import SimpleNamespace
                from codex_pet import daemon as module
                from codex_pet.adapters.codex import BOOT_ID
                from codex_pet.delivery import EventJournal
                from codex_pet.processes import ProcessIdentity
                root = Path(sys.argv[1])
                module.RUNTIME = root
                module.CONFIG = root / 'config.json'
                module.SOCKET = root / 'pet.sock'
                module.EVENT_WAKE = root / 'events.sock'
                module.DAEMON_LOCK = root / 'daemon.lock'
                module.directories = lambda: None
                identity = ProcessIdentity(int(sys.argv[2]), int(sys.argv[3]), BOOT_ID)
                module.discover_clients = lambda: ({identity.instance_id: identity}, '')
                module.GuiWorker = lambda *args, **kwargs: SimpleNamespace(
                    start=lambda: (root / 'gui-started').touch(),
                    stop=lambda: (root / 'gui-stopped').touch(), wake=lambda: None)
                module.Daemon(journal=EventJournal(root)).run()
            ''')
            worker = subprocess.Popen([sys.executable, '-c', script, directory,
                                       str(client.pid), str(client_ticks)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.children.append(worker)
            deadline = time.monotonic() + 4
            while not (root / 'gui-started').exists() and worker.poll() is None and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue((root / 'gui-started').exists())
            # No request, hook, or status call wakes the daemon after this point.
            client.kill()
            client.wait(timeout=3)
            stdout, stderr = worker.communicate(timeout=4)
            self.assertEqual(worker.returncode, 0, stderr.decode())
            self.assertTrue((root / 'gui-stopped').exists())
            self.assertFalse((root / 'pet.sock').exists())
            self.assertFalse((root / 'events.sock').exists())
            self.assertIsNone(server.poll())
            saved, _ = journal.load()
            self.assertEqual(len(saved['sessions']), 1)
            self.assertEqual(saved['closed_instances'], [])


if __name__ == '__main__':
    unittest.main()
