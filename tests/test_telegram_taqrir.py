import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from typer.testing import CliRunner

from versline.services.channel_archive.discussion import (
    CACHE_NAME,
    DiscussionBuilder,
    DiscussionOptions,
    LogEntry,
    link_citations,
    render_log,
    split_log,
    truncate,
)
from versline.services.channel_archive.models import ChannelInfo, ChannelPost, MediaItem
from versline.services.channel_archive.steps import StepContext

BASE = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


class FakeSource:
    def __init__(self, posts, info=None):
        self.posts = posts
        self.info = info or ChannelInfo(ref="@grp", title="گروه مباحثه", username="grp", channel_id=7, kind="supergroup")
        self.downloads = []

    def resolve(self, ref):
        return self.info

    def iter_posts(self, channel, since=None, until=None, limit=None):
        for p in self.posts:
            if since and p.date < since:
                continue
            if until and p.date > until:
                break
            yield p

    def download(self, post, item, dest_dir, stem, progress_callback=None):
        dest_dir.mkdir(parents=True, exist_ok=True)
        ext = {"document": ".txt", "photo": ".jpg"}.get(item.kind, ".ogg")
        path = dest_dir / f"{stem}{ext}"
        path.write_text(item.source_ref or "x", encoding="utf-8")
        self.downloads.append(path)
        return path

    def close(self):
        pass


class FakeTranscriber:
    def __init__(self):
        self.calls = []

    def process_file(self, path, **kwargs):
        self.calls.append(path)
        return f"متن صوت {Path(path).stem}"


class FakeLLM:
    def __init__(self):
        self.prompts = []
        self.images = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        if "structured notes on THIS part" in prompt:
            return f"NOTES {len(self.prompts)} [#1]"
        if "points in dispute and the claims" in prompt:
            return "### محل بحث ۱: x\n- **گزاره ۱.۱:** الف [#1]\n  - **دلیل:** ب [#2, #3]"
        return "بله، حتماً. تقریر:\n\n### بحث\nمتن تقریر [#2]"

    def generate_with_image(self, prompt, path):
        self.images.append(path)
        return "متن تصویر"


def msg(pid, minutes, text="", sender=(1, "علی"), media=None, reply_to=None, url=True):
    return ChannelPost(id=pid, date=BASE + timedelta(minutes=minutes), text=text, media=media or [],
                       sender_id=sender[0], sender_name=sender[1], reply_to=reply_to,
                       url=f"https://t.me/grp/{pid}" if url else None)


