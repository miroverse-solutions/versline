import os
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from versline.config import settings
from versline.services.transcription import AudioTranscriber


class _FakeCompletions:
    def __init__(self):
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            usage=None,
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        )


class _FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=_FakeCompletions())


class TestTranscriptionProviderResolution(unittest.TestCase):
    def setUp(self):
        self._orig_provider = settings.llm.provider
        self._orig_avalai_provider = settings.llm.avalai_provider

    def tearDown(self):
        settings.llm.provider = self._orig_provider
        settings.llm.avalai_provider = self._orig_avalai_provider

    def test_resolve_provider_uses_env_when_settings_empty(self):
        transcriber = AudioTranscriber()
        settings.llm.provider = ""

        with patch.dict(os.environ, {"VERSLINE_LLM_PROVIDER": "AvalAI"}, clear=False):
            self.assertEqual(transcriber._resolve_provider_name(), "avalai")

    def test_resolve_provider_maps_google_alias(self):
        transcriber = AudioTranscriber()
        settings.llm.provider = "Google"
        self.assertEqual(transcriber._resolve_provider_name(), "gemini")

    def test_avalai_extra_body_is_inferred_for_gemini_model(self):
        transcriber = AudioTranscriber()
        settings.llm.avalai_provider = None

        fake_client = _FakeClient()
        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path = os.path.join(tmp_dir, "chunk.wav")
            with open(audio_path, "wb") as f:
                f.write(b"audio-bytes")
            transcriber.transcribe_audio_chunk_by_openaicompatible(
                client=fake_client,
                model_name="gemini-3-flash-preview",
                audio_path=audio_path,
                prompt="prompt",
                provider="avalai",
            )

        self.assertEqual(
            fake_client.chat.completions.last_kwargs.get("extra_body"),
            {"provider": "google"},
        )


if __name__ == "__main__":
    unittest.main()
