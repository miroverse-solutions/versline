import unittest
from unittest.mock import patch

from versline.config import settings
from versline.services import ai
from versline.services.ai import LLMSettings, MissingAPIKeyError
from versline.services.transcription import AudioTranscriber


@patch.dict("os.environ", {"OPENAI_API_KEY": "", "GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""})
class TestMissingAPIKey(unittest.TestCase):
    def test_configure_openai_raises_clear_error(self):
        with self.assertRaises(MissingAPIKeyError) as cm:
            ai.configure_openai(LLMSettings(provider="OpenRouter"))
        self.assertIn("versline init", str(cm.exception))
        self.assertIn("OpenRouter", str(cm.exception))

    def test_configure_gemini_raises_clear_error(self):
        with self.assertRaises(MissingAPIKeyError):
            ai.configure_gemini(LLMSettings(provider="Google"))

    def test_sdk_env_var_counts_as_key(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            ai.require_api_key(LLMSettings(provider="OpenAI"))

    def test_transcription_does_not_retry_without_key(self):
        orig = (settings.llm.provider, settings.llm.api_key)
        settings.llm.provider, settings.llm.api_key = "OpenRouter", None
        try:
            with patch("versline.services.transcription.time.sleep") as sleep:
                with self.assertRaises(MissingAPIKeyError):
                    AudioTranscriber().transcribe_chunk_with_retry("m", "chunk_000.mp3", "p")
            sleep.assert_not_called()
        finally:
            settings.llm.provider, settings.llm.api_key = orig


if __name__ == "__main__":
    unittest.main()
