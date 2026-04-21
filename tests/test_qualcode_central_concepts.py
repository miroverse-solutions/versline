import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from versline.services.qualitative_coding import QualitativeCoder


class TestQualcodeCentralConcepts(unittest.TestCase):
    def test_parse_central_concepts_markdown(self):
        coder = QualitativeCoder(output_formats=["json"], export_excel=False)
        parsed = coder._parse_central_concepts_markdown(
            """
# مفاهیم مرکزی

## انگیزه ها
### پیشگیری و اصلاح
#### ۱ و ۲

### نوع دوستی
#### ۳
""".strip()
        )

        self.assertEqual(parsed["title"], "مفاهیم مرکزی")
        self.assertEqual(len(parsed["sections"]), 1)
        self.assertEqual(parsed["sections"][0]["section"], "انگیزه ها")
        self.assertEqual(parsed["sections"][0]["concepts"][0]["concept"], "پیشگیری و اصلاح")
        self.assertEqual(parsed["sections"][0]["concepts"][0]["evidence_refs"], "۱ و ۲")

    def test_process_file_writes_updated_central_concepts_output(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "interview.md"
            central_path = tmp_path / "central.md"
            output_dir = tmp_path / "out"

            input_path.write_text(
                "# مصاحبه\n\nاین یک متن کوتاه برای تحلیل کیفی است.",
                encoding="utf-8",
            )
            central_path.write_text(
                """
# مفاهیم مرکزی

## انگیزه ها
### پیشگیری و اصلاح
#### ۱
""".strip(),
                encoding="utf-8",
            )

            coder = QualitativeCoder(
                output_dir=str(output_dir),
                methods=["thematic"],
                output_formats=["json"],
                export_excel=False,
                words_per_batch=5000,
                force=True,
                central_concepts_path=str(central_path),
            )

            analysis_response = {
                "method": "thematic",
                "codes": [
                    {
                        "code": "پیشگیری",
                        "description": "گرایش به پیشگیری",
                        "segment_ids": ["S1"],
                        "quotes": [],
                        "confidence": 0.9,
                    }
                ],
                "categories": [
                    {
                        "name": "انگیزه",
                        "description": "طبقه انگیزشی",
                        "code_names": ["پیشگیری"],
                    }
                ],
                "themes": [
                    {
                        "name": "جهت گیری حرفه ای",
                        "description": "تم حرفه ای",
                        "category_names": ["انگیزه"],
                    }
                ],
                "framework_matrix": [],
                "findings": ["یافته نمونه"],
                "memo": "یادداشت نمونه",
            }

            updated_central_response = {
                "title": "مفاهیم مرکزی",
                "sections": [
                    {
                        "section": "انگیزه ها",
                        "concepts": [
                            {
                                "concept": "پیشگیری و اصلاح",
                                "evidence_refs": "۱ و ۲",
                            },
                            {
                                "concept": "جهت گیری حرفه ای",
                                "evidence_refs": "۱",
                            },
                        ],
                    }
                ],
                "update_memo": "دو مفهوم با اتکا به شواهد حفظ و یک مفهوم جدید اضافه شد.",
            }

            with (
                patch.object(coder, "_request_llm", return_value=analysis_response),
                patch.object(coder, "_request_llm_json_object", return_value=updated_central_response),
            ):
                outputs = coder.process_file(str(input_path))

            self.assertIn("central-concepts", outputs)
            central_output = outputs["central-concepts"]
            self.assertTrue(central_output.exists())

            rendered = central_output.read_text(encoding="utf-8")
            self.assertIn("### جهت گیری حرفه ای", rendered)
            self.assertIn("#### ۱ و ۲", rendered)

            json_output = outputs["json"]
            data = json.loads(json_output.read_text(encoding="utf-8"))
            self.assertIn("central_concepts", data)
            self.assertEqual(data["central_concepts"]["updated"]["title"], "مفاهیم مرکزی")
            concepts = data["central_concepts"]["updated"]["sections"][0]["concepts"]
            self.assertEqual(concepts[1]["concept"], "جهت گیری حرفه ای")


if __name__ == "__main__":
    unittest.main()
