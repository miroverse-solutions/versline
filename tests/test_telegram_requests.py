import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from versline.services.channel_archive.models import MediaItem
from versline.services.telegram_requests import (
    MARK,
    MAX_ATTEMPTS,
    RequestOptions,
    RequestProcessor,
    RequestState,
    classify,
    is_request,
)

SEGMENTS = [
    {"start": 0.0, "end": 30.0, "text": "بحث امروز درباره‌ی صبر است."},
    {"start": 30.0, "end": 60.0, "text": "امام صادق علیه السلام فرمودند الصبر راس الایمان."},
    {"start": 60.0, "end": 90.0, "text": "در پایان دو نکته درباره‌ی تربیت فرزند."},
]


def msg(id, text="", out=True, reply_to=None, voice=False, kind=None):
    return SimpleNamespace(id=id, message=text, out=out, reply_to_msg_id=reply_to, voice=voice, video_note=None,
                           audio=None, action=None, date=datetime(2026, 11, 1, tzinfo=timezone.utc), kind=kind)


class FakeSource:
    def __init__(self, messages, entity=None):
        self.messages = {m.id: m for m in messages}
        self.entity = entity or SimpleNamespace(id=555, username=None, title="صندوق")
        self.sent = []
        self.fail_get = set()

    def entity_of(self, ref):
        return self.entity

    def peer_id(self, entity):
        return -100555

    def messages_after(self, entity, after_id=0, since=None, limit=None):
        return [m for i, m in sorted(self.messages.items()) if i > after_id]

    def get_messages(self, entity, ids):
        if set(ids) & self.fail_get:
            raise ValueError("network down")
        return [self.messages[i] for i in ids if i in self.messages]

    @staticmethod
    def _media_item(m):
        if m.kind is None:
            return None
        return MediaItem(kind=m.kind, file_name="talk.mp3" if m.kind == "audio" else None, source_ref=m)

    def download_message(self, m, dest_dir, stem):
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / f"{stem}.mp3"
        path.write_bytes(f"bytes of {m.id}".encode())
        return path

    def send(self, entity, text, parse_mode=None, file=None, link_preview=True, reply_to=None):
        self.sent.append({"text": text, "reply_to": reply_to, "file": file})
        return {"id": 1000 + len(self.sent)}


class FakeLLM:
    """Classifies by keyword, then answers taqrir/find prompts."""

    def __init__(self):
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        if "Classify a request" in prompt:
            request = prompt.split('"""')[1]
            if "تقریر" in request:
                return json.dumps({"mode": "taqrir", "query": "", "instruction": ""})
            return json.dumps({"mode": "find", "query": request.strip(), "instruction": ""})
        if "Find passages" in prompt:
            return json.dumps({"passages": [{"quote": "امام صادق علیه السلام فرمودند الصبر راس الایمان",
                                             "start": "0:00:30", "end": "0:01:00", "attribution": "امام صادق (ع)",
                                             "context": "حدیث", "relevance": "high"}]}, ensure_ascii=False)
        return "### تقریر\nمتن تقریر"


class FakeTranscriber:
    def __init__(self):
        self.calls = []
        self.skipped_ranges = []

    def process_file(self, path, **kwargs):
        self.calls.append((Path(path).name, kwargs.get("timestamped", False)))
        if kwargs.get("timestamped"):
            return {"text": " ".join(s["text"] for s in SEGMENTS), "segments": SEGMENTS}
        if Path(path).name.startswith("request_"):
            return "روایت امام صادق درباره‌ی صبر"  # a voice request
        return " ".join(s["text"] for s in SEGMENTS)


class ClassifyTests(unittest.TestCase):
    def test_llm_answer(self):
        self.assertEqual(classify(FakeLLM(), "تقریر کن")["mode"], "taqrir")
        intent = classify(FakeLLM(), "روایت امام صادق")
        self.assertEqual((intent["mode"], intent["query"]), ("find", "روایت امام صادق"))

    def test_heuristic_when_llm_fails(self):
        broken = SimpleNamespace(generate=lambda prompt: "not json")
        self.assertEqual(classify(broken, "لطفاً تقریر کن")["mode"], "taqrir")
        self.assertEqual(classify(broken, "اون حدیثی که خوند")["mode"], "find")


class IsRequestTests(unittest.TestCase):
    def test_rules(self):
        self.assertTrue(is_request(msg(2, "تقریر", reply_to=1)))
        self.assertTrue(is_request(msg(2, "", reply_to=1, voice=True)))
        self.assertFalse(is_request(msg(2, "تقریر", reply_to=1, out=False)))  # another member
        self.assertFalse(is_request(msg(2, "تقریر")))  # not a reply
        self.assertFalse(is_request(msg(2, f"{MARK} پاسخ", reply_to=1)))  # Versline's own reply
        self.assertFalse(is_request(msg(2, "", reply_to=1)))


class ProcessorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"VERSLINE_CACHE_DIR": str(root / "cache")})
        self.env.start()
        self.duration = mock.patch("versline.services.media.get_audio_duration", return_value=90.0)
        self.duration.start()
        self.out = root / "vault" / "Telegram"
        self.state = RequestState(root / "state.json")
        self.options = RequestOptions(output_dir=self.out, temp_dir=root / "temp", clip=False, refine=False)
        self.cwd = os.getcwd()
        os.chdir(root)

    def tearDown(self):
        os.chdir(self.cwd)
        self.duration.stop()
        self.env.stop()
        self.tmp.cleanup()

    def processor(self, source, transcriber=None, options=None):
        return RequestProcessor(source, FakeLLM(), transcriber or FakeTranscriber(), lambda note: FakeTranscriber(),
                                options or self.options, self.state)

    def test_answers_taqrir_and_find_and_ignores_others(self):
        source = FakeSource([
            msg(1, "", kind="audio"),
            msg(2, "تقریر کن", reply_to=1),
            msg(3, "روایت امام صادق درباره‌ی صبر", reply_to=1),
            msg(4, "نظر من", reply_to=1, out=False),  # another member
            msg(5, "سلام"),  # not a reply
            msg(6, "یک جواب", reply_to=5),  # reply to a text message, not a talk
        ])
        transcriber = FakeTranscriber()
        summary = self.processor(source, transcriber).run("me")
        self.assertEqual((summary.processed, summary.failed), (2, 0))
        self.assertEqual(transcriber.calls, [("talk_1.mp3", False), ("talk_1.mp3", True)])  # once, then cached
        taqrir = self.out / "talk - تقریر.md"
        points = self.out / "talk - نکته‌ها.md"
        self.assertTrue(taqrir.exists() and points.exists())
        self.assertIn("متن تقریر", taqrir.read_text(encoding="utf-8"))
        self.assertIn("0:00:30–0:01:00 — امام صادق (ع)", points.read_text(encoding="utf-8"))
        self.assertEqual({s["reply_to"] for s in source.sent}, {2, 3})
        self.assertTrue(all(s["text"].startswith(MARK) for s in source.sent))
        self.assertEqual(self.state.chat(-100555)["last_id"], 6)

    def test_second_run_reads_only_new_messages(self):
        source = FakeSource([msg(1, "", kind="audio"), msg(2, "تقریر کن", reply_to=1)])
        self.processor(source).run("me")
        sent = len(source.sent)
        source.messages[7] = msg(7, f"{MARK} **تقریر**", reply_to=2)  # our own reply showing up in the chat
        source.messages[8] = msg(8, "روایت امام صادق", reply_to=1)
        transcriber = FakeTranscriber()
        summary = self.processor(source, transcriber).run("me")
        self.assertEqual(summary.processed, 1)
        self.assertEqual(transcriber.calls, [])  # the talk's transcript is remembered by its message
        self.assertEqual([s["reply_to"] for s in source.sent[sent:]], [8])

    def test_voice_request_is_transcribed(self):
        source = FakeSource([msg(1, "", kind="voice"), msg(2, "", reply_to=1, voice=True)])
        transcriber = FakeTranscriber()
        summary = self.processor(source, transcriber).run("me")
        self.assertEqual(summary.processed, 1)
        self.assertIn(("request_2.mp3", False), transcriber.calls)
        self.assertTrue((self.out / "صندوق 1 - نکته‌ها.md").exists())

    def test_failed_request_is_retried_then_given_up(self):
        source = FakeSource([msg(1, "", kind="audio"), msg(2, "تقریر کن", reply_to=1)])
        source.fail_get = {1}
        for attempt in range(1, MAX_ATTEMPTS + 1):
            summary = self.processor(source).run("me")
            self.assertEqual(summary.failed, 1)
            self.assertEqual(self.state.chat(-100555)["failed"], {"2": attempt})
        self.assertIn("دفعه‌ی بعد", source.sent[0]["text"])
        self.assertNotIn("دفعه‌ی بعد", source.sent[-1]["text"])
        summary = self.processor(source).run("me")  # given up: not tried again
        self.assertEqual((summary.failed, summary.processed), (0, 0))

    def test_retry_succeeds(self):
        source = FakeSource([msg(1, "", kind="audio"), msg(2, "تقریر کن", reply_to=1)])
        source.fail_get = {1}
        self.processor(source).run("me")
        source.fail_get = set()
        summary = self.processor(source).run("me")
        self.assertEqual(summary.processed, 1)
        self.assertEqual(self.state.chat(-100555)["failed"], {})

    def test_dry_run_changes_nothing(self):
        source = FakeSource([msg(1, "", kind="audio"), msg(2, "تقریر کن", reply_to=1)])
        options = RequestOptions(output_dir=self.out, temp_dir=Path(self.tmp.name) / "temp", dry_run=True)
        summary = self.processor(source, options=options).run("me")
        self.assertEqual([p["id"] for p in summary.pending], [2])
        self.assertEqual(source.sent, [])
        self.assertEqual(self.state.chat(-100555)["last_id"], 0)

    def test_no_reply_option_only_writes_notes(self):
        source = FakeSource([msg(1, "", kind="audio"), msg(2, "تقریر کن", reply_to=1)])
        options = RequestOptions(output_dir=self.out, temp_dir=Path(self.tmp.name) / "temp", reply=False)
        summary = self.processor(source, options=options).run("me")
        self.assertEqual(summary.processed, 1)
        self.assertEqual(source.sent, [])


if __name__ == "__main__":
    unittest.main()
