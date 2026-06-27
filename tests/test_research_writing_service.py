import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from versline.services.research_writing import (
    ResearchWritingService,
    load_research_input,
)


class TestResearchInputLoading(unittest.TestCase):
    def test_load_json_object(self):
        payload = {"study": {"title": "Test"}, "materials": {"themes": []}}
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", encoding="utf-8", delete=False) as f:
            f.write(json.dumps(payload, ensure_ascii=False))
            path = f.name

        try:
            data = load_research_input(path)
            self.assertEqual(data["study"]["title"], "Test")
        finally:
            Path(path).unlink(missing_ok=True)

    def test_non_json_input_rejected(self):
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", encoding="utf-8", delete=False) as f:
            f.write("# not json")
            path = f.name

        try:
            with self.assertRaises(ValueError):
                load_research_input(path)
        finally:
            Path(path).unlink(missing_ok=True)


class TestResearchWritingService(unittest.TestCase):
    def test_unsupported_section_method_raises(self):
        with self.assertRaises(ValueError):
            ResearchWritingService(section="discussion", method="thematic-colaizzi")

    @patch("versline.services.research_writing.settings")
    @patch("versline.services.research_writing.ai")
    def test_outline_generation_openai(self, mock_ai, mock_settings):
        mock_settings.llm.provider = "openai"
        mock_settings.llm.model = "gpt-4o-mini"
        mock_settings.llm.api_key = "fake"
        mock_settings.llm.api_endpoint = None
        mock_settings.llm.proxy = None

        completion = MagicMock()
        completion.usage = MagicMock(prompt_tokens=10, completion_tokens=20)
        completion.choices = [MagicMock(message=MagicMock(content="# Chapter 4 Outline"))]

        client = MagicMock()
        client.chat.completions.create.return_value = completion
        mock_ai.configure_openai.return_value = client

        service = ResearchWritingService(section="findings", method="thematic-colaizzi")
        result = service.generate_outline(
            {
                "study": {"type": "qualitative", "method": "colaizzi"},
                "materials": {"themes": [{"name": "Motivation"}]},
            }
        )

        self.assertIn("Chapter 4 Outline", result)
        self.assertEqual(service.tracker.total_input_tokens, 10)
        self.assertEqual(service.tracker.total_output_tokens, 20)

    def test_full_generation_requires_approved_outline(self):
        service = ResearchWritingService(section="findings", method="colaizzi")
        with self.assertRaises(ValueError):
            service.generate_full_text(research_inputs={"materials": {}}, approved_outline="")


if __name__ == "__main__":
    unittest.main()
