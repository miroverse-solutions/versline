import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from versline.services import transcript_cache
from versline.services.audio_points import (
    FindResult,
    Passage,
    append_section,
    clock,
    find_passages,
    locate_quote,
    normalize,
    parse_clock,
    parse_json,
    render_find_section,
    windows,
    write_taqrir,
)
from versline.services.transcript_cache import Transcript

SEGMENTS = [
    {"start": 0.0, "end": 30.0, "text": "بسم الله الرحمن الرحیم. بحث امروز درباره‌ی صبر است."},
    {"start": 30.0, "end": 60.0, "text": "صبر سه قسم دارد: صبر بر طاعت، صبر از معصیت و صبر در مصیبت."},
    {"start": 60.0, "end": 90.0, "text": "امام صادق علیه السلام فرمودند: الصَّبْرُ رَأْسُ الْإِيمَانِ."},
    {"start": 90.0, "end": 120.0, "text": "یعنی صبر نسبت به ایمان مانند سر است نسبت به بدن."},
    {"start": 120.0, "end": 150.0, "text": "علامه طباطبایی در المیزان می‌گوید صبر ملکه‌ای نفسانی است."},
    {"start": 150.0, "end": 180.0, "text": "در پایان دو نکته درباره‌ی تربیت فرزند عرض می‌کنم."},
]


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self.replies.pop(0) if self.replies else "{}"


class ClockTests(unittest.TestCase):
    def test_round_trip(self):
        self.assertEqual(clock(3725), "1:02:05")
        self.assertEqual(parse_clock("1:02:05"), 3725)
        self.assertEqual(parse_clock("2:05"), 125)
        self.assertIsNone(parse_clock("soon"))


class LocateQuoteTests(unittest.TestCase):
    def test_normalize_ignores_diacritics_and_arabic_letters(self):
        self.assertEqual(normalize("الصَّبْرُ رَأْسُ الْإِيمَانِ"), normalize("الصبر راس الایمان"))

    def test_finds_quote_despite_small_differences(self):
        located = locate_quote("امام صادق فرمودند الصبر راس الایمان یعنی صبر نسبت به ایمان مانند سر است", SEGMENTS)
        self.assertIsNotNone(located)
        first, last, score = located
        self.assertEqual((first, last), (2, 3))
        self.assertGreaterEqual(score, 0.8)

    def test_rejects_invented_quote(self):
        self.assertIsNone(locate_quote("پیامبر فرمودند علم را از گهواره تا گور بجویید", SEGMENTS))

    def test_hint_breaks_ties(self):
        segments = [{"start": 0, "end": 10, "text": "صبر کلید فرج است"},
                    {"start": 10, "end": 20, "text": "مطلب دیگری"},
                    {"start": 20, "end": 30, "text": "صبر کلید فرج است"}]
        self.assertEqual(locate_quote("صبر کلید فرج است", segments, hint=25)[0], 2)
        self.assertEqual(locate_quote("صبر کلید فرج است", segments, hint=0)[0], 0)


