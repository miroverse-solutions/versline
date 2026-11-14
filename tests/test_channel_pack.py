import csv
import json
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from versline.commands import telegram as telegram_cmd
from versline.services.channel_archive import pack
from versline.services.docexport import engine


def fake_convert(pairs, fmt, opts):
    for md, out in pairs:
        Path(out).write_text(Path(md).read_text(encoding="utf-8"), encoding="utf-8")
    return [(out, None) for _md, out in pairs]


def make_note(post_id, title, date, body, attachments=()):
    embeds = "".join(f"![[{a}]]\n" for a in attachments)
    return (
        f'---\ntitle: "{title}"\nsource: "telegram"\npost_id: {post_id}\ndate: "{date}"\n'
        f'date_shamsi: "x"\nmedia_type: "audio"\nduration: 60\nviews: 5\nurl: "https://t.me/ch/{post_id}"\n'
        f'tags: ["telegram"]\naliases: []\n---\n\n# {title}\n\n## توضیحات\n\n{body}\n\n'
        + (f"## پیوست‌ها\n\n{embeds}\n" if attachments else "")
    )


def make_archive(root: Path):
    (root / "posts").mkdir(parents=True)
    (root / "attachments").mkdir()
    (root / "attachments" / "ch_1.mp3").write_bytes(b"audio")
    specs = [
        (1, "پست اول", "2026-03-21T10:00:00+03:30", ["attachments/ch_1.mp3"]),
        (2, "پست دوم", "2026-05-01T10:00:00+03:30", []),
        (3, "پست سوم", "2026-05-02T10:00:00+03:30", []),
    ]
    posts = {}
    for pid, title, date, atts in specs:
        rel = f"posts/{date[:10]} - {pid} - {title}.md"
        (root / rel).write_text(make_note(pid, title, date, f"متن {title}", atts), encoding="utf-8")
        posts[str(pid)] = {"status": "done", "note": rel, "title": title, "media_type": "audio", "date": date, "duration": 60}
    posts["4"] = {"status": "done", "merged_into": 3, "note": posts["3"]["note"], "title": "x", "date": "2026-05-02T10:05:00+03:30"}
    posts["5"] = {"status": "failed", "error": "e", "date": "2026-05-03T10:00:00+03:30"}
    (root / ".versline-channel.json").write_text(
        json.dumps({"channel": {"title": "کانال تست", "username": "ch", "id": 1}, "posts": posts}, ensure_ascii=False),
        encoding="utf-8",
    )


class PackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.archive = self.dir / "archive"
        make_archive(self.archive)
        for p in (patch.object(engine, "available", return_value=True), patch.object(engine, "convert", side_effect=fake_convert)):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, **kw):
        opts = pack.PackOptions(out_dir=self.dir / "out", **kw)
        return pack.build_pack(self.archive, opts)

    def test_collect_skips_merged_failed_and_filters_dates(self):
        _, posts = pack.collect_posts(self.archive)
        self.assertEqual([p.entry["title"] for p in posts], ["پست اول", "پست دوم", "پست سوم"])
        since = datetime.fromisoformat("2026-04-01T00:00:00+03:30")
        _, posts = pack.collect_posts(self.archive, since=since)
        self.assertEqual(len(posts), 2)

    def test_layout_catalog_and_zip(self):
        result = self.build()
        root = result.root
        self.assertEqual(result.posts, 3)
        self.assertEqual(root.name, "ch_2026-03-21_2026-05-02")
        for rel in ("README.md", "README.pdf", "کانال تست.docx", "کانال تست.pdf", "catalog.csv", "catalog.xlsx",
                    "notes/کانال تست.md", "notes/attachments/ch_1.mp3"):
            self.assertTrue((root / rel).is_file(), rel)
        self.assertEqual(len(list((root / "posts" / "docx").glob("*.docx"))), 3)
        self.assertEqual(len(list((root / "posts" / "pdf").glob("*.pdf"))), 3)
        with open(root / "catalog.csv", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(len(rows), 4)  # header + 3 posts (merged part and failed post excluded)
        self.assertIn("posts/docx/2026-03-21 - 1 - پست اول.docx", rows[1])
        self.assertIn("attachments/ch_1.mp3", rows[1])
        with zipfile.ZipFile(result.zip_path) as zf:
            names = zf.namelist()
        self.assertIn(f"{root.name}/catalog.csv", names)
        self.assertEqual(result.failures, [])

    def test_book_markdown_structure(self):
        info, posts = pack.collect_posts(self.archive)
        md = pack.build_book_markdown(info, posts, front_matter=True)
        self.assertTrue(md.startswith("# کانال تست"))
        self.assertEqual(md.count('<div class="page-break"></div>'), 1 + 2 + 1)  # after cover, before 2 months, between posts of a month
        self.assertIn("## فهرست مطالب", md)
        self.assertIn("### پست اول", md)
        self.assertIn("#### توضیحات", md)  # note headings demoted two levels
        self.assertNotIn("\n# پست اول", md)
        self.assertIn("| مدت | 00:01:00 |", md)
        self.assertNotIn("| مشخصه", pack.build_book_markdown(info, posts, front_matter=False))

    def test_toc_links_point_at_real_heading_ids(self):
        # a duplicate title gets a "-1" id suffix; the TOC must link to it, not to the first one
        info, posts = pack.collect_posts(self.archive)
        posts[2].entry["title"] = posts[1].entry["title"]
        md = pack.build_book_markdown(info, posts, front_matter=False)
        toc = md.split("## فهرست مطالب")[1].split("**", 0)[0].split('<div class="page-break">')[0]
        self.assertIn("[پست دوم](#پست-دوم)", toc)
        self.assertIn("[پست دوم](#پست-دوم-1)", toc)
        self.assertRegex(toc, r"\*\*\[[^\]]+\]\(#[^)]+\)\*\*")  # month entries are links too

    def test_toc_off(self):
        info, posts = pack.collect_posts(self.archive)
        md = pack.build_book_markdown(info, posts, front_matter=False, toc=False)
        self.assertNotIn("فهرست مطالب", md)
        self.assertNotIn("@@TOC@@", md)

    def test_options_media_zip_per_post_off(self):
        result = self.build(media=False, make_zip=False, per_post=False)
        self.assertIsNone(result.zip_path)
        self.assertFalse((result.root / "posts").exists())
        self.assertFalse((result.root / "notes" / "attachments").exists())

    def test_per_post_resume_skips_up_to_date(self):
        self.build()
        with patch.object(engine, "convert", side_effect=fake_convert) as conv:
            self.build()
        per_post_pairs = [c for c in conv.call_args_list if c.args[0]]
        # only the book (and README) are rebuilt; per-post files are up to date
        self.assertTrue(all(len(c.args[0]) <= 2 for c in per_post_pairs))

    def test_missing_archive(self):
        with self.assertRaises(FileNotFoundError):
            pack.collect_posts(self.dir)

    def test_cli_pack(self):
        result = CliRunner().invoke(
            telegram_cmd.app,
            ["pack", str(self.archive), "-o", str(self.dir / "cli"), "--to", "docx", "--no-zip", "--since", "1405-02-01"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        root = next((self.dir / "cli").iterdir())
        self.assertEqual(len(list((root / "posts" / "docx").glob("*.docx"))), 2)
        self.assertFalse((root / "posts" / "pdf").exists())


if __name__ == "__main__":
    unittest.main()
