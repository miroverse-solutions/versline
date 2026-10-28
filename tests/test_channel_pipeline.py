import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from versline.services.channel_archive.models import ChannelInfo, ChannelPost, MediaItem
from versline.services.channel_archive.pipeline import ArchiveOptions, ChannelArchiver
from versline.services.channel_archive.steps import StepContext, clean_transcript

BASE = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


class FakeSource:
    def __init__(self, posts):
        self.posts = posts
        self.downloads = []

    def resolve(self, ref):
        return ChannelInfo(ref=ref, title="کانال تست", username="testchan", channel_id=1)

    def iter_posts(self, channel, since=None, until=None, limit=None):
        for p in self.posts:
            if since and p.date < since:
                continue
            if until and p.date > until:
                break
            yield p

    def download(self, post, item, dest_dir, stem, progress_callback=None):
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / f"{stem}.mp3"
        path.write_bytes(b"x")
        self.downloads.append(path)
        return path

    def close(self):
        pass


class FakeTranscriber:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def process_file(self, path, **kwargs):
        self.calls.append(path)
        if self.fail_on and self.fail_on in path:
            raise RuntimeError("boom")
        return f"transcript of {Path(path).stem}"


def audio(pid, day, text=""):
    return ChannelPost(id=pid, date=BASE + timedelta(days=day), text=text,
                       media=[MediaItem(kind="audio", duration=30, size=10, source_ref=object())])


class FakeLLM:
    def __init__(self):
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return "TAQRIR TEXT" if "taqrir" in prompt.lower() else "SUMMARY TEXT"


