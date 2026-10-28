import unittest
from datetime import datetime, timezone

from versline.services.channel_archive import obsidian
from versline.services.channel_archive.models import ChannelInfo, ChannelPost, PostRecord


def _post(text, pid=7):
    return ChannelPost(id=pid, date=datetime(2026, 3, 14, 9, 12, tzinfo=timezone.utc), text=text)


class TestObsidian(unittest.TestCase):
    def test_frontmatter_escapes_quotes_newlines_and_keeps_persian(self):
        out = obsidian.render_frontmatter({"title": 'او گفت: "سلام"\nخط دوم', "n": 3, "ok": True, "skip": None, "tags": ["a", "ب"]})
        self.assertIn('title: "او گفت: \\"سلام\\"\\nخط دوم"', out)
        self.assertIn("n: 3", out)
        self.assertIn("ok: true", out)
        self.assertNotIn("skip", out)
        self.assertIn('tags: ["a", "ب"]', out)

    def test_title_skips_hashtags_urls_and_falls_back(self):
        self.assertEqual(obsidian.make_title(_post("#فقه\n\nدرس اول: طهارت https://t.me/x\nمتن")), "درس اول: طهارت")
        self.assertEqual(obsidian.make_title(_post("")), "پست 7")
        long = obsidian.make_title(_post("کلمه " * 50))
        self.assertLessEqual(len(long), 82)

    def test_hashtags(self):
        self.assertEqual(obsidian.extract_hashtags("متن #فقه_اسلامی و #فقه_اسلامی #123 #علم."), ["فقه_اسلامی", "علم"])

    def test_note_stem_has_no_link_breaking_chars(self):
        stem = obsidian.note_stem(_post("x"), "a [b] #c | d^e", tz=timezone.utc)
        self.assertTrue(stem.startswith("2026-03-14 - 7 - "))
        for ch in "[]#|^":
            self.assertNotIn(ch, stem)

    def test_parse_date_gregorian_shamsi_and_end_of_day(self):
        start = obsidian.parse_date_arg("2026-03-14")
        end = obsidian.parse_date_arg("2026-03-14", end=True)
        self.assertEqual((end - start).days, 0)
        self.assertGreater(end, start)
        shamsi = obsidian.parse_date_arg("۱۴۰۴/۰۱/۰۱")
        self.assertEqual(shamsi.date().isoformat(), "2025-03-21")
        with self.assertRaises(ValueError):
            obsidian.parse_date_arg("14 March")

    def test_to_shamsi(self):
        self.assertEqual(obsidian.to_shamsi(datetime(2025, 3, 21)), "1404-01-01")

    def test_render_note_and_index(self):
        rec = PostRecord(post=ChannelPost(id=1, date=datetime(2026, 1, 1, tzinfo=timezone.utc), url="https://t.me/x/1"))
        rec.frontmatter["title"] = "T"
        rec.sections["caption"] = "hello"
        rec.sections["transcript"] = "متن"
        rec.attachments.append("attachments/x_1.mp3")
        note = obsidian.render_note(rec, "T")
        self.assertIn("## توضیحات", note)
        self.assertIn("## متن پیاده‌شده", note)
        self.assertIn("![[attachments/x_1.mp3]]", note)
        self.assertIn("(https://t.me/x/1)", note)
        idx = obsidian.render_index(
            ChannelInfo(ref="@x", title="X", username="x"),
            [{"status": "done", "note": "posts/a.md", "title": "a|b", "date": "2026-01-01T00:00:00+00:00", "media_type": "audio", "duration": 65}],
            "2026-01-01", "2026-01-01",
        )
        self.assertIn("[[posts/a\\|a\\|b]]", idx)
        self.assertIn("00:01:05", idx)
        self.assertIn("post_count: 1", idx)


if __name__ == "__main__":
    unittest.main()
