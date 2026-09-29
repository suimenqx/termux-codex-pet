"""Installer updates only its owned Codex hook block."""

from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from codex_pet import hooks_config


class HookConfigTests(unittest.TestCase):
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