class TestCleanTranscript(unittest.TestCase):
    def test_removes_preamble_and_end_marker_only(self):
        raw = "بله، حتماً. در ادامه پیاده‌سازی و ویراستاری این فایل صوتی تقدیم می‌گردد:\n\n**گوینده اول:** سلام\n\n[---پایان فایل صوتی---]"
        self.assertEqual(clean_transcript(raw), "**گوینده اول:** سلام")
        self.assertEqual(clean_transcript("بله، من آنجا بودم و گفتم:\n"), "بله، من آنجا بودم و گفتم:")
        keep = "[---خروجی ناقص است---]"
        self.assertEqual(clean_transcript(keep), keep)


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.posts = [
            audio(1, 0, "#علم درس یک"),
            ChannelPost(id=2, date=BASE + timedelta(days=1), text="فقط متن"),
            audio(3, 2, "درس سه"),
        ]

    def run_archive(self, source=None, transcriber=None, **opts):
        source = source or FakeSource(self.posts)
        transcriber = transcriber or FakeTranscriber()
        ctx = StepContext(source=source, channel=None, out_dir=None, temp_dir=self.tmp / "tmp", transcriber=transcriber,
                          keep_media=opts.pop("keep_media", False), transcribe=opts.pop("transcribe", True))
        options = ArchiveOptions(out_dir=self.tmp / "out", temp_dir=ctx.temp_dir, **opts)
        archiver = ChannelArchiver(source, ctx, options)
        return archiver, archiver.run("@testchan"), source, transcriber

    def test_non_downloadable_media_is_skipped_but_note_written(self):
        self.posts = [ChannelPost(id=9, date=BASE, text="x",
                                  media=[MediaItem(kind="audio", duration=30, downloadable=False)])]
        _, summary, source, tr = self.run_archive()
        self.assertEqual((summary.done, summary.failed), (1, 0))
        self.assertEqual(source.downloads, [])
        self.assertEqual(tr.calls, [])
        note = next((self.tmp / "out" / "posts").glob("*.md")).read_text(encoding="utf-8")
        self.assertIn("audio not downloadable", note)

    def test_notes_written_for_audio_and_text_posts(self):
        _, summary, _, tr = self.run_archive()
        self.assertEqual((summary.done, summary.failed), (3, 0))
        notes = sorted((self.tmp / "out" / "posts").glob("*.md"))
        self.assertEqual(len(notes), 3)
        body = notes[0].read_text(encoding="utf-8")
        self.assertIn("post_id: 1", body)
        self.assertIn("transcribed: true", body)
        self.assertIn("transcript of testchan_1", body)
        self.assertIn('"علم"', body)
        text_note = notes[1].read_text(encoding="utf-8")
        self.assertIn('media_type: "text"', text_note)
        self.assertNotIn("transcribed", text_note)
        self.assertEqual(len(tr.calls), 2)
        self.assertTrue((self.tmp / "out" / "کانال تست.md").is_file())

    def test_date_range_and_types_filter(self):
        _, summary, _, _ = self.run_archive(since=BASE + timedelta(days=1), until=BASE + timedelta(days=1, hours=5))
        self.assertEqual(summary.done, 1)
        _, summary, _, _ = self.run_archive(types={"audio"}, force=True)
        self.assertEqual(summary.done, 2)

    def test_rerun_skips_done_and_force_redoes(self):
        self.run_archive()
        _, summary, _, tr = self.run_archive()
        self.assertEqual((summary.done, summary.skipped), (0, 3))
        self.assertEqual(tr.calls, [])
        _, summary, _, _ = self.run_archive(force=True)
        self.assertEqual(summary.done, 3)
        self.assertEqual(len(list((self.tmp / "out" / "posts").glob("*.md"))), 3)  # no duplicates

    def test_failure_does_not_abort_and_is_retried(self):
        _, summary, _, _ = self.run_archive(transcriber=FakeTranscriber(fail_on="testchan_1"))
        self.assertEqual((summary.done, summary.failed), (2, 1))
        _, summary, _, _ = self.run_archive()
        self.assertEqual((summary.done, summary.skipped), (1, 2))

    def test_media_deleted_by_default_and_kept_with_flag(self):
        _, _, source, _ = self.run_archive()
        self.assertTrue(all(not p.exists() for p in source.downloads))
        _, _, _, _ = self.run_archive(keep_media=True, force=True)
        self.assertTrue((self.tmp / "out" / "attachments" / "testchan_1.mp3").is_file())
        self.assertIn("![[attachments/testchan_1.mp3]]", sorted((self.tmp / "out" / "posts").glob("*.md"))[0].read_text(encoding="utf-8"))

    def test_no_transcribe_and_dry_run(self):
        _, _, source, tr = self.run_archive(transcribe=False)
        self.assertEqual((tr.calls, source.downloads), ([], []))
        _, summary, _, _ = self.run_archive(dry_run=True)
        self.assertEqual(len(summary.plans), 3)

    def test_limit(self):
        _, summary, _, _ = self.run_archive(limit=2)
        self.assertEqual(summary.done, 2)


    def test_summary_goes_first_and_taqrir_after_transcript(self):
        self.posts = [audio(1, 0, "کپشن " * 80)]
        llm = FakeLLM()
        source, transcriber = FakeSource(self.posts), FakeTranscriber()
        ctx = StepContext(source=source, channel=None, out_dir=None, temp_dir=self.tmp / "tmp",
                          transcriber=transcriber, text_llm=llm)
        options = ArchiveOptions(out_dir=self.tmp / "out", temp_dir=ctx.temp_dir, steps=["media", "transcribe", "summary", "taqrir"])
        summary = ChannelArchiver(source, ctx, options).run("@testchan")
        self.assertEqual(summary.done, 1)
        note = next((self.tmp / "out" / "posts").glob("*.md")).read_text(encoding="utf-8")
        order = [note.index(h) for h in ("## خلاصه", "## توضیحات", "## متن پیاده‌شده", "## تقریر و صورت‌بندی")]
        self.assertEqual(order, sorted(order))
        self.assertIn("SUMMARY TEXT", note)
        self.assertIn("TAQRIR TEXT", note)

    def test_long_text_post_gets_taqrir_from_caption(self):
        self.posts = [ChannelPost(id=3, date=BASE, text="متن بلند " * 80)]
        llm = FakeLLM()
        source = FakeSource(self.posts)
        ctx = StepContext(source=source, channel=None, out_dir=None, temp_dir=self.tmp / "tmp", text_llm=llm, transcribe=False)
        options = ArchiveOptions(out_dir=self.tmp / "out", temp_dir=ctx.temp_dir, steps=["media", "taqrir"])
        ChannelArchiver(source, ctx, options).run("@testchan")
        self.assertEqual(len(llm.prompts), 1)
        self.assertIn("written channel post", llm.prompts[0])
        note = next((self.tmp / "out" / "posts").glob("*.md")).read_text(encoding="utf-8")
        self.assertIn("TAQRIR TEXT", note)

    def test_short_text_posts_get_no_summary_and_no_taqrir(self):
        self.posts = [ChannelPost(id=2, date=BASE, text="فقط متن")]
        llm = FakeLLM()
        source = FakeSource(self.posts)
        ctx = StepContext(source=source, channel=None, out_dir=None, temp_dir=self.tmp / "tmp", text_llm=llm, transcribe=False)
        options = ArchiveOptions(out_dir=self.tmp / "out", temp_dir=ctx.temp_dir, steps=["media", "summary", "taqrir"])
        ChannelArchiver(source, ctx, options).run("@testchan")
        self.assertEqual(llm.prompts, [])

    def test_reuse_transcripts_keeps_text_and_adds_new_sections_without_transcribing(self):
        self.posts = [audio(1, 0, "کپشن " * 80)]
        self.run_archive()
        llm = FakeLLM()
        source, transcriber = FakeSource(self.posts), FakeTranscriber()
        ctx = StepContext(source=source, channel=None, out_dir=None, temp_dir=self.tmp / "tmp",
                          transcriber=transcriber, text_llm=llm)
        options = ArchiveOptions(out_dir=self.tmp / "out", temp_dir=ctx.temp_dir, reuse_transcripts=True,
                                 steps=["media", "transcribe", "summary", "taqrir"])
        summary = ChannelArchiver(source, ctx, options).run("@testchan")
        self.assertEqual((summary.done, summary.skipped), (1, 0))
        self.assertEqual(transcriber.calls, [])
        self.assertEqual(source.downloads, [])
        note = next((self.tmp / "out" / "posts").glob("*.md")).read_text(encoding="utf-8")
        self.assertIn("transcript of", note)
        self.assertIn("SUMMARY TEXT", note)
        self.assertIn("TAQRIR TEXT", note)

if __name__ == "__main__":
    unittest.main()