class TestDiscussion(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.posts = [
            msg(1, 0, "آیا امر دلالت بر وجوب دارد؟"),
            msg(2, 5, "", sender=(2, "حسن"), reply_to=1, media=[MediaItem(kind="voice", duration=40, size=10)]),
            msg(3, 10, "این کتاب را ببینید", media=[MediaItem(kind="document", file_name="kifayah.txt", size=10,
                                                              source_ref="متن سند " * 50)]),
            msg(4, 15, "", sender=(2, "حسن"), media=[MediaItem(kind="photo", size=10)]),
        ]

    def build(self, source=None, llm=None, transcriber=None, **opts):
        source = source or FakeSource(self.posts)
        llm = llm or FakeLLM()
        transcriber = transcriber or FakeTranscriber()
        ctx = StepContext(source=source, channel=None, out_dir=None, temp_dir=self.tmp / "tmp", transcriber=transcriber)
        options = DiscussionOptions(out_dir=self.tmp / "out", temp_dir=ctx.temp_dir, **opts)
        result = DiscussionBuilder(source, ctx, options, text_llm=llm).run("@grp")
        return result, llm, transcriber, source

    def test_note_with_both_styles_and_anonymous_log(self):
        result, llm, tr, source = self.build(doc_chars=100)
        note = result.note_path.read_text(encoding="utf-8")
        self.assertIn("## تقریر", note)
        self.assertIn("## ادعاها و ادله", note)
        self.assertIn("متن تقریر ([#2](https://t.me/grp/2))", note)
        self.assertIn("([#2](https://t.me/grp/2)، [#3](https://t.me/grp/3))", note)
        self.assertNotIn("بله، حتماً", note)
        self.assertIn('style: "both"', note)
        self.assertIn("messages: 4", note)
        self.assertIn("voices: 1", note)
        self.assertNotIn("participants:", note)
        self.assertIn("kifayah.txt", note)  # sources section
        # the log the LLM saw: anonymous, with transcript, truncated document, image text and reply
        prompt = llm.prompts[0]
        self.assertNotIn("علی", prompt)
        self.assertNotIn("حسن", prompt)
        self.assertIn("شرکت‌کننده ۱", prompt)
        self.assertIn("شرکت‌کننده ۲ | در پاسخ به #1", prompt)
        self.assertIn("متن صوت grp_2_1", prompt)
        self.assertIn("[… بقیه متن حذف شد]", prompt)
        self.assertIn("متن تصویر", prompt)
        self.assertEqual(len(llm.prompts), 2)  # descriptive + claims, no map step for a short log
        self.assertEqual(len(llm.images), 1)
        log = result.log_path.read_text(encoding="utf-8")
        self.assertIn("^m3", log)
        self.assertEqual(list((self.tmp / "tmp").iterdir()), [])  # downloads cleaned up

    def test_attribute_names_participants(self):
        result, llm, _, _ = self.build(style="claims", attribute=True)
        self.assertIn("علی", llm.prompts[0])
        self.assertIn("حسن", llm.prompts[0])
        note = result.note_path.read_text(encoding="utf-8")
        self.assertIn('participants: ["علی", "حسن"]', note)
        self.assertNotIn("## تقریر\n", note)
        self.assertIn("## ادعاها و ادله", note)

    def test_cache_skips_extraction_on_rerun(self):
        self.build(style="descriptive")
        result, llm, tr, source = self.build(style="claims")
        self.assertEqual(tr.calls, [])
        self.assertEqual(llm.images, [])
        self.assertEqual(source.downloads, [])
        self.assertIn("متن صوت grp_2_1", llm.prompts[0])
        cache = json.loads((self.tmp / "out" / CACHE_NAME).read_text(encoding="utf-8"))
        self.assertIn("2:0", cache["media"])
        _, _, tr, _ = self.build(style="claims", force=True)
        self.assertEqual(len(tr.calls), 1)

    def test_flags_disable_media_reading(self):
        _, llm, tr, source = self.build(style="descriptive", transcribe=False, documents=False, images=False)
        self.assertEqual((tr.calls, llm.images, source.downloads), ([], [], []))
        self.assertIn("(پیام صوتی)", llm.prompts[0])

    def test_long_log_uses_map_reduce_and_caches_notes(self):
        self.posts = [msg(i, i * 60 * 24, "سخن " * 400, sender=(i % 2, f"p{i % 2}")) for i in range(1, 7)]
        result, llm, _, _ = self.build(style="descriptive", max_chars=3000)
        maps = [p for p in llm.prompts if "structured notes on THIS part" in p]
        self.assertGreater(len(maps), 1)
        self.assertIn("structured notes taken", llm.prompts[-1])
        self.assertIn("NOTES", llm.prompts[-1])
        _, llm2, _, _ = self.build(style="claims", max_chars=3000)
        self.assertEqual(len(llm2.prompts), 1)  # only the final write-up
        self.assertEqual(result.llm_calls, len(maps) + 1)

    def test_private_chat_links_to_log_blocks(self):
        info = ChannelInfo(ref="-55", title="شخصی", channel_id=55, kind="user")
        self.posts = [msg(1, 0, "سلام", url=False), msg(2, 1, "پاسخ", url=False)]
        result, _, _, _ = self.build(source=FakeSource(self.posts, info), style="descriptive")
        self.assertEqual(result.out_dir, self.tmp / "out")
        note = result.note_path.read_text(encoding="utf-8")
        self.assertIn(f"[[{result.log_path.stem}#^m2\\|#2]]", note)

    def test_dry_run_and_empty_range(self):
        result, llm, tr, source = self.build(dry_run=True)
        self.assertEqual(len(result.entries), 4)
        self.assertIsNone(result.note_path)
        self.assertEqual((llm.prompts, source.downloads), ([], []))
        result, _, _, _ = self.build(since=BASE + timedelta(days=30))
        self.assertEqual(result.entries, [])
        self.assertIsNone(result.note_path)

    def test_failed_media_is_reported_not_fatal(self):
        class BadTranscriber(FakeTranscriber):
            def process_file(self, path, **kwargs):
                raise RuntimeError("boom")

        result, llm, _, _ = self.build(transcriber=BadTranscriber(), style="descriptive")
        self.assertTrue(result.note_path.is_file())
        self.assertTrue(any("boom" in e for e in result.errors))
        self.assertIn("[خوانده نشد]", llm.prompts[0])
        cache = json.loads((self.tmp / "out" / CACHE_NAME).read_text(encoding="utf-8"))
        self.assertNotIn("2:0", cache["media"])  # retried next run


class TestHelpers(unittest.TestCase):
    def test_split_log_prefers_day_boundaries(self):
        entries = [LogEntry(post=msg(i, i * 60 * 24, "x" * 500), speaker="s") for i in range(4)]
        chunks = split_log(render_log(entries), 1300)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(c.startswith("==") for c in chunks))

    def test_split_log_cuts_long_day_between_messages(self):
        entries = [LogEntry(post=msg(i, i, "x" * 500), speaker="s") for i in range(4)]
        chunks = split_log(render_log(entries), 1300)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(sum(c.count("[#") for c in chunks), 4)

    def test_link_citations_unknown_ids_stay_plain(self):
        self.assertEqual(link_citations("x [#9]", {1: "u"}, "log"), "x (#9)")
        self.assertEqual(link_citations("x [#1](keep)", {1: "u"}, None), "x [#1](keep)")

    def test_truncate(self):
        self.assertEqual(truncate("abc", 10), "abc")
        self.assertIn("حذف شد", truncate("a\n" * 50, 10))


