import unittest
from unittest.mock import patch

from versline.config import settings
from versline.services.transcription import AudioTranscriber


class TestMainPathSttRouting(unittest.TestCase):
    def setUp(self):
        self._orig = (settings.llm.provider, settings.llm.api_endpoint, settings.llm.api_key)
        settings.llm.provider = "openrouter"
        settings.llm.api_key = "k"
        settings.llm.api_endpoint = None

    def tearDown(self):
        settings.llm.provider, settings.llm.api_endpoint, settings.llm.api_key = self._orig

    def test_stt_model_name_is_detected(self):
        t = AudioTranscriber()
        self.assertTrue(t._uses_stt_api("openrouter", "elevenlabs/scribe-v2"))
        self.assertTrue(t._uses_stt_api("openai", "whisper-1"))
        self.assertTrue(t._uses_stt_api("openai", "gpt-4o-transcribe"))
        self.assertFalse(t._uses_stt_api("openrouter", "google/gemini-2.5-flash"))
        self.assertFalse(t._uses_stt_api("gemini", "whisper-1"))

    def test_transcriptions_endpoint_forces_stt(self):
        settings.llm.api_endpoint = "https://example.com/v1/audio/transcriptions"
        self.assertTrue(AudioTranscriber()._uses_stt_api("openaicompatible", "some-model"))

    def test_endpoint_path_is_stripped(self):
        settings.llm.provider = "openaicompatible"
        settings.llm.api_endpoint = "https://example.com/v1/audio/transcriptions/"
        cfg = AudioTranscriber()._llm_stt_config("openaicompatible")
        self.assertEqual(cfg["endpoint"], "https://example.com/v1")

    def test_openrouter_full_url_uses_base(self):
        settings.llm.api_endpoint = "https://openrouter.ai/api/v1/audio/transcriptions"
        cfg = AudioTranscriber()._llm_stt_config("openrouter")
        self.assertEqual(cfg["endpoint"], "https://openrouter.ai/api/v1")

    def test_chunk_goes_to_stt_not_chat(self):
        settings.llm.api_endpoint = "https://openrouter.ai/api/v1/audio/transcriptions"
        t = AudioTranscriber()
        with patch.object(t, "transcribe_chunk_via_stt_api", return_value="متن") as stt, \
             patch.object(t, "transcribe_audio_chunk_by_openaicompatible") as chat:
            out = t.transcribe_chunk_with_retry("elevenlabs/scribe-v2", "x.m4a", "p", max_retries=1)
        self.assertEqual(out, "متن")
        stt.assert_called_once()
        self.assertEqual(stt.call_args.kwargs["stt"]["endpoint"], "https://openrouter.ai/api/v1")
        chat.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class DefaultTimestampModelTests(unittest.TestCase):
    def setUp(self):
        from versline.config import TranscriptionSettings

        self.saved = (settings.transcription, settings.llm.provider, settings.llm.api_endpoint)
        self.fresh = TranscriptionSettings.model_construct()  # defaults only; nothing counts as configured
        settings.transcription = self.fresh

    def tearDown(self):
        settings.transcription, settings.llm.provider, settings.llm.api_endpoint = self.saved

    def test_openrouter_gets_scribe_unless_a_model_is_set(self):
        settings.llm.provider = "OpenRouter"
        t = AudioTranscriber()
        self.assertEqual(t.default_timestamp_model(), "elevenlabs/scribe-v2")
        self.fresh.timestamp_model = "openai/whisper-1"
        self.assertEqual(t.default_timestamp_model(), "openai/whisper-1")

    def test_other_providers_keep_the_default(self):
        settings.llm.provider = "OpenAI"
        self.assertEqual(AudioTranscriber().default_timestamp_model(), "gpt-4o-mini-transcribe")
        settings.llm.provider = "OpenRouter"
        self.fresh.timestamp_provider = "OpenAI"  # timestamps go to OpenAI even though the LLM is on OpenRouter
        self.assertEqual(AudioTranscriber().default_timestamp_model(), "gpt-4o-mini-transcribe")

    def test_openrouter_llm_without_endpoint_uses_openrouter_for_stt(self):
        settings.llm.provider = "OpenRouter"
        settings.llm.api_endpoint = None
        self.assertEqual(AudioTranscriber()._resolve_stt_config()["endpoint"], "https://openrouter.ai/api/v1")
