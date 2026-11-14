import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from versline.services.docexport import (
    ExportError, ExportItem, ExportOptions, build_markdown, export_items, parse_formats,
)
from versline.services.docexport import engine


NOTE = '---\ntitle: "پست"\nsource: "telegram"\n---\n\n# پست\n\nمتن\n'


def fake_convert(pairs, fmt, opts):
    for md, out in pairs:
        Path(out).write_text(Path(md).read_text(encoding="utf-8"), encoding="utf-8")
    return [(out, None) for _md, out in pairs]


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.src = self.dir / "n.md"
        self.src.write_text(NOTE, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_formats(self):
        self.assertEqual(parse_formats("docx,pdf"), ("docx", "pdf"))
        self.assertEqual(parse_formats("word"), ("docx",))
        self.assertEqual(parse_formats("all"), ("docx", "pdf"))
        self.assertEqual(parse_formats("pdf docx pdf"), ("pdf", "docx"))
        self.assertEqual(parse_formats(None), ())
        with self.assertRaises(ValueError):
            parse_formats("odt")

    def test_table_follows_title_when_front_matter_on(self):
        md = build_markdown(ExportItem(out_base=self.dir / "n", source=self.src, metadata={"model": "m", "title": "ignored"}), True, False)
        self.assertTrue(md.startswith("# پست\n\n| مشخصه"))
        self.assertIn("| مدل | m |", md)
        self.assertIn("| عنوان | پست |", md)  # the document's own front matter wins over generated metadata
        self.assertNotIn("source:", md)

    def test_no_table_when_front_matter_off(self):
        md = build_markdown(ExportItem(out_base=self.dir / "n", source=self.src), False, False)
        self.assertNotIn("|", md)
        self.assertNotIn("---", md)

    def test_title_created_when_document_has_none(self):
        item = ExportItem(out_base=self.dir / "x", text="متن ساده", metadata={"model": "m"}, title="سند")
        self.assertTrue(build_markdown(item, True, False).startswith("# سند\n\n| مشخصه"))
        self.assertEqual(build_markdown(item, False, False), "متن ساده")

    def test_export_skips_up_to_date_and_force_redoes(self):
        item = ExportItem(out_base=self.dir / "n", source=self.src)
        opts = ExportOptions(formats=("docx",))
        with patch.object(engine, "available", return_value=True), patch.object(engine, "convert", side_effect=fake_convert) as conv:
            first = export_items([item], opts)
            self.assertTrue(first[0].ok and not first[0].skipped)
            self.assertTrue((self.dir / "n.docx").is_file())
            second = export_items([item], opts)
            self.assertTrue(second[0].skipped)
            self.assertEqual(conv.call_count, 2)  # second call had no pairs
            self.assertEqual(conv.call_args[0][0], [])
            opts.force = True
            third = export_items([item], opts)
            self.assertFalse(third[0].skipped)

    def test_missing_engine_raises_install_hint(self):
        with patch.object(engine, "available", return_value=False):
            with self.assertRaises(ExportError) as ctx:
                export_items([ExportItem(out_base=self.dir / "n", source=self.src)], ExportOptions(formats=("pdf",)))
        self.assertIn("versline[export]", str(ctx.exception))

    def test_failed_conversion_reported(self):
        def failing(pairs, fmt, opts):
            return [(out, "boom") for _m, out in pairs]

        with patch.object(engine, "available", return_value=True), patch.object(engine, "convert", side_effect=failing):
            res = export_items([ExportItem(out_base=self.dir / "n", source=self.src)], ExportOptions(formats=("pdf",)))
        self.assertFalse(res[0].ok)
        self.assertEqual(res[0].error, "boom")


@unittest.skipUnless(engine.available(), "mdpersia not installed")
class RealDocxTests(unittest.TestCase):
    def test_docx_contains_text_and_metadata_table(self):
        import docx

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "n.md"
            src.write_text(NOTE + "\n[[a|پیوند]]\n", encoding="utf-8")
            res = export_items([ExportItem(out_base=Path(tmp) / "n", source=src)], ExportOptions(formats=("docx",)))
            self.assertTrue(res[0].ok, res[0].error)
            document = docx.Document(str(Path(tmp) / "n.docx"))
            texts = [p.text for p in document.paragraphs]
            self.assertIn("متن", texts)
            self.assertIn("پیوند", texts)
            self.assertEqual(document.tables[0].rows[1].cells[0].text, "عنوان")

            res = export_items([ExportItem(out_base=Path(tmp) / "m", source=src)], ExportOptions(formats=("docx",), front_matter=False))
            self.assertEqual(len(docx.Document(str(Path(tmp) / "m.docx")).tables), 0)


if __name__ == "__main__":
    unittest.main()
