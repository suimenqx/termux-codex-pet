"""Installer updates only its owned Codex hook block."""

from pathlib import Path
import json
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from codex_pet import hooks_config


class HookConfigTests(unittest.TestCase):
    def test_uninstall_without_manifest_removes_both_sources_and_only_pet_trust(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            codex = home / ".codex"
            codex.mkdir()
            command = str(home / ".local/bin/codex-pet-event")
            hooks = codex / "hooks.json"
            hooks.write_text(json.dumps({"description": "user settings", "hooks": {
                "Stop": [{"matcher": ".*", "hooks": [
                    {"type": "command", "command": command},
                    {"type": "command", "command": "/user/hook"}]}],
                "Empty": [],
            }}))
            toml = codex / "config.toml"
            json_id = f"{hooks}:stop:0:0"
            inline_id = f"{toml}:session_start:0:0"
            user_id = f"{hooks}:stop:0:1"
            prefix = '# user comment\n[features]\nhooks = true\n\n[hooks.state]\n'
            toml.write_text(prefix +
                            f'"{json_id}" = {{ trusted_hash = "pet" }}\n' +
                            f'[hooks.state."{inline_id}"]\ntrusted_hash = "pet-inline"\n' +
                            f'[hooks.state."{user_id}"]\ntrusted_hash = "user"\n\n' +
                            hooks_config.BEGIN + '\n[[hooks.SessionStart]]\n' +
                            '[[hooks.SessionStart.hooks]]\ntype = "command"\n' +
                            f'command = {json.dumps(command)}\n' + hooks_config.END + '\n')

            hooks_config.uninstall(home)
            state = tomllib.loads(toml.read_text())["hooks"]["state"]
            self.assertEqual(state, {user_id: {"trusted_hash": "user"}})
            self.assertTrue(toml.read_text().startswith(prefix))
            self.assertNotIn(hooks_config.BEGIN, toml.read_text())
            self.assertEqual(json.loads(hooks.read_text()), {
                "description": "user settings", "hooks": {
                    "Stop": [{"matcher": ".*", "hooks": [
                        {"type": "command", "command": "/user/hook"}]}], "Empty": []}})
            snapshots = toml.read_bytes(), hooks.read_bytes()
            backup_count = len(list(codex.glob("*.codex-pet-backup-*")))
            hooks_config.uninstall(home)
            self.assertEqual((toml.read_bytes(), hooks.read_bytes()), snapshots)
            self.assertEqual(len(list(codex.glob("*.codex-pet-backup-*"))), backup_count)

    def test_manifest_cleans_trust_when_json_source_was_already_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            hooks_config.install(home)
            hooks = home / ".codex/hooks.json"
            manifest = home / ".config/codex-pet/install.json"
            ids = json.loads(manifest.read_text())["hook_state_ids"]
            self.assertEqual(len(ids), len(hooks_config.HOOK_STATES))
            toml = home / ".codex/config.toml"
            toml.write_text('[hooks.state]\n' + ''.join(
                f'[hooks.state.{json.dumps(key)}]\ntrusted_hash = "pet"\n' for key in ids))
            hooks.unlink()

            hooks_config.uninstall(home)

            self.assertEqual(tomllib.loads(toml.read_text())["hooks"]["state"], {})
            self.assertFalse(manifest.exists())
            self.assertFalse(hooks.exists())

    def test_install_migrates_json_pet_to_inline_without_duplicate_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            hooks_config.install(home)
            hooks = home / ".codex/hooks.json"
            toml = home / ".codex/config.toml"
            pet_id = f"{hooks}:stop:0:0"
            toml.write_text('[features]\nhooks = true\n[hooks.state]\n' +
                            f'"{pet_id}" = {{ trusted_hash = "pet" }}\n' +
                            '[[hooks.Stop]]\n[[hooks.Stop.hooks]]\n' +
                            'type = "command"\ncommand = "/user/stop"\n')

            hooks_config.install(home)

            self.assertFalse(hooks.exists())
            config = tomllib.loads(toml.read_text())
            self.assertEqual(config["hooks"]["state"], {})
            stops = config["hooks"]["Stop"]
            self.assertEqual([g["hooks"][0]["command"] for g in stops],
                             ["/user/stop", str(home / ".local/bin/codex-pet-event")])
            self.assertEqual(json.loads((home / ".config/codex-pet/install.json").read_text())
                             ["hooks_mode"], "inline")
            hooks_config.uninstall(home)
            self.assertEqual(tomllib.loads(toml.read_text())["hooks"]["Stop"], stops[:1])

    def test_invalid_json_prevents_uninstall_from_changing_any_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            hooks_config.install(home)
            hooks = home / ".codex/hooks.json"
            manifest = home / ".config/codex-pet/install.json"
            hooks.write_text('{"hooks": []}\n')
            original = manifest.read_bytes()
            with self.assertRaisesRegex(ValueError, "unexpected shape"):
                hooks_config.uninstall(home)
            self.assertEqual(manifest.read_bytes(), original)
            self.assertEqual(hooks.read_text(), '{"hooks": []}\n')

    def test_manifest_does_not_delete_trust_for_a_slot_now_owned_by_a_user_hook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            hooks_config.install(home)
            hooks = home / ".codex/hooks.json"
            user_hooks = {"hooks": {"Stop": [{"hooks": [
                {"type": "command", "command": "/user/replacement"}]}]}}
            hooks.write_text(json.dumps(user_hooks))
            toml = home / ".codex/config.toml"
            content = f'[hooks.state."{hooks}:stop:0:0"]\ntrusted_hash = "user"\n'
            toml.write_text(content)
            hooks_config.uninstall(home)
            self.assertEqual(toml.read_text(), content)
            self.assertEqual(json.loads(hooks.read_text()), user_hooks)

    def test_trust_without_explicit_parent_table_is_removed_and_comments_are_kept(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            hooks_config.install(home)
            hooks = home / ".codex/hooks.json"
            toml = home / ".codex/config.toml"
            toml.write_text(f'[hooks.state."{hooks}:stop:0:0"]\ntrusted_hash = "pet"\n'
                            '# user comment\n[features]\nhooks = true\n')
            hooks_config.uninstall(home)
            self.assertEqual(tomllib.loads(toml.read_text()), {"features": {"hooks": True}})
            self.assertIn("# user comment", toml.read_text())

    def test_incomplete_inline_markers_abort_before_modifying_hook_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            hooks_config.install(home)
            toml = home / ".codex/config.toml"
            content = hooks_config.BEGIN + '\n[features]\nhooks = true\n'
            toml.write_text(content)
            hooks = home / ".codex/hooks.json"
            original = hooks.read_bytes()
            for operation in (hooks_config.install, hooks_config.uninstall):
                with self.assertRaisesRegex(ValueError, "hook markers"):
                    operation(home)
                self.assertEqual(toml.read_text(), content)
                self.assertEqual(hooks.read_bytes(), original)

    def test_codex_hook_state_metadata_does_not_select_inline_install_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex = root / ".codex"
            codex.mkdir()
            toml = codex / "config.toml"
            hooks_json = codex / "hooks.json"
            manifest = root / ".config" / "codex-pet" / "install.json"
            toml.write_text('[features]\nhooks = true\n\n'
                            '[hooks.state]\n"cached-hook-state" = { trusted = true }\n')
            old_events = set(hooks_config.HOOK_STATES) - {"PostToolUse"}
            json_hooks = {"hooks": {
                event: [{"hooks": [{"type": "command", "command": "/tmp/codex-pet-event"}]}]
                for event in old_events
            }}
            json_hooks["hooks"]["PostToolUse"] = [{"hooks": [
                {"type": "command", "command": "/tmp/user-post-tool-hook"},
            ]}]
            hooks_json.write_text(json.dumps(json_hooks))
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({
                "hooks_mode": "json",
                "installed_events": sorted(old_events),
                "created_hooks_file": True,
            }))
            original_toml = toml.read_text()

            with patch.multiple(hooks_config, CODEX=codex, TOML=toml,
                                HOOKS=hooks_json, MANIFEST=manifest,
                                COMMAND="/tmp/codex-pet-event"):
                hooks_config.install()

                self.assertEqual(toml.read_text(), original_toml)
                self.assertEqual(json.loads(manifest.read_text())["hooks_mode"], "json")
                installed_hooks = json.loads(hooks_json.read_text())["hooks"]
                post_tool_commands = [hook["command"]
                                      for group in installed_hooks["PostToolUse"]
                                      for hook in group["hooks"]]
                self.assertIn("/tmp/user-post-tool-hook", post_tool_commands)
                self.assertIn("/tmp/codex-pet-event", post_tool_commands)

    def test_inline_install_refreshes_pet_events_and_preserves_user_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex = root / ".codex"
            codex.mkdir()
            toml = codex / "config.toml"
            manifest = root / ".config" / "codex-pet" / "install.json"
            old_pet_block = (f"{hooks_config.BEGIN}\n"
                             "[[hooks.SessionStart]]\n"
                             "[[hooks.SessionStart.hooks]]\n"
                             "type = \"command\"\n"
                             "command = \"/tmp/codex-pet-event\"\n"
                             "timeout = 3\n\n"
                             f"{hooks_config.END}\n")
            user_hook = ("[[hooks.UserPromptSubmit]]\n"
                         "matcher = \".*\"\n"
                         "[[hooks.UserPromptSubmit.hooks]]\n"
                         "type = \"command\"\n"
                         "command = \"/tmp/my-hook\"\n")
            toml.write_text("[features]\nhooks = true\n\n" + old_pet_block + user_hook)

            with patch.multiple(hooks_config, CODEX=codex, TOML=toml,
                                HOOKS=codex / "hooks.json", MANIFEST=manifest,
                                COMMAND="/tmp/codex-pet-event"):
                hooks_config.install()
                installed = tomllib.loads(toml.read_text())["hooks"]
                self.assertIn("PostToolUse", installed)
                user_commands = [hook["command"] for group in installed["UserPromptSubmit"]
                                 for hook in group.get("hooks", [])]
                self.assertIn("/tmp/my-hook", user_commands)
                pet_commands = [hook["command"] for name, groups in installed.items()
                                for group in groups for hook in group.get("hooks", [])
                                if hook.get("command") == "/tmp/codex-pet-event"]
                self.assertEqual(len(pet_commands), len(hooks_config.HOOK_STATES))
                backups_before = list(codex.glob("config.toml.codex-pet-backup-*"))

                hooks_config.install()

                backups_after = list(codex.glob("config.toml.codex-pet-backup-*"))
                self.assertEqual(len(backups_after), len(backups_before))
                self.assertEqual(tomllib.loads(toml.read_text())["hooks"], installed)


if __name__ == "__main__":
    unittest.main()
