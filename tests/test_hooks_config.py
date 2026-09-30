"""Installer updates only its owned Codex hook block."""

from pathlib import Path
import json
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from codex_pet import hooks_config


class HookConfigTests(unittest.TestCase):
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