class TestTelegramSourceHelpers(unittest.TestCase):
    def test_normalize_ref_ids(self):
        from versline.services.channel_archive.sources.telegram import normalize_ref

        self.assertEqual(normalize_ref("-1001234"), -1001234)
        self.assertEqual(normalize_ref("me"), "me")
        self.assertEqual(normalize_ref("@grp"), "grp")

    def test_slug_and_links_by_kind(self):
        self.assertEqual(ChannelInfo(ref="x", title="t", channel_id=5, kind="user").slug, "chat_5")
        self.assertEqual(ChannelInfo(ref="x", title="t", channel_id=5).slug, "channel_5")
        self.assertFalse(ChannelInfo(ref="x", title="t", kind="group").linkable)
        self.assertTrue(ChannelInfo(ref="x", title="t", kind="supergroup").linkable)


class TestTaqrirCli(unittest.TestCase):
    def test_invalid_dates_and_style(self):
        from versline.commands.telegram import app

        runner = CliRunner()
        res = runner.invoke(app, ["taqrir", "@grp", "--since", "1404-13-01"])
        self.assertNotEqual(res.exit_code, 0)
        res = runner.invoke(app, ["taqrir", "@grp", "--since", "2026-03-05", "--until", "2026-03-01"])
        self.assertNotEqual(res.exit_code, 0)
        res = runner.invoke(app, ["taqrir", "@grp", "--style", "poem"])
        self.assertNotEqual(res.exit_code, 0)

    def test_dry_run_lists_messages(self):
        from versline.commands import telegram as tg

        posts = [msg(1, 0, "سلام بحث"), msg(2, 1, "", media=[MediaItem(kind="voice", duration=30)])]
        with mock.patch.object(tg, "_make_source", return_value=FakeSource(posts)):
            res = CliRunner().invoke(tg.app, ["taqrir", "@grp", "--since", "2026-03-01", "--dry-run"])
        self.assertEqual(res.exit_code, 0, res.output)
        self.assertIn("2 messages", res.output)
        self.assertIn("voice ×1", res.output)

    def test_negative_chat_id_after_double_dash(self):
        from versline.commands import telegram as tg

        source = FakeSource([msg(1, 0, "سلام")])
        refs = []
        source.resolve = lambda ref: refs.append(ref) or source.info
        with mock.patch.object(tg, "_make_source", return_value=source):
            res = CliRunner().invoke(tg.app, ["taqrir", "--dry-run", "--limit", "5", "--", "-1001234"])
        self.assertEqual(res.exit_code, 0, res.output)
        self.assertEqual(refs, ["-1001234"])


if __name__ == "__main__":
    unittest.main()
