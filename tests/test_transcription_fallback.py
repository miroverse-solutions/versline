"""Fallback model for chunks the main model blocks (content policy), and the report of skipped time ranges."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from versline.config import settings
from versline.services import transcription as tr
from versline.services.transcription import AudioTranscriber, ContentBlockedError, uncovered_ranges

LLM_FIELDS = ("provider", "model", "api_key", "api_endpoint", "proxy", "extra_body", "avalai_provider")
FALLBACK_FIELDS = ("fallback_model", "fallback_provider", "fallback_api_key", "fallback_api_endpoint", "fallback_proxy",
                   "fallback_own_settings", "fallback_extra_body")


class _SettingsCase(unittest.TestCase):
    def setUp(self):
        self._llm = {k: getattr(settings.llm, k) for k in LLM_FIELDS}
        self._tr = {k: getattr(settings.transcription, k) for k in FALLBACK_FIELDS}
        settings.llm.provider = "Google"
        settings.llm.model = "gemini-main"
        settings.llm.api_key = "gemini-key"
        settings.llm.api_endpoint = None
        settings.llm.proxy = None
        settings.llm.extra_body = None
        for k in FALLBACK_FIELDS:
            setattr(settings.transcription, k, None)
        self._cwd = tempfile.TemporaryDirectory()
        self._old_cwd = Path.cwd()
        import os
        os.chdir(self._cwd.name)

    def tearDown(self):
        import os
        os.chdir(self._old_cwd)
        self._cwd.cleanup()
        for k, v in self._llm.items():
            setattr(settings.llm, k, v)
        for k, v in self._tr.items():
            setattr(settings.transcription, k, v)


class TestFallbackConfig(_SettingsCase):
    def test_disabled_without_model(self):
        self.assertIsNone(AudioTranscriber().fallback_config())
        settings.transcription.fallback_model = "  "
        self.assertIsNone(AudioTranscriber().fallback_config())

    def test_same_provider_inherits_key_and_endpoint(self):
        settings.transcription.fallback_model = "gemini-other"
        settings.llm.api_endpoint = "https://example/v1"
        cfg = AudioTranscriber().fallback_config()
        self.assertEqual(cfg["provider"], "Google")
        self.assertEqual(cfg["api_key"], "gemini-key")
        self.assertEqual(cfg["api_endpoint"], "https://example/v1")

    def test_other_provider_does_not_inherit_key(self):
        settings.transcription.fallback_model = "openai/gpt-4o-audio-preview"
        settings.transcription.fallback_provider = "OpenRouter"
        settings.llm.proxy = "socks5://p"
        cfg = AudioTranscriber().fallback_config()
        self.assertIsNone(cfg["api_key"])
        self.assertIsNone(cfg["api_endpoint"])
        self.assertEqual(cfg["proxy"], "socks5://p")
        settings.transcription.fallback_api_key = "or-key"
        self.assertEqual(AudioTranscriber().fallback_config()["api_key"], "or-key")

    def test_provider_aliases_count_as_same(self):
        settings.transcription.fallback_model = "gemini-other"
        settings.transcription.fallback_provider = "gemini"
        self.assertEqual(AudioTranscriber().fallback_config()["api_key"], "gemini-key")


class TestFallbackOwnSettings(_SettingsCase):
    def setUp(self):
        super().setUp()
        settings.llm.extra_body = {"reasoning": {"max_tokens": 1500}}
        settings.llm.avalai_provider = "google"
        settings.transcription.fallback_model = "gemini-other"

    def test_same_provider_inherits_extras_by_default(self):
        cfg = AudioTranscriber().fallback_config()
        self.assertEqual(cfg["extra_body"], {"reasoning": {"max_tokens": 1500}})
        self.assertEqual(cfg["avalai_provider"], "google")

    def test_own_settings_drop_extras_but_keep_key(self):
        settings.transcription.fallback_own_settings = True
        cfg = AudioTranscriber().fallback_config()
        self.assertIsNone(cfg["extra_body"])
        self.assertIsNone(cfg["avalai_provider"])
        self.assertEqual(cfg["api_key"], "gemini-key")

    def test_explicit_extra_body_wins_in_both_modes(self):
        settings.transcription.fallback_extra_body = {"thinking": False}
        self.assertEqual(AudioTranscriber().fallback_config()["extra_body"], {"thinking": False})
        settings.transcription.fallback_own_settings = True
        self.assertEqual(AudioTranscriber().fallback_config()["extra_body"], {"thinking": False})

    def test_config_set_validates_and_compacts_extra_body(self):
        from versline.bridge.tools import system
        key = "VERSLINE_TRANSCRIPTION_FALLBACK_EXTRA_BODY"
        with patch("versline.userenv.update_env") as update, patch.object(system, "config_get", return_value={}):
            with self.assertRaises(ValueError):
                system.config_set(system.ConfigSetParams(values={key: "[1]"}), None)
            with self.assertRaises(ValueError):
                system.config_set(system.ConfigSetParams(values={key: "{bad"}), None)
            system.config_set(system.ConfigSetParams(values={key: '{"a": {"b": 1}}'}), None)
        self.assertEqual(update.call_args[0][0][key], '{"a":{"b":1}}')


class TestUncoveredRanges(unittest.TestCase):
    def test_overlap_covered_by_neighbours_is_not_missing(self):
        chunks = [
            {"start": 0, "end": 900, "ok": True},
            {"start": 720, "end": 1620, "ok": False},
            {"start": 1440, "end": 2340, "ok": True},
        ]
        self.assertEqual(uncovered_ranges(chunks), [(900, 1440)])

    def test_consecutive_skipped_chunks_join(self):
        chunks = [
            {"start": 0, "end": 900, "ok": True},
            {"start": 720, "end": 1620, "ok": False},
            {"start": 1440, "end": 2340, "ok": False},
            {"start": 2160, "end": 3060, "ok": True},
        ]
        self.assertEqual(uncovered_ranges(chunks), [(900, 2160)])

    def test_first_and_last_chunks(self):
        chunks = [
            {"start": 0, "end": 900, "ok": False},
            {"start": 720, "end": 1620, "ok": True},
            {"start": 1440, "end": 2000, "ok": False},
        ]
        self.assertEqual(uncovered_ranges(chunks), [(0, 720), (1620, 2000)])

    def test_clock_format(self):
        self.assertEqual(tr.format_clock(75), "1:15")
        self.assertEqual(tr.format_clock(3725), "1:02:05")


class TestBlockDetection(unittest.TestCase):
    def test_markers(self):
        self.assertTrue(tr._is_content_block("finish_reason=content_filter"))
        self.assertTrue(tr._is_content_block("PROHIBITED_CONTENT"))
        self.assertTrue(tr._is_content_block("Error code: 400 - {'code': 'content_policy_violation'}"))
        self.assertTrue(tr._is_content_block("finish_reason: SAFETY"))
        self.assertFalse(tr._is_content_block("Connection reset by peer"))
        self.assertFalse(tr._is_content_block("safety margin exceeded"))

    def _completion(self, content, finish):
        msg = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=finish)], usage=None)

    def test_openai_finish_reason_content_filter(self, *_):
        client = MagicMock()
        client.base_url = "https://example/v1"
        client.chat.completions.create.return_value = self._completion(None, "content_filter")
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ContentBlockedError):
            # Not NamedTemporaryFile: Windows cannot reopen it while it is held open.
            audio = Path(d) / "chunk.mp3"
            audio.write_bytes(b"")
            AudioTranscriber().transcribe_audio_chunk_by_openaicompatible(client, "m", str(audio), "p", provider="openai")

    def test_openai_sdk_error_with_content_filter(self):
        client = MagicMock()
        client.base_url = "https://example/v1"
        client.chat.completions.create.side_effect = RuntimeError("Error code: 400 - {'code': 'content_filter'}")
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ContentBlockedError):
            # Not NamedTemporaryFile: Windows cannot reopen it while it is held open.
            audio = Path(d) / "chunk.mp3"
            audio.write_bytes(b"")
            AudioTranscriber().transcribe_audio_chunk_by_openaicompatible(client, "m", str(audio), "p", provider="openai")

    def _gemini_client(self, response):
        client = MagicMock()
        client.files.upload.return_value = SimpleNamespace(state=SimpleNamespace(name="ACTIVE"), name="f1")
        client.models.generate_content.return_value = response
        return client

    def test_gemini_prompt_block(self):
        response = SimpleNamespace(
            usage_metadata=None, text=None, candidates=[],
            prompt_feedback=SimpleNamespace(block_reason=SimpleNamespace(name="PROHIBITED_CONTENT")),
        )
        client = self._gemini_client(response)
        with self.assertRaises(ContentBlockedError):
            AudioTranscriber().transcribe_audio_chunk_by_gemini(client, "gemini", "x.mp3", "p")
        client.files.delete.assert_called_once()

    def test_gemini_safety_finish(self):
        response = SimpleNamespace(
            usage_metadata=None, text=None, prompt_feedback=None,
            candidates=[SimpleNamespace(finish_reason="FinishReason.SAFETY")],
        )
        with self.assertRaises(ContentBlockedError):
            AudioTranscriber().transcribe_audio_chunk_by_gemini(self._gemini_client(response), "gemini", "x.mp3", "p")

    def test_blocked_is_not_retried(self):
        t = AudioTranscriber()
        settings_provider = settings.llm.provider
        settings.llm.provider = "openai"
        try:
            with patch.object(t, "transcribe_audio_chunk_by_openaicompatible",
                              side_effect=ContentBlockedError("blocked")) as call, \
                 patch.object(tr.ai, "configure_openai", return_value=MagicMock()), \
                 patch.object(tr.time, "sleep"):
                with self.assertRaises(ContentBlockedError):
                    t.transcribe_chunk_with_retry("gpt", "x.mp3", "p", max_retries=3)
            self.assertEqual(call.call_count, 1)
        finally:
            settings.llm.provider = settings_provider


class _ChunkLoopCase(_SettingsCase):
    """_process_file_internal with ffmpeg and the API mocked: four 900s chunks, 180s overlap (step 720s)."""

    def _run(self, blocked_by, skip_blocked=False, force=False, reuse_only=False):
        """blocked_by: {chunk_index: set of models that block it}."""
        calls = []
        chunks = [f"/tmp/chunk_{i:03d}.mp3" for i in range(4)]

        def fake(model_name, audio_path, prompt, max_retries=None):
            index = chunks.index(audio_path)
            calls.append((index, model_name, settings.llm.model, settings.llm.provider, settings.llm.api_key))
            if model_name in blocked_by.get(index, set()):
                raise ContentBlockedError(f"blocked by {model_name}")
            return f"متن تکه {index} " * 10

        t = AudioTranscriber()
        audio = Path("talk.mp3")
        audio.write_bytes(b"x")
        with patch.object(t, "transcribe_chunk_with_retry", side_effect=fake), \
             patch.object(tr.media, "split_audio_with_ffmpeg", return_value=chunks), \
             patch.object(tr.media, "get_audio_duration", return_value=900.0):
            text = t._process_file_internal(
                str(audio), 900, 180, None, force, reuse_only=reuse_only, skip_blocked=skip_blocked
            )
        return t, text, calls


class TestChunkLoop(_ChunkLoopCase):
    def test_blocked_chunk_goes_to_fallback_then_back_to_main(self):
        settings.transcription.fallback_model = "gpt-4o-audio"
        settings.transcription.fallback_provider = "OpenRouter"
        settings.transcription.fallback_api_key = "or-key"
        t, text, calls = self._run({1: {"gemini-main"}})
        self.assertEqual([(c[0], c[1]) for c in calls], [
            (0, "gemini-main"), (1, "gemini-main"), (1, "gpt-4o-audio"), (2, "gemini-main"), (3, "gemini-main"),
        ])
        fallback_call = calls[2]
        self.assertEqual(fallback_call[2:], ("gpt-4o-audio", "OpenRouter", "or-key"))
        self.assertEqual(calls[3][2:], ("gemini-main", "Google", "gemini-key"))
        self.assertEqual(settings.llm.model, "gemini-main")
        self.assertEqual(t.skipped_ranges, [])
        self.assertIn("متن تکه 1", text)

    def test_both_block_skips_chunk_and_reports_range(self):
        settings.transcription.fallback_model = "gpt-4o-audio"
        t, text, calls = self._run({1: {"gemini-main", "gpt-4o-audio"}})
        self.assertEqual([c[0] for c in calls], [0, 1, 1, 2, 3])
        self.assertEqual(len(t.skipped_ranges), 1)
        r = t.skipped_ranges[0]
        self.assertEqual((r["start"], r["end"]), (900, 1440))
        self.assertEqual((r["start_label"], r["end_label"]), ("15:00", "24:00"))
        self.assertEqual(r["models"], ["gemini-main", "gpt-4o-audio"])
        self.assertIn("15:00 تا 24:00 پیاده نشد", text)
        self.assertIn("متن تکه 2", text)
        progress = json.loads(next(Path("work_dir").glob("*/progress.json")).read_text(encoding="utf-8"))
        self.assertEqual(progress["skipped"][0]["index"], 1)

    def test_no_fallback_stops_like_before(self):
        with self.assertRaises(ContentBlockedError) as ctx:
            self._run({1: {"gemini-main"}})
        self.assertIn("--fallback-model", str(ctx.exception))

    def test_no_fallback_with_skip_blocked_skips(self):
        t, text, calls = self._run({2: {"gemini-main"}}, skip_blocked=True)
        self.assertEqual([c[0] for c in calls], [0, 1, 2, 3])
        self.assertEqual(t.skipped_ranges[0]["models"], ["gemini-main"])
        self.assertEqual((t.skipped_ranges[0]["start"], t.skipped_ranges[0]["end"]), (1620, 2160))

    def test_consecutive_skipped_chunks_leave_one_placeholder(self):
        settings.transcription.fallback_model = "gpt-4o-audio"
        both = {"gemini-main", "gpt-4o-audio"}
        t, text, _ = self._run({1: both, 2: both})
        self.assertEqual([(r["start"], r["end"]) for r in t.skipped_ranges], [(900, 2160)])
        self.assertEqual(text.count("پیاده نشد"), 1)
        self.assertIn("15:00 تا 36:00", text)

    def test_skipped_ranges_survive_resume(self):
        settings.transcription.fallback_model = "gpt-4o-audio"
        self._run({1: {"gemini-main", "gpt-4o-audio"}})
        t, _, calls = self._run({})
        self.assertEqual(calls, [])  # everything was already done
        self.assertEqual([(r["start"], r["end"]) for r in t.skipped_ranges], [(900, 1440)])


class TestReuseTranscript(_ChunkLoopCase):
    """--reuse-transcript: no main-transcription calls; --force must not wipe the cached transcript."""

    def test_reuse_skips_transcription_even_with_force(self):
        _, first_text, _ = self._run({})
        t, text, calls = self._run({}, force=True, reuse_only=True)
        self.assertEqual(calls, [])
        self.assertEqual(text, first_text)
        self.assertTrue(next(Path("work_dir").glob("*/progress.json")).exists())

    def test_reuse_keeps_skipped_ranges(self):
        settings.transcription.fallback_model = "gpt-4o-audio"
        self._run({1: {"gemini-main", "gpt-4o-audio"}})
        t, text, calls = self._run({}, reuse_only=True)
        self.assertEqual(calls, [])
        self.assertEqual([(r["start"], r["end"]) for r in t.skipped_ranges], [(900, 1440)])
        self.assertIn("15:00 تا 24:00 پیاده نشد", text)

    def test_reuse_fails_on_incomplete_cache(self):
        with self.assertRaises(ContentBlockedError):
            self._run({2: {"gemini-main"}})  # stops at chunk 3, two chunks cached
        with self.assertRaises(RuntimeError) as ctx:
            self._run({}, reuse_only=True)
        self.assertIn("incomplete (2/4", str(ctx.exception))

    def test_reuse_without_cache_fails(self):
        with self.assertRaises(RuntimeError):
            self._run({}, reuse_only=True)


class TestCommandReport(unittest.TestCase):
    def test_message_names_ranges_and_models(self):
        from versline.commands import transcribe as cmd

        cmd.warnings.clear()
        cmd.report_skipped(Path("talk.mp3"), Path("out/talk.md"), [{
            "start": 900, "end": 1440, "start_label": "15:00", "end_label": "24:00",
            "models": ["gemini-main", "gpt-4o-audio"], "chunks": [2], "reason": "x",
        }])
        self.assertEqual(len(cmd.warnings), 1)
        message = cmd.warnings[0]["message"]
        self.assertIn("from 15:00 to 24:00 was NOT transcribed", message)
        self.assertIn("gemini-main and gpt-4o-audio", message)
        cmd.warnings.clear()


if __name__ == "__main__":
    unittest.main()
