import os
import tempfile
import unittest
from pathlib import Path

from versline.config import reload_settings, settings


class TestConfigEnv(unittest.TestCase):
    def setUp(self):
        self._original_env = os.environ.copy()
        for key in ["VERSLINE_LLM_PROVIDER", "VERSLINE_LLM_MODEL", "VERSLINE_ENV_FILE"]:
            os.environ.pop(key, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._original_env)
        reload_settings()

    def test_reload_settings_from_custom_env_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_file = Path(tmp_dir) / ".custom.env"
            env_file.write_text(
                "\n".join(
                    [
                        "VERSLINE_LLM_PROVIDER=OpenAI",
                        "VERSLINE_LLM_MODEL=gpt-4o-mini",
                        "VERSLINE_SLIDES_NPM_REGISTRY=https://registry.example.com",
                    ]
                ),
                encoding="utf-8",
            )

            reload_settings(env_file=env_file)

            self.assertEqual(settings.llm.provider, "OpenAI")
            self.assertEqual(settings.llm.model, "gpt-4o-mini")
            self.assertEqual(settings.slides.npm_registry, "https://registry.example.com")

    def test_reload_settings_uses_env_file_fallback(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_file = Path(tmp_dir) / ".fallback.env"
            env_file.write_text(
                "\n".join(
                    [
                        "VERSLINE_LLM_PROVIDER=OpenRouter",
                        "VERSLINE_LLM_MODEL=openrouter/auto",
                    ]
                ),
                encoding="utf-8",
            )

            os.environ["VERSLINE_ENV_FILE"] = str(env_file)
            reload_settings()

            self.assertEqual(settings.llm.provider, "OpenRouter")
            self.assertEqual(settings.llm.model, "openrouter/auto")

    def test_explicit_env_file_overrides_existing_env(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_file = Path(tmp_dir) / ".explicit.env"
            env_file.write_text(
                "\n".join(
                    [
                        "VERSLINE_LLM_PROVIDER=OpenAICompatible",
                        "VERSLINE_LLM_MODEL=gpt-4o-mini",
                    ]
                ),
                encoding="utf-8",
            )

            os.environ["VERSLINE_LLM_PROVIDER"] = "Google"
            reload_settings(env_file=env_file)

            self.assertEqual(settings.llm.provider, "OpenAICompatible")
            self.assertEqual(settings.llm.model, "gpt-4o-mini")

    def test_empty_values_from_env_example_are_treated_as_unset(self):
        example = Path(__file__).resolve().parents[1] / ".env.example"
        for line in example.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.startswith("VERSLINE_") and not value:
                os.environ[key] = ""

        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.chdir(tmp_dir)  # keep the repo's own .env out of it
            try:
                reload_settings()
            finally:
                os.chdir(cwd)

        self.assertIsNone(settings.telegram.api_id)
        self.assertIsNone(settings.llm.extra_body)


if __name__ == "__main__":
    unittest.main()
