import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from versline.services.channel_archive.merge import (
    ends_with_marker, group_parts, merge_posts, starts_with_marker,
)
from versline.services.channel_archive.models import ChannelPost, MediaItem
from versline.services.channel_archive.pipeline import ArchiveOptions, ChannelArchiver
from versline.services.channel_archive.steps import StepContext
from tests.test_channel_pipeline import FakeSource, FakeTranscriber

BASE = datetime(2018, 6, 29, 12, 0, tzinfo=timezone.utc)


def post(pid, text, secs=0, media=None):
    return ChannelPost(id=pid, date=BASE + timedelta(seconds=secs), text=text,
                       url=f"https://t.me/x/{pid}", media=media or [])


class TestMarkers(unittest.TestCase):
    def test_end_markers(self):
        for text in ["متن\n⬇️", "متن\n👇👇", "متن\nادامه دارد...", "متن\nادامه در پست بعد", "متن\n⬇️\n@chan\n#tag"]:
            self.assertTrue(ends_with_marker(text), text)
        for text in ["متن عادی", "ادامه این بحث را خواهیم گفت و بسیار مفصل است", "⬇️ متن"]:
            self.assertFalse(ends_with_marker(text), text)

    def test_start_markers(self):
        for text in ["⬆️\nمتن", "👆 ادامه\nمتن", "ادامه\nمتن", "ادامه‌ی پست قبل\nمتن", "⬆️ متن"]:
            self.assertTrue(starts_with_marker(text), text)
        for text in ["ادامه این بحث در جلسه بعد", "متن\n⬆️"]:
            self.assertFalse(starts_with_marker(text), text)


class TestGrouping(unittest.TestCase):
    def test_merge_two_parts_and_gap(self):
        a, b = post(75, "💠 عنوان\nمتن یک\n⬇️"), post(76, "⬆️\nمتن دو\n#حدیث", secs=9)
        out = list(group_parts([a, b]))
        self.assertEqual(len(out), 1)
        m = out[0]
        self.assertEqual(m.id, 75)
        self.assertEqual(m.part_ids, [75, 76])
        self.assertEqual(m.text, "💠 عنوان\nمتن یک\n\nمتن دو\n#حدیث")
        far = post(76, "⬆️\nمتن دو", secs=3600)
        self.assertEqual(len(list(group_parts([a, far]))), 2)

    def test_chain_and_media(self):
        item = lambda: MediaItem(kind="audio", source_ref=object())
        a = post(1, "الف\n⬇️", media=[item()])
        b = post(2, "⬆️ ب\n⬇️", secs=5, media=[item()])
        c = post(3, "ج", secs=10)
        d = post(4, "مستقل", secs=20)
        out = list(group_parts([a, b, c, d]))
        self.assertEqual([p.part_ids for p in out], [[1, 2, 3], [4]])
        self.assertEqual(len(out[0].media), 2)
        self.assertEqual(out[0].text, "الف\n\nب\n\nج")


class TestPipelineMerge(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.posts = [post(75, "💠 منبع\nمتن یک\n⬇️"), post(76, "⬆️\nمتن دو", secs=9)]

    def run_archive(self, merge, posts=None, transcriber=None):
        src = FakeSource(posts or self.posts)
        ctx = StepContext(source=src, channel=None, out_dir=self.tmp, temp_dir=self.tmp / "t",
                          transcriber=transcriber)
        opts = ArchiveOptions(out_dir=self.tmp, merge_parts=merge, steps=["media", "transcribe"])
        return ChannelArchiver(src, ctx, opts).run("@testchan")

    def test_merged_note_and_rerun(self):
        s = self.run_archive(True)
        self.assertEqual(s.done, 1)
        notes = list((self.tmp / "posts").glob("*.md"))
        self.assertEqual(len(notes), 1)
        text = notes[0].read_text(encoding="utf-8")
        self.assertIn("متن یک", text)
        self.assertIn("متن دو", text)
        self.assertNotIn("⬇️", text)
        self.assertIn("post_ids: [75, 76]", text)
        self.assertEqual(self.run_archive(True).skipped, 1)

    def test_existing_separate_notes_are_merged(self):
        self.run_archive(False)
        self.assertEqual(len(list((self.tmp / "posts").glob("*.md"))), 2)
        self.run_archive(True)
        notes = list((self.tmp / "posts").glob("*.md"))
        self.assertEqual(len(notes), 1)
        self.assertTrue(notes[0].name.startswith("2018-06-29 - 75"))
        index = next(self.tmp.glob("*.md")).read_text(encoding="utf-8")
        self.assertEqual(index.count("[[posts/"), 1)

    def test_transcripts_reused(self):
        mk = lambda pid, text, secs: post(pid, text, secs, [MediaItem(kind="audio", duration=3, size=1, source_ref=object())])
        posts = [mk(75, "الف\n⬇️", 0), mk(76, "ب", 9)]
        t1 = FakeTranscriber()
        self.run_archive(False, posts, t1)
        t2 = FakeTranscriber()
        self.run_archive(True, posts, t2)
        self.assertEqual(t2.calls, [])
        text = next((self.tmp / "posts").glob("*.md")).read_text(encoding="utf-8")
        self.assertIn("transcript of", text)

    def test_without_flag_unchanged(self):
        self.run_archive(False)
        self.assertEqual(len(list((self.tmp / "posts").glob("*.md"))), 2)


if __name__ == "__main__":
    unittest.main()