class ParseJsonTests(unittest.TestCase):
    def test_code_fence_and_chatter(self):
        self.assertEqual(parse_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(parse_json('Here it is: {"a": [1, 2]} done'), {"a": [1, 2]})
        with self.assertRaises(ValueError):
            parse_json("nothing")


class WindowTests(unittest.TestCase):
    def test_windows_overlap_and_cover_everything(self):
        segments = [{"start": i * 10, "end": i * 10 + 10, "text": "x" * 88} for i in range(50)]
        parts = windows(segments, max_chars=1000, overlap_chars=200)
        self.assertGreater(len(parts), 1)
        self.assertEqual(parts[0][0], segments[0])
        self.assertEqual(parts[-1][-1], segments[-1])
        for a, b in zip(parts, parts[1:]):
            self.assertIn(b[0], a)  # each window starts inside the previous one

    def test_single_window_for_short_transcript(self):
        self.assertEqual(windows(SEGMENTS), [SEGMENTS])


class FindPassagesTests(unittest.TestCase):
    def test_times_come_from_transcript_and_invented_passages_are_dropped(self):
        reply = json.dumps({"passages": [
            {"quote": "امام صادق علیه السلام فرمودند: الصبر راس الایمان", "start": "0:09:00", "end": "0:10:00",
             "attribution": "امام صادق (ع)", "context": "حدیث درباره‌ی صبر", "relevance": "high"},
            {"quote": "این جمله اصلاً گفته نشده است و ساختگی است", "start": "0:00:10", "end": "0:00:20"},
        ]}, ensure_ascii=False)
        llm = FakeLLM([reply])
        found = find_passages(llm, Transcript(text="", segments=SEGMENTS), "روایت امام صادق درباره‌ی صبر")
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0].start, found[0].end), (60.0, 90.0))
        self.assertEqual(found[0].attribution, "امام صادق (ع)")
        self.assertIn("[0:01:00] امام صادق", llm.prompts[0])
        self.assertIn("روایت امام صادق", llm.prompts[0])

    def test_duplicates_from_overlapping_windows_are_merged(self):
        item = {"quote": "صبر سه قسم دارد صبر بر طاعت صبر از معصیت و صبر در مصیبت", "start": "0:00:30", "end": "0:01:00",
                "relevance": "medium"}
        llm = FakeLLM([json.dumps({"passages": [item]}), json.dumps({"passages": [dict(item, relevance="high")]})])
        with mock.patch("versline.services.audio_points.windows", return_value=[SEGMENTS[:3], SEGMENTS[1:]]):
            found = find_passages(llm, Transcript(text="", segments=SEGMENTS), "اقسام صبر")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].relevance, "high")

    def test_unreadable_reply_finds_nothing(self):
        self.assertEqual(find_passages(FakeLLM(["sorry"]), Transcript(text="", segments=SEGMENTS), "x"), [])


class WordBoundsTests(unittest.TestCase):
    WORDS = [{"start": 60 + i * 0.5, "end": 60.4 + i * 0.5, "word": w} for i, w in enumerate(
        "و امام صادق علیه السلام فرمودند الصبر راس الایمان پس".split())]

    def test_word_times_narrow_the_passage(self):
        reply = json.dumps({"passages": [{"quote": "امام صادق علیه السلام فرمودند الصبر راس الایمان", "start": "0:01:00"}]})
        found = find_passages(FakeLLM([reply]), Transcript(text="", segments=SEGMENTS, words=self.WORDS), "روایت")
        self.assertEqual((found[0].start, found[0].end), (60.5, 64.4))

    def test_segment_times_kept_when_words_disagree(self):
        words = [{"start": 61, "end": 62, "word": "چیز"}, {"start": 62, "end": 63, "word": "دیگری"}]
        reply = json.dumps({"passages": [{"quote": "امام صادق علیه السلام فرمودند الصبر راس الایمان", "start": "0:01:00"}]})
        found = find_passages(FakeLLM([reply]), Transcript(text="", segments=SEGMENTS, words=words), "روایت")
        self.assertEqual((found[0].start, found[0].end), (60.0, 90.0))


