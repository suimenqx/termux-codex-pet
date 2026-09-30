import io
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from codex_pet import hook


class HookEntryTests(unittest.TestCase):
    def test_send_failure_uses_notification_fallback(self) -> None:
        payload = (
            b'{"hook_event_name":"PermissionRequest","session_id":"s1",'
            b'"cwd":"/tmp/demo","tool_input":{"description":"Approve this"}}'
        )
        stdin = SimpleNamespace(buffer=io.BytesIO(payload))
        with patch.object(hook.sys, "argv", ["codex-pet-event"]), \
             patch.object(hook.sys, "stdin", stdin), \
             patch.object(hook, "send_event", return_value=False) as send_event, \
             patch.object(hook, "notification") as notification:
            hook.event_main()

        sent_event = send_event.call_args.args[0]
        self.assertEqual(sent_event["state"], "needs_input")
        self.assertEqual(sent_event["project"], "demo")
        notification.assert_called_once_with("needs_input", "demo", "Approve this")

    def test_invalid_json_is_logged_and_kept_fail_open(self) -> None:
        stdin = SimpleNamespace(buffer=io.BytesIO(b"{"))
        with patch.object(hook.sys, "argv", ["codex-pet-event"]), \
             patch.object(hook.sys, "stdin", stdin), \
             patch.object(hook, "_log_hook_error") as log_error, \
             patch.object(hook, "send_event") as send_event, \
             patch.object(hook, "notification") as notification:
            hook.event_main()

        log_error.assert_called_once()
        send_event.assert_not_called()
        notification.assert_not_called()

    def test_hook_and_ordinary_cli_entrypoints_do_not_load_gui_or_daemon(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        scripts = (repo / "bin" / "codex-pet-event", repo / "bin" / "codex-pet")
        bootstrap = """
import builtins
import runpy
import sys

script = sys.argv[1]
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name == "termuxgui" or name.startswith("termuxgui."):
        raise ImportError("Termux:GUI import is forbidden in this entrypoint check")
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
sys.argv = [script, "--help"]
try:
    runpy.run_path(script, run_name="__main__")
except SystemExit as exc:
    if exc.code not in (None, 0):
        raise
assert "codex_pet.daemon" not in sys.modules
assert "codex_pet.gui" not in sys.modules
assert "termuxgui" not in sys.modules
"""
        for script in scripts:
            with self.subTest(script=script.name):
                result = subprocess.run(
                    [sys.executable, "-c", bootstrap, str(script)],
                    capture_output=True, text=True, timeout=10, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)


if __name__ == "__main__":
    unittest.main()
