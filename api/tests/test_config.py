import os
import unittest
from unittest.mock import patch

from api.config import Settings


class SettingsTests(unittest.TestCase):
    def test_reads_local_model_configuration(self):
        with patch.dict(
            os.environ,
            {
                "OLLAMA_BASE_URL": "http://127.0.0.1:11434/",
                "OLLAMA_MODEL": "qwen2.5-coder:14b",
                "OLLAMA_TIMEOUT_SECONDS": "120",
            },
            clear=False,
        ):
            settings = Settings.from_environment()

        self.assertEqual(settings.ollama_base_url, "http://127.0.0.1:11434")
        self.assertEqual(settings.ollama_model, "qwen2.5-coder:14b")
        self.assertEqual(settings.ollama_timeout_seconds, 120)

    def test_rejects_public_or_credential_bearing_model_urls(self):
        with patch.dict(
            os.environ,
            {"OLLAMA_BASE_URL": "https://example.com"},
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "loopback/private"):
                Settings.from_environment()

        with patch.dict(
            os.environ,
            {"OLLAMA_BASE_URL": "http://user:password@127.0.0.1:11434"},
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "credentials"):
                Settings.from_environment()


if __name__ == "__main__":
    unittest.main()
