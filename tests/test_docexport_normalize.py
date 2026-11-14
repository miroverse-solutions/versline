import tempfile
import unittest
from pathlib import Path

from versline.services.docexport import prepare_markdown


class NormalizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / "attachments").mkdir()
        (self.base / "attachments" / "a.png").write_bytes(b"x")
        (self.base / "attachments" / "a b.mp3").write_bytes(b"x")

    def tearDown(self):
        self.tmp.cleanup()

    def test_image_embed_becomes_absolute_markdown_image(self):
        out = prepare_markdown("![[attachments/a.png]]", self.base)
        self.assertEqual(out, f"![](<{(self.base / 'attachments' / 'a.png').resolve().as_posix()}>)")

    def test_image_embed_as_uri_for_pdf(self):
        out = prepare_markdown("![[attachments/a.png]]", self.base, as_uri=True)
        self.assertTrue(out.startswith("![](</"))
        self.assertNotIn("file:", out)

    def test_non_image_and_missing_embeds_become_attachment_lines(self):
        out = prepare_markdown("![[attachments/a b.mp3]]\n![[attachments/none.png]]", self.base)
        self.assertEqual(out, "📎 a b.mp3\n📎 none.png")

    def test_wikilinks(self):
        text = "[[posts/x|عنوان]] [[posts/y\\|جدول]] [[posts/z]]"
        self.assertEqual(prepare_markdown(text, self.base), "عنوان جدول z")

    def test_callouts_uppercased(self):
        self.assertEqual(prepare_markdown("> [!note]+ T\n> body", self.base), "> [!NOTE] T\n> body")

    def test_relative_markdown_image_made_absolute_and_urls_kept(self):
        out = prepare_markdown("![x](attachments/a.png) ![y](https://e.com/i.png)", self.base)
        self.assertIn("<" + (self.base / "attachments" / "a.png").resolve().as_posix() + ">", out)
        self.assertIn("![y](https://e.com/i.png)", out)

    def test_code_fences_untouched(self):
        text = "```\n![[attachments/a.png]] [[x]]\n```"
        self.assertEqual(prepare_markdown(text, self.base), text)


if __name__ == "__main__":
    unittest.main()
