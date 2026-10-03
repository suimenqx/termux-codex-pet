"""Real installation, hooks, IPC, native-wire output and rollback in a temp home."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home, self.prefix, self.source = (
            self.root / name for name in ('home', 'prefix', 'source'))
        self.home.mkdir()
        (self.prefix / 'bin').mkdir(parents=True)
        for name in ('bin', 'codex_pet'):
            shutil.copytree(ROOT / name, self.source / name,
                            ignore=shutil.ignore_patterns('__pycache__'))
        for name in ('install.sh', 'uninstall.sh'):
            shutil.copy2(ROOT / name, self.source / name)
        recorder = ROOT / 'tests/native_gui_recorder.py'
        for name in ('termux-am', 'am'):
            path = self.prefix / 'bin' / name
            path.write_text(
                f'#!{sys.executable}\nimport runpy\nrunpy.run_path({str(recorder)!r}, run_name="__main__")\n')
            path.chmod(0o700)
        # Fault injection is an external executable boundary, not an app mock.
        driver = self.prefix / 'bin/python'
        driver.write_text(f'''#!{sys.executable}
import os, sys, subprocess
from pathlib import Path
fault = Path(os.environ['PET_TEST_ROOT']) / 'fail-restart'
if len(sys.argv) == 3 and Path(sys.argv[1]).name == 'codex-pet' and sys.argv[2] == 'restart' and fault.exists():
    fault.unlink()
    subprocess.run([sys.executable, sys.argv[1], 'stop'], check=True)
    raise SystemExit(23)
os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
''')
        driver.chmod(0o700)
        notification = self.prefix / 'bin/termux-notification'
        notification.write_text(f'#!{sys.executable}\n')
        notification.chmod(0o700)
        self.env = {**os.environ, 'HOME': str(self.home), 'PREFIX': str(self.prefix),
                    'PATH': str(self.prefix / 'bin') + os.pathsep + os.environ['PATH'],
                    'PYTHONPATH': str(ROOT), 'PET_TEST_ROOT': str(self.root)}
        self.app = self.home / '.local/share/codex-pet'
        self.cli = self.home / '.local/bin/codex-pet'
        self.event = self.home / '.local/bin/codex-pet-event'
        self.config = self.home / '.config/codex-pet/config.json'
        self.config.parent.mkdir(parents=True)
        self.config.write_text(
            '{"appearance":"akita","position":{"x":130,"y":240},"theme":"mine"}\n')
        self.hooks = self.home / '.codex/hooks.json'
        self.hooks.parent.mkdir()
        self.user_hooks = {'hooks': {
            'Stop': [{'hooks': [{'type': 'command', 'command': '/user/own-hook'}]}]}}
        self.hooks.write_text(json.dumps(self.user_hooks))

    def run_command(self, command, *, input=None, success=True):
        result = subprocess.run([str(x) for x in command], env=self.env, cwd=ROOT,
                                text=True, input=input, capture_output=True, timeout=35)
        if success:
            self.assertEqual(result.returncode, 0,
                             result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0,
                                result.stdout + result.stderr)
        return result

    def request(self, payload):
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(1)
            client.connect(str(self.home / '.cache/codex-pet/pet.sock'))
            client.sendall(json.dumps(payload).encode() + b'\n')
            return json.loads(client.makefile('rb').readline())

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.02)
        self.fail('Observable output did not arrive before deadline')

    def frames(self):
        path = self.root / 'renderer.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def tearDown(self):
        try:
            if self.cli.is_file() and 'CODEX_PET_MANAGED' in self.cli.read_text():
                subprocess.run([str(self.cli), 'stop'],
                               env=self.env, capture_output=True, timeout=20)
        finally:
            self.temp.cleanup()

    def test_install_repeat_move_checkout_failed_upgrade_rollback_and_uninstall(self):
        foreign = self.prefix / 'bin/codex-pet-event'
        foreign.write_text('user-owned command\n')
        self.run_command(['bash', self.source / 'install.sh'])
        first = (self.app / 'current').resolve()
        self.run_command(['bash', self.source / 'install.sh'])
        second = (self.app / 'current').resolve()
        self.assertNotEqual(first, second)
        self.assertEqual((self.app / 'previous').resolve(), first)
        before = self.request({'action': 'status'})
        moved = self.root / 'moved-checkout'
        self.source.rename(moved)
        self.source = moved
        self.run_command([self.cli, 'pet', 'use', 'robot'])
        self.wait_for(lambda: any(row.get('size') == [
                      64, 64] for row in self.frames()))
        offset = len(self.frames())
        self.run_command([self.cli, 'pet', 'use', 'pixel_dog'])
        from PIL import Image
        with Image.open(second / 'codex_pet/assets/pixel_dog/frames/standing/00.png') as img:
            expected = hashlib.sha256(img.tobytes()).hexdigest()
        self.wait_for(lambda: any(row.get('rgba_sha256') == expected
                                  for row in self.frames()[offset:]))
        self.assertEqual(json.loads(self.config.read_text()), {
            'appearance': 'pixel_dog', 'position': {'x': 130, 'y': 240}, 'theme': 'mine'})
        self.assertIn('CC0', (second / 'codex_pet/assets/pixel_dog/LICENSE.txt').read_text())
        # Reinstallation also preserves the new selection and unrelated settings.
        self.run_command(['bash', self.source / 'install.sh'])
        first, second = second, (self.app / 'current').resolve()
        self.assertEqual(json.loads(self.config.read_text()), {
            'appearance': 'pixel_dog', 'position': {'x': 130, 'y': 240}, 'theme': 'mine'})
        self.run_command([self.cli, 'pet', 'use', 'akita'])
        saved_config, saved_hooks = self.config.read_bytes(), self.hooks.read_bytes()
        saved_releases = set(self.app.joinpath('releases').iterdir())
        (self.root / 'fail-restart').touch()
        self.run_command(['bash', self.source / 'install.sh'], success=False)
        self.assertEqual((self.app / 'current').resolve(), second)
        self.assertEqual((self.app / 'previous').resolve(), first)
        self.assertEqual(set(self.app.joinpath(
            'releases').iterdir()), saved_releases)
        self.assertEqual(self.config.read_bytes(), saved_config)
        self.assertEqual(self.hooks.read_bytes(), saved_hooks)
        restored = self.request({'action': 'status'})
        self.assertTrue(restored['gui_ready'])
        self.assertNotEqual(restored['pid'], before['pid'])
        self.run_command([self.cli, 'stop'])
        self.run_command([sys.executable, '-m', 'codex_pet.deployment',
                         'rollback', '--source', self.source, '--home', self.home])
        self.assertEqual((self.app / 'current').resolve(), first)
        self.run_command([self.cli, 'start'])
        self.assertTrue(self.request({'action': 'status'})['gui_ready'])
        self.run_command(['bash', self.source / 'uninstall.sh'])
        self.assertEqual(foreign.read_text(), 'user-owned command\n')
        self.assertEqual(json.loads(self.hooks.read_text()), self.user_hooks)
        self.assertEqual(self.config.read_bytes(), saved_config)
        self.assertFalse(self.app.exists())

    def test_invalid_activation_target_and_pack_keep_user_files(self):
        self.app.mkdir(parents=True)
        target = self.app / 'current'
        target.write_text('foreign runtime path')
        original = self.config.read_bytes(), self.hooks.read_bytes()
        result = self.run_command(
            ['bash', self.source / 'install.sh'], success=False)
        self.assertIn('non-symlink runtime path', result.stderr)
        self.assertEqual(target.read_text(), 'foreign runtime path')
        target.unlink()
        pack = self.source / 'codex_pet/assets/akita/pet.json'
        pack.write_text('{"schema_version":999}')
        self.run_command(['bash', self.source / 'install.sh'], success=False)
        self.assertFalse(target.exists())
        self.assertEqual(
            (self.config.read_bytes(), self.hooks.read_bytes()), original)

    def test_real_hooks_ipc_frames_turn_closure_and_position(self):
        self.run_command(['bash', self.source / 'install.sh'])

        def hook(name, turn='t1'):
            self.run_command([self.event], input=json.dumps({'hook_event_name': name,
                                                             'session_id': 'integration', 'turn_id': turn, 'cwd': '/work/demo'}))
        for name, state, physical in [('UserPromptSubmit', 'running', 'running/00'),
                                      ('PermissionRequest',
                                       'needs_input', 'needs_input/00'),
                                      ('PostToolUse', 'running', 'running/00'),
                                      ('Stop', 'ready', 'ready/05')]:
            offset = len(self.frames())
            hook(name)
            self.assertEqual(self.request(
                {'action': 'status'})['state'], state)
            from PIL import Image
            with Image.open(self.source / f'codex_pet/assets/akita/frames/{physical}.png') as img:
                expected = hashlib.sha256(
                    img.convert('RGBA').tobytes()).hexdigest()
            self.wait_for(lambda: any(row.get('rgba_sha256') ==
                          expected for row in self.frames()[offset:]))
        hook('PostToolUse')
        self.assertEqual(self.request({'action': 'status'})['state'], 'ready')
        hook('UserPromptSubmit', 't2')
        hook('Stop', 't1')
        self.assertEqual(self.request({'action': 'status'})[
                         'state'], 'running')
        with (self.root / 'touch.jsonl').open('a') as events:
            for action, x, y in [('down', 140, 250), ('move', 190, 310), ('up', 190, 310)]:
                events.write(json.dumps({'type': 'overlayTouch', 'value': {
                             'action': action, 'x': x, 'y': y}}) + '\n')
        self.wait_for(lambda: json.loads(self.config.read_text())
                      ['position'] == {'x': 180, 'y': 300})
        self.assertTrue(any(row.get('x') == 180 and row.get(
            'y') == 300 for row in self.frames()))
        status = self.request({'action': 'status'})
        # Start is idempotent at the real lock/process boundary.
        self.run_command([self.cli, 'start'])
        self.assertEqual(self.request({'action': 'status'})[
                         'pid'], status['pid'])
        for invalid in ('{', ' ' * 65537):
            self.run_command([self.event], input=invalid)
            self.assertEqual(self.request({'action': 'status'})[
                             'state'], 'running')
        hook('SessionEnd', 't2')
        self.assertEqual(self.request({'action': 'status'})[
                         'session_count'], 0)


if __name__ == '__main__':
    unittest.main()
