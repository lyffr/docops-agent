import os
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


class StreamlitAppTests(unittest.TestCase):
    def test_ui_requires_login_when_password_is_configured(self) -> None:
        with patch.dict(
            os.environ,
            {"DOCOPS_UI_PASSWORD": "streamlit-test-password-1234"},
        ):
            app_path = Path(__file__).resolve().parents[1] / "docops_agent" / "streamlit_app.py"
            app = AppTest.from_file(app_path).run(timeout=10)

        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.title[0].value, "DocOps Agent 登录")
        self.assertEqual(app.text_input[0].label, "访问口令")


if __name__ == "__main__":
    unittest.main()
