"""Unit tests for configuration and environment variable loading.

Verifies:
- Loading TELEGRAM_TOKEN and TELEGRAM_CHAT_ID from .env file.
- Fallback to os.environ when .env is absent.
- Handling of missing configuration variables.
- Validation that .env.example contains required template keys.
- Module-level constants and helper functions.
"""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src import config
from src.config import get_telegram_config, load_config, reload_config


class TestConfig(unittest.TestCase):
    def test_default_db_path(self):
        """Verify that default DB_PATH ends with econobot.db."""
        self.assertTrue(config.DB_PATH.endswith("econobot.db"))

    def test_environment_variables_exported(self):
        """Verify that module exports string types for tokens."""
        self.assertIsInstance(config.TELEGRAM_TOKEN, str)
        self.assertIsInstance(config.TELEGRAM_CHAT_ID, str)

    def test_load_config_from_custom_env_file(self):
        """Verifies loading credentials from a valid .env file."""
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("TELEGRAM_TOKEN=123456:ABC-DEF_test_token\n")
            f.write("TELEGRAM_CHAT_ID=-100987654321\n")
            temp_env = f.name

        try:
            with patch.dict(os.environ, {}, clear=True):
                cfg = load_config(env_path=temp_env)
                self.assertEqual(cfg.telegram_token, "123456:ABC-DEF_test_token")
                self.assertEqual(cfg.telegram_chat_id, "-100987654321")
                self.assertEqual(config.TELEGRAM_TOKEN, "123456:ABC-DEF_test_token")
                self.assertEqual(config.TELEGRAM_CHAT_ID, "-100987654321")
        finally:
            if os.path.exists(temp_env):
                os.remove(temp_env)

    def test_load_config_from_environ_fallback(self):
        """Verifies fallback to os.environ when no .env file is provided."""
        env_vars = {
            "TELEGRAM_TOKEN": "bot999999:xyz_from_environ",
            "TELEGRAM_CHAT_ID": "11223344",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            cfg = load_config(env_path="/non_existent_env_path_12345")
            self.assertEqual(cfg.telegram_token, "bot999999:xyz_from_environ")
            self.assertEqual(cfg.telegram_chat_id, "11223344")
            self.assertEqual(config.TELEGRAM_TOKEN, "bot999999:xyz_from_environ")
            self.assertEqual(config.TELEGRAM_CHAT_ID, "11223344")

    def test_load_config_missing_variables(self):
        """Verifies config behavior when variables are missing (None or empty string)."""
        with patch.dict(os.environ, {}, clear=True):
            cfg = load_config(env_path="/non_existent_env_path_12345")
            self.assertIn(cfg.telegram_token, (None, ""))
            self.assertIn(cfg.telegram_chat_id, (None, ""))

    def test_get_telegram_config(self):
        """Verifies get_telegram_config returns current token and chat ID."""
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("TELEGRAM_TOKEN=my_test_token\n")
            f.write("TELEGRAM_CHAT_ID=my_test_chat\n")
            temp_env = f.name

        try:
            with patch.dict(os.environ, {}, clear=True):
                reload_config(env_path=temp_env)
                token, chat_id = get_telegram_config()
                self.assertEqual(token, "my_test_token")
                self.assertEqual(chat_id, "my_test_chat")
        finally:
            if os.path.exists(temp_env):
                os.remove(temp_env)

    def test_env_example_contains_required_keys(self):
        """Verifies that .env.example exists in the project root and defines required keys."""
        example_path = Path(__file__).resolve().parent.parent.parent / ".env.example"
        self.assertTrue(
            example_path.is_file(),
            f".env.example not found at expected path: {example_path}"
        )
        with open(example_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("TELEGRAM_TOKEN", content)
        self.assertIn("TELEGRAM_CHAT_ID", content)


if __name__ == "__main__":
    unittest.main()
