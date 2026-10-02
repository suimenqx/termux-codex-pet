"""Real startup lock and socket boundaries; never use the user's runtime."""
import fcntl
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest


class StartupDeadlineTests(unittest.TestCase):
    def test_concurrent_starts_recover_a_stale_socket_and_share_one_daemon(self):
        # The native broadcast is the external boundary. The real process,
        # locks, hook IPC and daemon are exercised in an isolated home.
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            runtime = home / '.cache/codex-pet'
            runtime.mkdir(parents=True)
            (runtime / 'pet.sock').write_text('stale')
            commands = home / 'commands'
            commands.mkdir()
            shell = shutil.which('sh')
            assert shell is not None
            for name in ('am', 'termux-am'):
                path = commands / name
                path.write_text(f'#!{shell}\nexit 1\n')
                path.chmod(0o700)
            environment = {**os.environ, 'HOME': directory,
                           'PATH': str(commands) + os.pathsep + os.environ['PATH']}
            code = ('import json; from codex_pet.runtime import start_daemon; '
                    'print(json.dumps(start_daemon(2)))')
            processes = [subprocess.Popen([sys.executable, '-c', code], env=environment,
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                          text=True) for _ in range(4)]
            try:
                results = []
                for process in processes:
                    out, err = process.communicate(timeout=5)
                    self.assertEqual(process.returncode, 0, err)
                    results.append(json.loads(out))
                self.assertTrue(all(result and result['ok'] for result in results))
                self.assertEqual(len({result['pid'] for result in results}), 1)
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                    process.communicate()
                subprocess.run([sys.executable, '-c',
                                'from codex_pet.runtime import request; request({"action":"stop"})'],
                               env=environment, capture_output=True, timeout=3)
                deadline = time.monotonic() + 3
                while (runtime / 'pet.sock').exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertFalse((runtime / 'pet.sock').exists())

    def test_released_lock_reuses_the_existing_daemon(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / '.cache/codex-pet'
            runtime.mkdir(parents=True)
            with (runtime / 'start.lock').open('a+b') as lock, \
                    socket.socket(socket.AF_UNIX) as listener:
                listener.bind(str(runtime / 'pet.sock'))
                listener.listen(1)
                listener.settimeout(2)
                fcntl.flock(lock, fcntl.LOCK_EX)
                def respond():
                    time.sleep(0.05)
                    fcntl.flock(lock, fcntl.LOCK_UN)
                    connection, _ = listener.accept()
                    with connection:
                        connection.recv(4096)
                        connection.sendall(b'{"ok":true,"pid":123}\n')
                thread = threading.Thread(target=respond)
                thread.start()
                try:
                    result = subprocess.run(
                        [sys.executable, '-c',
                         'from codex_pet.runtime import start_daemon; '
                         'assert start_daemon(1)["pid"] == 123'],
                        env={**os.environ, 'HOME': directory},
                        capture_output=True, text=True, timeout=3)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue((runtime / 'pet.sock').exists())
                finally:
                    thread.join(3)

    def test_real_hook_fails_open_while_start_lock_is_held(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / '.cache/codex-pet'
            runtime.mkdir(parents=True)
            with (runtime / 'start.lock').open('a+b') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                result = subprocess.run(
                    [sys.executable, 'bin/codex-pet-event'],
                    input=json.dumps({'hook_event_name': 'UserPromptSubmit',
                                      'session_id': 'isolated'}),
                    env={**os.environ, 'HOME': directory},
                    capture_output=True, text=True, timeout=3)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((runtime / 'pet.sock').exists())

    def test_contended_start_lock_consumes_the_startup_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            runtime = home / '.cache/codex-pet'
            runtime.mkdir(parents=True)
            with (runtime / 'start.lock').open('a+b') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                result = subprocess.run(
                    [sys.executable, '-c',
                     'from codex_pet.runtime import start_daemon; '
                     'assert start_daemon(0.05) is None'],
                    env={**os.environ, 'HOME': directory},
                    capture_output=True, text=True, timeout=1,
                )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
