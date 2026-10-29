"""The full install path restores owned and foreign files after a failed step."""

import json
from pathlib import Path
import shutil
import sys
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

    def test_install_and_uninstall_do_not_restore_legacy_links_from_other_checkouts(self) -> None:
        local_bin = self.home / ".local/bin"
        local_bin.mkdir(parents=True)
        backups = self.home / ".config/codex-pet/cli-backups"
        backups.mkdir(parents=True)
        for name in deployment.ENTRYPOINTS:
            legacy = self.home / "codex-pet/bin" / name
            (local_bin / name).symlink_to(legacy)
            (backups / name).symlink_to(legacy)
            (self.prefix / "bin" / name).symlink_to(self.home / "termux-codex-pet/bin" / name)
            (backups / f"prefix-{name}").symlink_to(local_bin / name)
        with patch.object(deployment, "_run", return_value=0):
            deployment.install_application(self.source, self.home, self.prefix)
            deployment.uninstall_application(self.source, self.home, self.prefix)
            deployment.uninstall_application(self.source, self.home, self.prefix)
        for name in deployment.ENTRYPOINTS:
            self.assertFalse((local_bin / name).is_symlink())
            self.assertFalse((self.prefix / "bin" / name).is_symlink())
            self.assertFalse((backups / name).is_symlink())
            self.assertFalse((backups / f"prefix-{name}").is_symlink())

    def test_uninstall_broken_legacy_link_stops_through_checkout_in_target_home(self) -> None:
        local_bin = self.home / ".local/bin"
        local_bin.mkdir(parents=True)
        for name in deployment.ENTRYPOINTS:
            (local_bin / name).symlink_to(self.home / "codex-pet/bin" / name)
        with patch.object(deployment, "_run", return_value=0) as run:
            deployment.uninstall_application(self.source, self.home, self.prefix)
        run.assert_called_once_with([sys.executable, str(self.source / "bin/codex-pet"), "stop"],
                                    home=self.home)
        for name in deployment.ENTRYPOINTS:
            self.assertFalse((local_bin / name).is_symlink())

    def test_foreign_broken_symlink_is_backed_up_and_restored_verbatim(self) -> None:
        local_bin = self.home / ".local/bin"
        local_bin.mkdir(parents=True)
        target = self.root / "user-command/bin/codex-pet"
        foreign = local_bin / "codex-pet"
        foreign.symlink_to(target)
        with patch.object(deployment, "_run", return_value=0):
            deployment.install_application(self.source, self.home, self.prefix)
            deployment.uninstall_application(self.source, self.home, self.prefix)
        self.assertTrue(foreign.is_symlink())
        self.assertEqual(foreign.readlink(), target)

    def test_uninstall_disables_hooks_before_stopping_daemon(self) -> None:
        with patch.object(deployment, "_run", return_value=0):
            deployment.install_application(self.source, self.home, self.prefix)

        def stop(command: list[str], **_kwargs: object) -> int:
            self.assertEqual(command[-1], "stop")
            self.assertEqual(json.loads(self.hooks.read_text()), self.user_hooks)
            return 0

        with patch.object(deployment, "_run", side_effect=stop) as run:
            deployment.uninstall_application(self.source, self.home, self.prefix)
        run.assert_called_once()

    def test_failed_stop_keeps_installed_commands_and_runtime_for_recovery(self) -> None:
        with patch.object(deployment, "_run", return_value=0):
            release = deployment.install_application(self.source, self.home, self.prefix)
        with patch.object(deployment, "_run", return_value=1):
            with self.assertRaisesRegex(RuntimeError, "did not stop"):
                deployment.uninstall_application(self.source, self.home, self.prefix)
        self.assertTrue(release.is_dir())
        self.assertTrue((self.home / ".local/bin/codex-pet").is_file())
        self.assertTrue((self.prefix / "bin/codex-pet").is_symlink())
        self.assertEqual(json.loads(self.hooks.read_text()), self.user_hooks)

    def test_failed_legacy_migration_restores_symlinks_and_trust_metadata(self) -> None:
        local_bin = self.home / ".local/bin"
        local_bin.mkdir(parents=True)
        legacy = self.home / "codex-pet/bin/codex-pet"
        (local_bin / "codex-pet").symlink_to(legacy)
        toml = self.codex / "config.toml"
        original = '[hooks.state]\n"user-trust" = { trusted_hash = "keep" }\n'
        toml.write_text(original)

        def run(command: list[str], **_kwargs: object) -> int:
            return int(len(command) > 1 and command[1] == "restart")

        with patch.object(deployment, "_run", side_effect=run):
            with self.assertRaisesRegex(RuntimeError, "restart"):
                deployment.install_application(self.source, self.home, self.prefix)
        self.assertEqual((local_bin / "codex-pet").readlink(), legacy)
        self.assertEqual(toml.read_text(), original)

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
        self.assertTrue(any(command[-1] == "stop" for command in calls))

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
