from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest
import json

from codex_pet.deployment import deploy, remove_installation, rollback


class DeploymentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "termux-home"
        self.home.mkdir()
        self.source = self.root / "editable-checkout"
        shutil.copytree(Path(__file__).resolve().parents[1] / "codex_pet/assets",
                        self.source / "codex_pet/assets")
        (self.source / "bin").mkdir(parents=True)
        (self.source / "codex_pet" / "assets").mkdir(parents=True, exist_ok=True)
        (self.source / "bin" / "codex-pet").write_text("cli source\n", encoding="utf-8")
        (self.source / "bin" / "codex-pet-event").write_text("hook source\n", encoding="utf-8")
        (self.source / "codex_pet" / "__init__.py").write_text("", encoding="utf-8")
        (self.source / "codex_pet" / "runtime.py").write_text("runtime source\n", encoding="utf-8")
        (self.source / "codex_pet" / "assets" / "frame.png").write_bytes(b"image")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_deploy_copies_runtime_and_installs_stable_wrappers(self) -> None:
        cli_source = self.source / "bin" / "codex-pet"
        cli_source.chmod(0o644)

        release = deploy(self.source, self.home)

        self.assertEqual(release.parent, self.home / ".local/share/codex-pet/releases")
        self.assertEqual((release / "codex_pet/runtime.py").read_text(encoding="utf-8"), "runtime source\n")
        self.assertEqual((release / "codex_pet/assets/frame.png").read_bytes(), b"image")
        self.assertEqual(cli_source.stat().st_mode & 0o777, 0o644)
        self.assertEqual((release / ".codex-pet-release").read_text(encoding="utf-8"), "codex-pet\n")

        current = self.home / ".local/share/codex-pet/current"
        self.assertTrue(current.is_symlink())
        self.assertTrue(current.resolve().samefile(release))
        for name in ("codex-pet", "codex-pet-event"):
            wrapper = self.home / ".local/bin" / name
            self.assertTrue(wrapper.is_file())
            self.assertIn(f"# CODEX_PET_MANAGED_ENTRYPOINT={name}", wrapper.read_text(encoding="utf-8"))
            self.assertIn(f"current/bin/{name}", wrapper.read_text(encoding="utf-8"))

        moved_source = self.root / "moved-checkout"
        self.source.rename(moved_source)
        self.assertTrue((current.resolve() / "codex_pet/assets/frame.png").is_file())

    def test_deploy_retains_previous_release_and_rollback_switches_atomically(self) -> None:
        first = deploy(self.source, self.home)
        (self.source / "codex_pet" / "runtime.py").write_text("updated runtime\n", encoding="utf-8")

        second = deploy(self.source, self.home)

        app_dir = self.home / ".local/share/codex-pet"
        self.assertEqual((app_dir / "current").resolve(), second)
        self.assertEqual((app_dir / "previous").resolve(), first)
        self.assertEqual((app_dir / "current/codex_pet/runtime.py").read_text(encoding="utf-8"), "updated runtime\n")

        rolled_back = rollback(self.home)

        self.assertEqual(rolled_back, first)
        self.assertEqual((app_dir / "current").resolve(), first)
        self.assertEqual((app_dir / "previous").resolve(), second)

    def test_invalid_pet_pack_cannot_replace_the_active_release(self):
        first = deploy(self.source, self.home)
        pack = self.source / 'codex_pet/assets/robot/pet.json'
        pack.parent.mkdir(parents=True, exist_ok=True)
        pack.write_text(json.dumps({'schema_version':99}))
        with self.assertRaises(ValueError):
            deploy(self.source, self.home)
        self.assertEqual((self.home / '.local/share/codex-pet/current').resolve(), first)

    def test_missing_or_corrupt_derived_frame_preserves_current(self):
        first = deploy(self.source, self.home)
        blink = self.source / 'codex_pet/assets/akita/derived/ready-blink.png'
        blink.unlink()
        for data in (None, b'broken PNG'):
            if data is not None:
                blink.write_bytes(data)
            with self.assertRaises(ValueError):
                deploy(self.source, self.home)
            self.assertEqual((self.home / '.local/share/codex-pet/current').resolve(), first)

    def test_missing_new_pet_frame_cannot_replace_active_release(self):
        first = deploy(self.source, self.home)
        (self.source / 'codex_pet/assets/pixel_dog/frames/running/04.png').unlink()
        with self.assertRaises(ValueError):
            deploy(self.source, self.home)
        self.assertEqual((self.home / '.local/share/codex-pet/current').resolve(), first)

    def test_deploy_migrates_legacy_source_symlinks_without_backing_them_up(self) -> None:
        local_bin = self.home / ".local/bin"
        local_bin.mkdir(parents=True)
        (local_bin / "codex-pet").symlink_to(self.source / "bin/codex-pet")

        deploy(self.source, self.home)

        self.assertFalse((self.home / ".config/codex-pet/cli-backups/codex-pet").exists())
        self.assertIn(
            "# CODEX_PET_MANAGED_ENTRYPOINT=codex-pet",
            (local_bin / "codex-pet").read_text(encoding="utf-8"),
        )

    def test_remove_restores_foreign_commands_and_preserves_source_and_user_data(self) -> None:
        local_bin = self.home / ".local/bin"
        local_bin.mkdir(parents=True)
        foreign_command = local_bin / "codex-pet"
        foreign_command.write_text("my existing command\n", encoding="utf-8")
        deploy(self.source, self.home)

        remove_installation(self.source, self.home)

        self.assertEqual(foreign_command.read_text(encoding="utf-8"), "my existing command\n")
        self.assertTrue(self.source.is_dir())
        self.assertFalse((self.home / ".local/share/codex-pet").exists())

    def test_remove_leaves_unmarked_runtime_files_alone(self) -> None:
        app_dir = self.home / ".local/share/codex-pet"
        unrelated = app_dir / "releases/keep-me"
        unrelated.mkdir(parents=True)
        (unrelated / "notes.txt").write_text("user data\n", encoding="utf-8")
        deploy(self.source, self.home)

        remove_installation(self.source, self.home)

        self.assertEqual((unrelated / "notes.txt").read_text(encoding="utf-8"), "user data\n")


if __name__ == "__main__":
    unittest.main()
