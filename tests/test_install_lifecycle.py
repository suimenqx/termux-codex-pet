"""The full install path restores owned and foreign files after a failed step."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from codex_pet import deployment


class InstallLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.prefix = self.root / "prefix"
        (self.prefix / "bin").mkdir(parents=True)
        self.source = self.root / "checkout"
        shutil.copytree(Path(__file__).resolve().parents[1] / "codex_pet/assets",
                        self.source / "codex_pet/assets")
        (self.source / "bin").mkdir(parents=True)
        (self.source / "codex_pet").mkdir(exist_ok=True)
        for name in deployment.ENTRYPOINTS:
            (self.source / "bin" / name).write_text(f"source {name}\n")
        (self.source / "codex_pet" / "__init__.py").write_text("")
        self.codex = self.home / ".codex"
        self.codex.mkdir()
        self.hooks = self.codex / "hooks.json"
        self.user_hooks = {"hooks": {"Stop": [{"hooks": [
            {"type": "command", "command": "/tmp/user-hook"},
        ]}]}}
        self.hooks.write_text(json.dumps(self.user_hooks))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_repeated_install_and_uninstall_preserve_foreign_commands_and_hooks(self) -> None:
        local_bin = self.home / ".local" / "bin"
        local_bin.mkdir(parents=True)
        foreign_local = local_bin / "codex-pet"
        foreign_local.write_text("my local command\n")
        foreign_prefix = self.prefix / "bin" / "codex-pet-event"
        foreign_prefix.write_text("my prefix command\n")
        calls: list[list[str]] = []

        def run(command: list[str], **_kwargs: object) -> int:
            calls.append(command)
            return 0

        with patch.object(deployment, "_run", side_effect=run):
            first = deployment.install_application(self.source, self.home, self.prefix)
            second = deployment.install_application(self.source, self.home, self.prefix)
            self.assertNotEqual(first, second)
            self.assertEqual((self.home / ".local/share/codex-pet/current").resolve(), second)
            self.assertEqual((self.home / ".local/share/codex-pet/previous").resolve(), first)
            self.assertEqual(json.loads(self.hooks.read_text())["hooks"]["Stop"][0],
                             self.user_hooks["hooks"]["Stop"][0])
            deployment.uninstall_application(self.source, self.home, self.prefix)

        self.assertEqual(foreign_local.read_text(), "my local command\n")
        self.assertEqual(foreign_prefix.read_text(), "my prefix command\n")
        self.assertFalse((self.prefix / "bin" / "codex-pet").exists())
        self.assertEqual(json.loads(self.hooks.read_text()), self.user_hooks)
        self.assertFalse((self.home / ".local/share/codex-pet").exists())
        self.assertFalse((self.home / ".config/codex-pet/install.json").exists())
        self.assertTrue((self.home / ".config/codex-pet/config.json").exists())
        self.assertTrue(any(len(command) > 1 and command[1] == "restart" for command in calls))
        self.assertTrue(any(len(command) > 1 and command[1] == "stop" for command in calls))

    def test_failed_first_install_restores_hooks_commands_and_release(self) -> None:
        foreign_prefix = self.prefix / "bin" / "codex-pet"
        foreign_prefix.write_text("my command\n")
        original_hooks = self.hooks.read_bytes()
        calls: list[str] = []

        def run(command: list[str], **_kwargs: object) -> int:
            calls.append(command[1] if len(command) > 1 else "event")
            return 1 if len(command) > 1 and command[1] == "restart" else 0

        with patch.object(deployment, "_run", side_effect=run):
            with self.assertRaisesRegex(RuntimeError, "restart"):
                deployment.install_application(self.source, self.home, self.prefix)

        self.assertEqual(calls, ["restart", "stop"])
        self.assertEqual(foreign_prefix.read_text(), "my command\n")
        self.assertEqual(self.hooks.read_bytes(), original_hooks)
        self.assertFalse((self.home / ".config/codex-pet/install.json").exists())
        self.assertFalse((self.home / ".config/codex-pet/config.json").exists())
        self.assertFalse((self.home / ".local/bin/codex-pet").exists())
        self.assertFalse((self.home / ".local/share/codex-pet/current").exists())
        self.assertEqual(list((self.home / ".local/share/codex-pet/releases").iterdir()), [])

    def test_failed_update_restores_previous_release_and_running_daemon(self) -> None:
        first = deployment.deploy(self.source, self.home)
        original_hooks = self.hooks.read_bytes()
        calls: list[str] = []

        def run(command: list[str], **_kwargs: object) -> int:
            action = command[1] if len(command) > 1 else "event"
            calls.append(action)
            return 1 if action == "restart" else 0

        with patch.object(deployment, "_run", side_effect=run):
            with self.assertRaisesRegex(RuntimeError, "restart"):
                deployment.install_application(self.source, self.home, self.prefix)

        self.assertEqual(calls, ["status", "restart", "stop", "start"])
        self.assertEqual((self.home / ".local/share/codex-pet/current").resolve(), first)
        self.assertFalse((self.home / ".local/share/codex-pet/previous").exists())
        self.assertEqual(self.hooks.read_bytes(), original_hooks)
        self.assertEqual([path for path in first.parent.iterdir() if path.is_dir()], [first])

    def test_invalid_hook_file_restores_entrypoints_before_daemon_restart(self) -> None:
        self.hooks.write_text('{"hooks": []}\n')
        foreign_prefix = self.prefix / "bin" / "codex-pet-event"
        foreign_prefix.write_text("foreign\n")
        with patch.object(deployment, "_run") as run:
            with self.assertRaisesRegex(ValueError, "unexpected shape"):
                deployment.install_application(self.source, self.home, self.prefix)

        run.assert_not_called()
        self.assertEqual(foreign_prefix.read_text(), "foreign\n")
        self.assertFalse((self.prefix / "bin" / "codex-pet").exists())
        self.assertEqual(self.hooks.read_text(), '{"hooks": []}\n')
        self.assertEqual(list((self.home / ".local/share/codex-pet/releases").iterdir()), [])

    def test_failed_inline_hook_install_restores_user_config(self) -> None:
        toml = self.codex / "config.toml"
        original = ('[features]\nhooks = true\n\n'
                    '[[hooks.Stop]]\n[[hooks.Stop.hooks]]\n'
                    'type = "command"\ncommand = "/tmp/user-hook"\n')
        toml.write_text(original)

        def run(command: list[str], **_kwargs: object) -> int:
            return 1 if len(command) > 1 and command[1] == "restart" else 0

        with patch.object(deployment, "_run", side_effect=run):
            with self.assertRaisesRegex(RuntimeError, "restart"):
                deployment.install_application(self.source, self.home, self.prefix)

        self.assertEqual(toml.read_text(), original)
        self.assertEqual(json.loads(self.hooks.read_text()), self.user_hooks)
        self.assertFalse((self.home / ".config/codex-pet/install.json").exists())

    def test_failed_update_reports_when_prior_daemon_cannot_restart(self) -> None:
        first = deployment.deploy(self.source, self.home)

        def run(command: list[str], **_kwargs: object) -> int:
            action = command[1] if len(command) > 1 else "event"
            return 1 if action in ("restart", "start") else 0

        with patch.object(deployment, "_run", side_effect=run):
            with self.assertRaisesRegex(RuntimeError, "rollback incomplete.*previous daemon"):
                deployment.install_application(self.source, self.home, self.prefix)

        self.assertEqual((self.home / ".local/share/codex-pet/current").resolve(), first)
        self.assertEqual([path for path in first.parent.iterdir() if path.is_dir()], [first])


if __name__ == "__main__":
    unittest.main()
