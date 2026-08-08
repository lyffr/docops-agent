import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docops_agent import desktop


class DesktopLauncherTests(unittest.TestCase):
    def test_available_port_falls_back_when_preferred_port_is_busy(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            occupied_port = occupied.getsockname()[1]

            selected_port = desktop._available_port(occupied_port)

        self.assertNotEqual(selected_port, occupied_port)
        self.assertGreater(selected_port, 0)

    def test_prepare_app_home_creates_default_config_and_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.dict(
                "os.environ",
                {"DOCOPS_DESKTOP_HOME": temporary_directory},
                clear=False,
            ):
                app_home, log_directory, config_path = desktop._prepare_app_home()

            self.assertEqual(app_home, Path(temporary_directory).resolve())
            self.assertTrue((app_home / "data").is_dir())
            self.assertTrue(log_directory.is_dir())
            self.assertIn("DOCOPS_LLM_PROVIDER=extractive", config_path.read_text("utf-8"))

    def test_load_config_rejects_settings_that_can_expose_the_desktop_server(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.env"
            config_path.write_text("DOCOPS_BIND_HOST=0.0.0.0\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported setting DOCOPS_BIND_HOST"):
                desktop._load_config(config_path)

    def test_desktop_environment_is_local_only_and_persistent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            app_home = Path(temporary_directory)
            with patch.object(desktop, "_available_port", side_effect=[18000, 18501]):
                environment, ui_url = desktop._desktop_environment(
                    {"DOCOPS_LLM_PROVIDER": "extractive"},
                    app_home,
                )

            self.assertEqual(environment["DOCOPS_DESKTOP_API_PORT"], "18000")
            self.assertEqual(environment["DOCOPS_DESKTOP_UI_PORT"], "18501")
            self.assertEqual(environment["DOCOPS_TRUSTED_HOSTS"], "localhost,127.0.0.1")
            self.assertEqual(
                environment["DOCOPS_DATABASE_PATH"],
                str(app_home / "data" / "docops.db"),
            )
            self.assertEqual(ui_url, "http://127.0.0.1:18501")


if __name__ == "__main__":
    unittest.main()
