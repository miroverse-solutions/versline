import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from versline.commands import summarize as summarize_cmd
from versline.services.docexport import engine
from versline.services.export import questions_to_markdown


def fake_convert(pairs, fmt, opts):
    for md, out in pairs:
        Path(out).write_text(Path(md).read_text(encoding="utf-8"), encoding="utf-8")
    return [(out, None) for _md, out in pairs]


class SummarizeExportTests(unittest.TestCase):
    def run_cli(self, tmp, *extra):
        src = Path(tmp) / "a.md"
        src.write_text("متن", encoding="utf-8")
        summarizer = MagicMock()
        summarizer.process_file.return_value = "# خلاصه\n\nمتن خلاصه"
        with patch.object(summarize_cmd, "TextSummarizer", return_value=summarizer), \
                patch.object(summarize_cmd, "print_cost_report"), \
                patch.object(engine, "available", return_value=True), \
                patch.object(engine, "convert", side_effect=fake_convert):
            return CliRunner().invoke(summarize_cmd.app, [str(src), "--mode", "outline", *extra])

    def test_export_writes_docx_with_generated_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_cli(tmp, "--export", "docx")
            self.assertEqual(result.exit_code, 0, result.output)
            text = (Path(tmp) / "a_summary_outline.docx").read_text(encoding="utf-8")
            self.assertIn("| حالت | outline |", text)
            self.assertIn("متن خلاصه", text)
            self.assertFalse((Path(tmp) / "a_summary_outline.pdf").exists())

    def test_no_frontmatter_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_cli(tmp, "-X", "pdf", "--no-export-frontmatter")
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertNotIn("|", (Path(tmp) / "a_summary_outline.pdf").read_text(encoding="utf-8"))

    def test_without_flag_nothing_is_exported_or_imported(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_cli(tmp)
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(sorted(p.suffix for p in Path(tmp).iterdir()), [".md", ".md"])

    def test_missing_engine_exits_with_hint_but_keeps_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "a.md"
            src.write_text("متن", encoding="utf-8")
            summarizer = MagicMock()
            summarizer.process_file.return_value = "خلاصه"
            with patch.object(summarize_cmd, "TextSummarizer", return_value=summarizer), \
                    patch.object(summarize_cmd, "print_cost_report"), \
                    patch.object(engine, "available", return_value=False):
                result = CliRunner().invoke(summarize_cmd.app, [str(src), "--mode", "outline", "--export", "pdf"])
            self.assertEqual(result.exit_code, 1)
            self.assertTrue((Path(tmp) / "a_summary_outline.md").is_file())


class QuestionSheetTests(unittest.TestCase):
    def test_mcq_sheet_has_options_and_answer_key(self):
        md = questions_to_markdown([
            {"question": "س؟", "option_a": "۱", "option_b": "۲", "option_c": "۳", "option_d": "۴",
             "correct_answer": "b", "explanation": "چون"},
            {"question": "باز؟", "answer": "پاسخ"},
        ])
        self.assertIn("- ب) ۲", md)
        self.assertIn("## پاسخنامه", md)
        self.assertIn("**1.** ب — چون", md)
        self.assertIn("**2.** پاسخ", md)
        self.assertIn('<div class="page-break"></div>', md)


if __name__ == "__main__":
    unittest.main()