class TaqrirTests(unittest.TestCase):
    def test_short_text_one_call_with_instruction(self):
        llm = FakeLLM(["### مسئله\nمتن"])
        self.assertEqual(write_taqrir(llm, "متن سخنرانی", "فقط استدلال‌ها"), "### مسئله\nمتن")
        self.assertEqual(len(llm.prompts), 1)
        self.assertIn("Additional guidance from the user (follow it): فقط استدلال‌ها", llm.prompts[0])

    def test_long_text_is_written_in_parts(self):
        text = "\n".join("جمله‌ای از سخنرانی " * 20 for _ in range(400))
        llm = FakeLLM(["الف", "ب", "ج", "د", "ه"])
        with mock.patch("versline.services.audio_points.TAQRIR_PART_CHARS", len(text) // 3 + 10):
            out = write_taqrir(llm, text)
        self.assertGreaterEqual(len(llm.prompts), 3)
        self.assertTrue(out.startswith("الف\n\nب"))
        self.assertIn("part 1 of", llm.prompts[0])


class NoteTests(unittest.TestCase):
    def test_sections_accumulate_in_one_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "talk - نکته‌ها.md"
            first = FindResult("روایت صبر", [Passage("الصبر راس الایمان", 60, 90, "امام صادق (ع)", "حدیث", "high",
                                                    clip=Path(tmp) / "c.mp3")])
            append_section(note, render_find_section(first), "talk")
            append_section(note, render_find_section(FindResult("چیز دیگر")), "talk")
            text = note.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# talk\n"))
        self.assertIn("### 1. 0:01:00–0:01:30 — امام صادق (ع)", text)
        self.assertIn("> الصبر راس الایمان", text)
        self.assertIn("![[c.mp3]]", text)
        self.assertIn("## چیز دیگر", text)
        self.assertIn("پیدا نشد", text)


class FakeTranscriber:
    """Main pass returns the text; the timestamp pass (reusing it) returns native segments or fails."""

    def __init__(self, result, native=True):
        self.result = result
        self.native = native
        self.calls = 0
        self.timestamp_calls = []
        self.skipped_ranges = []

    def process_file(self, path, **kwargs):
        if kwargs.get("timestamped"):
            self.timestamp_calls.append(kwargs)
            if not self.native:
                raise RuntimeError("Native timestamps not available and native_timestamps_only is set")
            return {**self.result, "timestamp_method": "api_native_verbose_json"}
        self.calls += 1
        return self.result["text"]


class TranscriptCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"VERSLINE_CACHE_DIR": self.tmp.name})
        self.env.start()
        self.duration = mock.patch("versline.services.media.get_audio_duration", return_value=180.0)
        self.duration.start()
        self.audio = Path(self.tmp.name) / "talk.mp3"
        self.audio.write_bytes(b"audio-bytes")

    def tearDown(self):
        self.duration.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_second_call_uses_cache(self):
        transcriber = FakeTranscriber({"text": "متن کامل", "segments": SEGMENTS,
                                       "words": [{"start": 60, "end": 60.5, "word": "امام"}]})
        key, first = transcript_cache.get_or_transcribe(self.audio, transcriber)
        _, second = transcript_cache.get_or_transcribe(self.audio, transcriber)
        self.assertEqual(transcriber.calls, 1)
        self.assertEqual(len(transcriber.timestamp_calls), 1)
        ts = transcriber.timestamp_calls[0]
        self.assertTrue(ts["native_timestamps_only"] and ts["reuse_transcript"])  # no second transcription
        self.assertEqual(second.segments, first.segments)
        self.assertEqual(second.words, [{"start": 60.0, "end": 60.5, "word": "امام"}])
        self.assertEqual(second.timestamp_method, "api_native_verbose_json")
        self.assertFalse(second.approximate)
        transcript_cache.remember_alias("tg:1:2", key)
        self.assertEqual(transcript_cache.key_for_alias("tg:1:2"), key)
        self.assertIsNone(transcript_cache.key_for_alias("tg:1:3"))

    def test_force_transcribes_again(self):
        transcriber = FakeTranscriber({"text": "متن", "segments": SEGMENTS})
        transcript_cache.get_or_transcribe(self.audio, transcriber)
        transcript_cache.get_or_transcribe(self.audio, transcriber, force=True)
        self.assertEqual(transcriber.calls, 2)

    def test_missing_segments_are_estimated(self):
        text = "جمله‌ی اول. " * 40 + "\n" + "جمله‌ی دوم. " * 40
        _, transcript = transcript_cache.get_or_transcribe(self.audio, FakeTranscriber({"text": text}, native=False))
        self.assertTrue(transcript.approximate)
        self.assertEqual(transcript.timestamp_method, "")
        self.assertGreater(len(transcript.segments), 1)
        self.assertEqual(transcript.segments[0]["start"], 0)
        self.assertAlmostEqual(transcript.segments[-1]["end"], 180.0, places=1)


if __name__ == "__main__":
    unittest.main()
