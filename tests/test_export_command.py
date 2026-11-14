import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from versline.commands import export as export_cmd
from versline.services.docexport import engine


def fake_convert(pairs, fmt, opts):
    for md, out in pairs:
        Path(out).write_text("x", encoding="utf-8")
    return [(out, None) for _md, out in pairs]


class ExportCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "in" / "sub").mkdir(parents=True)
        (self.dir / "in" / "a.md").write_text("# a", encoding="utf-8")
        (self.dir / "in" / "sub" / "b.md").write_text("# b", encoding="utf-8")
        self.runner = CliRunner()
        patches = [patch.object(engine, "available", return_value=True), patch.object(engine, "convert", side_effect=fake_convert)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return self.runner.invoke(export_cmd.app, [str(a) for a in args])

    def test_file_exports_next_to_source(self):
        result = self.run_cli(self.dir / "in" / "a.md", "--to", "docx")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue((self.dir / "in" / "a.docx").is_file())
        self.assertFalse((self.dir / "in" / "a.pdf").exists())

    def test_folder_with_output_mirrors_tree(self):
        result = self.run_cli(self.dir / "in", "-r", "-o", self.dir / "out", "--to", "all")
        self.assertEqual(result.exit_code, 0, result.output)
        for rel in ("a.docx", "a.pdf", "sub/b.docx", "sub/b.pdf"):
            self.assertTrue((self.dir / "out" / rel).is_file(), rel)

    def test_bad_format_rejected(self):
        result = self.run_cli(self.dir / "in" / "a.md", "--to", "odt")
        self.assertNotEqual(result.exit_code, 0)

    def test_no_inputs_shows_help(self):
        self.assertEqual(self.run_cli().exit_code, 1)


if __name__ == "__main__":
    unittest.main()
