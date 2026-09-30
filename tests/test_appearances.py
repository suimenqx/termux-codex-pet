from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_pet import cli, daemon
from codex_pet.preferences import read_config, save_appearance, save_position, selected_appearance
from codex_pet.pets import APPEARANCES


class PetPreferenceTests(unittest.TestCase):
    def test_akita_is_default_and_invalid_config_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            self.assertEqual(selected_appearance(config), "akita")
            config.write_text('{"appearance": "missing"}', encoding="utf-8")
            self.assertEqual(selected_appearance(config), "akita")

    def test_appearance_and_position_updates_preserve_each_other_and_other_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            save_position(config, 13, 27)
            config.write_text(
                '{"position": {"x": 13, "y": 27}, "theme": "night"}',
                encoding="utf-8")
            save_appearance(config, "robot")
            result = read_config(config)
            self.assertEqual(result["position"], {"x": 13, "y": 27})
            self.assertEqual(result["appearance"], "robot")
            self.assertEqual(result["theme"], "night")

            save_position(config, 20, 30)
            result = read_config(config)
            self.assertEqual(result["appearance"], "robot")
            self.assertEqual(result["position"], {"x": 20, "y": 30})

    def test_unknown_appearance_is_rejected_without_changing_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            save_appearance(config, "akita")
            with self.assertRaises(ValueError):
                save_appearance(config, "fox")
            self.assertEqual(selected_appearance(config), "akita")


class PetAppearanceIpcTests(unittest.TestCase):
    def test_daemon_persists_and_publishes_a_live_appearance_change(self) -> None:
        class FakeGui:
            ui = None

            def __init__(self) -> None:
                self.wake_count = 0

            def wake(self) -> None:
                self.wake_count += 1

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            fake_gui = FakeGui()
            with patch.object(daemon, "CONFIG", config), \
                 patch.object(daemon, "GuiWorker", return_value=fake_gui):
                instance = daemon.Daemon()
                try:
                    self.assertEqual(instance.snapshot()["appearance"], "akita")
                    result = instance.process({"action": "set_appearance", "appearance": "robot"})
                    self.assertTrue(result["ok"])
                    self.assertEqual(instance.snapshot()["appearance"], "robot")
                    self.assertEqual(selected_appearance(config), "robot")
                    self.assertEqual(fake_gui.wake_count, 1)

                    invalid = instance.process({"action": "set_appearance", "appearance": "fox"})
                    self.assertFalse(invalid["ok"])
                    self.assertEqual(selected_appearance(config), "robot")
                finally:
                    instance.signal_read.close()
                    instance.signal_write.close()


class PetAppearanceCliTests(unittest.TestCase):
    def test_list_marks_the_saved_choice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            save_appearance(config, "robot")
            output = io.StringIO()
            with patch.object(cli, "CONFIG", config), redirect_stdout(output):
                self.assertEqual(cli._pet_list(), 0)
            self.assertIn("* robot", output.getvalue())

    def test_use_updates_a_running_daemon(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            with patch.object(cli, "CONFIG", config), \
                 patch.object(cli, "request", return_value={"ok": True}) as request:
                self.assertEqual(cli._pet_use("robot"), 0)
            request.assert_called_once_with(
                {"action": "set_appearance", "appearance": "robot"}, 0.5)

    def test_use_saves_for_the_next_start_when_daemon_is_stopped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            output = io.StringIO()
            with patch.object(cli, "CONFIG", config), \
                 patch.object(cli, "request", side_effect=OSError("stopped")), \
                 patch.object(cli, "_status", return_value=None), \
                 redirect_stdout(output):
                self.assertEqual(cli._pet_use("akita"), 0)
            self.assertEqual(selected_appearance(config), "akita")
            self.assertIn("next time Pet starts", output.getvalue())

    def test_unknown_use_reports_supported_ids_without_ipc(self) -> None:
        error = io.StringIO()
        with patch.object(cli, "request") as request, redirect_stderr(error):
            self.assertEqual(cli._pet_use("fox"), 2)
        request.assert_not_called()
        self.assertIn(", ".join(item.id for item in APPEARANCES), error.getvalue())


if __name__ == "__main__":
    unittest.main()
