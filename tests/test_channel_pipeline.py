import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from versline.services.channel_archive.filters import FileFilter
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


class FileSource(FakeSource):
    """Writes each item's source_ref (bytes) as the downloaded file, with the extension of its file name."""

    def download(self, post, item, dest_dir, stem, progress_callback=None):
        dest_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(item.file_name).suffix if item.file_name else ""
        path = dest_dir / f"{stem}{suffix}"
        path.write_bytes(item.source_ref)
        self.downloads.append(path)
        return path


def doc_post(pid, day, name, data=b"pdf-bytes", text=""):
    return ChannelPost(id=pid, date=BASE + timedelta(days=day), text=text,
                       media=[MediaItem(kind="document", file_name=name, size=len(data), source_ref=data)])


class TestFileFilterPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.out = self.tmp / "out"

    def run_archive(self, posts, flt=None, files_only=False, **opts):
        source = FileSource(posts)
        ctx = StepContext(source=source, channel=None, out_dir=None, temp_dir=self.tmp / "tmp", file_filter=flt,
                          transcribe=False, keep_media=opts.pop("keep_media", False))
        options = ArchiveOptions(out_dir=self.out, temp_dir=ctx.temp_dir, file_filter=flt, files_only=files_only, **opts)
        summary = ChannelArchiver(source, ctx, options).run("@testchan")
        return summary, source

    def test_regular_archive_keeps_only_posts_with_matching_files(self):
        posts = [doc_post(1, 0, "جزوه_فقه.pdf"), doc_post(2, 1, "عکس.zip"), ChannelPost(id=3, date=BASE, text="متن")]
        flt = FileFilter.build(ext="pdf", match=["جزوه"])
        summary, _ = self.run_archive(posts, flt, keep_media=True)
        self.assertEqual(summary.done, 1)
        self.assertEqual(len(list((self.out / "posts").glob("*.md"))), 1)

    def test_album_downloads_only_matching_item(self):
        album = ChannelPost(id=5, date=BASE, media=[
            MediaItem(kind="photo", size=1, source_ref=b"img"),
            MediaItem(kind="document", file_name="a.pdf", size=3, source_ref=b"pdf"),
        ])
        _, source = self.run_archive([album], FileFilter.build(ext="pdf"), keep_media=True)
        self.assertEqual([p.name for p in source.downloads], ["testchan_5_2.pdf"])

    def test_dry_run_lists_matching_file_names(self):
        flt = FileFilter.build(ext="pdf")
        summary, source = self.run_archive([doc_post(1, 0, "a.pdf"), doc_post(2, 1, "b.zip")], flt, dry_run=True)
        self.assertEqual([(p.id, p.files) for p in summary.plans], [(1, ["a.pdf"])])
        self.assertEqual(source.downloads, [])

    def test_files_only_saves_original_names_without_notes(self):
        posts = [doc_post(1, 0, "جزوه فقه.pdf", b"one"), doc_post(2, 1, "draft.pdf", b"two"), doc_post(3, 2, "x.zip", b"three")]
        flt = FileFilter.build(ext="pdf", exclude=["draft"])
        summary, source = self.run_archive(posts, flt, files_only=True)
        self.assertEqual((summary.done, summary.files_saved, summary.duplicates), (1, 1, 0))
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), [".versline-files.json", "جزوه فقه.pdf"])
        self.assertEqual((self.out / "جزوه فقه.pdf").read_bytes(), b"one")
        self.assertFalse((self.out / "posts").exists())
        self.assertTrue(all(not p.exists() for p in source.downloads))  # nothing left in temp
        self.assertFalse((self.out / ".versline-channel.json").exists())

    def test_files_only_rerun_skips_and_duplicates_are_detected(self):
        posts = [doc_post(1, 0, "a.pdf", b"same"), doc_post(2, 1, "a.pdf", b"same")]
        summary, _ = self.run_archive(posts, files_only=True)
        self.assertEqual((summary.files_saved, summary.duplicates), (1, 1))
        summary, source = self.run_archive(posts, files_only=True)
        self.assertEqual((summary.done, summary.skipped, source.downloads), (0, 2, []))

    def test_files_only_same_name_different_size_gets_suffix(self):
        posts = [doc_post(1, 0, "a.pdf", b"short"), doc_post(2, 1, "a.pdf", b"a longer file")]
        summary, _ = self.run_archive(posts, files_only=True)
        self.assertEqual(summary.files_saved, 2)
        self.assertEqual(sorted(p.name for p in self.out.glob("*.pdf")), ["a (post 2).pdf", "a.pdf"])

    def test_files_only_skips_undownloadable_and_oversized(self):
        item = MediaItem(kind="document", file_name="web.pdf", downloadable=False)
        posts = [ChannelPost(id=1, date=BASE, media=[item]), doc_post(2, 1, "big.pdf", b"x" * 10)]
        source = FileSource(posts)
        ctx = StepContext(source=source, channel=None, out_dir=None, temp_dir=self.tmp / "tmp", transcribe=False,
                          max_size_mb=1e-6)
        options = ArchiveOptions(out_dir=self.out, temp_dir=ctx.temp_dir, files_only=True)
        summary = ChannelArchiver(source, ctx, options).run("@testchan")
        self.assertEqual((summary.done, summary.skipped, summary.files_saved), (0, 2, 0))
        self.assertEqual(source.downloads, [])


if __name__ == "__main__":
    unittest.main()
