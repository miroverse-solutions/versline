import unittest

from versline.services.channel_archive.obsidian import render_frontmatter
from versline.services.docexport import metadata_table, split_front_matter


class FrontMatterTests(unittest.TestCase):
    def test_roundtrip_with_render_frontmatter(self):
        data = {"title": "پست «تست» با \"نقل\"", "post_id": 12, "transcribed": True, "tags": ["telegram", "فقه"],
                "aliases": [], "date": "2026-01-02T10:00:00+03:30"}
        text = render_frontmatter(data) + "\n\n# متن\n"
        meta, body = split_front_matter(text)
        self.assertEqual(meta["title"], data["title"])
        self.assertEqual(meta["post_id"], 12)
        self.assertIs(meta["transcribed"], True)
        self.assertEqual(meta["tags"], ["telegram", "فقه"])
        self.assertEqual(meta["aliases"], [])
        self.assertEqual(body.strip(), "# متن")

    def test_no_front_matter_is_untouched(self):
        text = "---\nجدا کننده\n---\nمتن"
        self.assertEqual(split_front_matter(text), ({}, text))
        self.assertEqual(split_front_matter("# سلام"), ({}, "# سلام"))

    def test_table_labels_and_hidden_keys(self):
        table = metadata_table({"title": "ع", "duration": 3725, "tags": ["telegram"], "aliases": ["x"],
                                "url": "https://t.me/a/1", "transcribed": False})
        self.assertIn("| عنوان | ع |", table)
        self.assertIn("| مدت | 01:02:05 |", table)
        self.assertIn("[https://t.me/a/1](https://t.me/a/1)", table)
        self.assertIn("| پیاده‌سازی شده | خیر |", table)
        self.assertNotIn("aliases", table)
        self.assertNotIn("telegram", table.replace("t.me", ""))

    def test_empty_metadata_gives_no_table(self):
        self.assertEqual(metadata_table({"aliases": ["x"], "title": None}), "")


if __name__ == "__main__":
    unittest.main()
