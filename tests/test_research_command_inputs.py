import unittest
from pathlib import Path
from unittest.mock import patch
import tempfile

from versline.commands.research import _collect_coded_segments, _enrich_inputs


class TestResearchCommandInputEnrichment(unittest.TestCase):
    def test_enrich_inputs_includes_writing_guide_and_sample_output(self):
        base_input = {"study": {"title": "X"}}

        values = {
            "guide.md": "guide-content",
            "sample.docx": "sample-output-content",
            "themes.xlsx": "themes-table-content",
        }

        with patch("versline.commands.research._read_material_file") as mocked_reader:
            mocked_reader.side_effect = lambda p: values[p.name]
            result = _enrich_inputs(
                base_input=base_input,
                demographics_file=None,
                themes_table_file=Path("themes.xlsx"),
                central_concepts_file=None,
                coded_segments=[],
                writing_guide_file=Path("guide.md"),
                sample_output_file=Path("sample.docx"),
                interviews=[],
            )

        self.assertIn("materials", result)
        self.assertIsInstance(result["materials"], dict)
        self.assertEqual(result["materials"]["themes_table"], "themes-table-content")
        self.assertEqual(result["materials"]["writing_guide"], "guide-content")
        self.assertEqual(result["materials"]["sample_output"], "sample-output-content")

    def test_collect_coded_segments_from_files_and_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            f1 = tmp_path / "analysis1.docx"
            f1.write_text("x", encoding="utf-8")
            f2 = tmp_path / "analysis2.md"
            f2.write_text("y", encoding="utf-8")

            with patch("versline.commands.research._read_material_file") as mocked_reader:
                mocked_reader.side_effect = lambda p: f"content:{p.name}"
                result = _collect_coded_segments(
                    coded_segments_dir=tmp_path,
                    coded_segment_files=[f1],
                )

            names = {item["name"] for item in result}
            self.assertIn("analysis1.docx", names)
            self.assertIn("analysis2.md", names)


if __name__ == "__main__":
    unittest.main()
