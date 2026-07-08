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
    @patch("versline.services.research_writing.load_prompt")
    def test_outline_generation_openrouter_uses_openrouter_client(
        self, mock_load_prompt, mock_ai, mock_settings
    ):
        mock_settings.llm.provider = "openrouter"
        mock_settings.llm.model = "openrouter/auto"
        mock_settings.llm.api_key = "fake"
        mock_settings.llm.api_endpoint = None
        mock_settings.llm.proxy = None

        prompt_map = {
            "research_findings_colaizzi_outline_prompt.md": "OUTLINE::{research_context_json}::{language_instruction}",
            "research_findings_colaizzi_full_prompt.md": "FULL::{research_context_json}::{approved_outline}::{language_instruction}",
            "research_findings_revision_prompt.md": "REVISION::{revision_instructions}",
        }
        mock_load_prompt.side_effect = lambda filename: prompt_map[filename]

        completion = MagicMock()
        completion.usage = MagicMock(prompt_tokens=8, completion_tokens=9)
        completion.choices = [MagicMock(message=MagicMock(content="# OR Outline"))]

        client = MagicMock()
        client.chat.completions.create.return_value = completion
        mock_ai.configure_openrouter.return_value = client

        service = ResearchWritingService(section="findings", method="thematic-colaizzi")
        result = service.generate_outline({"study": {"type": "qualitative"}})

        self.assertIn("OR Outline", result)
        mock_ai.configure_openrouter.assert_called_once_with(mock_settings.llm)
        mock_ai.configure_openai.assert_not_called()

    @patch("versline.services.research_writing.settings")
    @patch("versline.services.research_writing.ai")
    @patch("versline.services.research_writing.load_prompt")
    def test_outline_generation_openai(self, mock_load_prompt, mock_ai, mock_settings):
        mock_settings.llm.provider = "openai"
        mock_settings.llm.model = "gpt-4o-mini"
        mock_settings.llm.api_key = "fake"
        mock_settings.llm.api_endpoint = None
        mock_settings.llm.proxy = None

        prompt_map = {
            "research_findings_colaizzi_outline_prompt.md": "OUTLINE::{research_context_json}::{language_instruction}",
            "research_findings_colaizzi_full_prompt.md": "FULL::{research_context_json}::{approved_outline}::{language_instruction}",
            "research_findings_revision_prompt.md": "REVISION::{revision_instructions}",
        }
        mock_load_prompt.side_effect = lambda filename: prompt_map[filename]

        completion = MagicMock()
        completion.usage = MagicMock(prompt_tokens=10, completion_tokens=20)
        completion.choices = [MagicMock(message=MagicMock(content="# Chapter 4 Outline"))]

        client = MagicMock()
        client.chat.completions.create.return_value = completion
        mock_ai.configure_openai.return_value = client

        service = ResearchWritingService(
            section="findings",
            method="thematic-colaizzi",
            revision_note="Keep the demographics section blank for now.",
        )
        result = service.generate_outline(
            {
                "study": {"type": "qualitative", "method": "colaizzi"},
                "materials": {"themes": [{"name": "Motivation"}]},
            }
        )

        self.assertIn("Chapter 4 Outline", result)
        self.assertEqual(service.tracker.total_input_tokens, 10)
        self.assertEqual(service.tracker.total_output_tokens, 20)
        prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("OUTLINE::", prompt)
        self.assertIn("REVISION::", prompt)

    @patch("versline.services.research_writing.settings")
    @patch("versline.services.research_writing.ai")
    @patch("versline.services.research_writing.load_prompt")
    def test_full_generation_includes_revision_brief(self, mock_load_prompt, mock_ai, mock_settings):
        mock_settings.llm.provider = "openai"
        mock_settings.llm.model = "gpt-4o-mini"
        mock_settings.llm.api_key = "fake"
        mock_settings.llm.api_endpoint = None
        mock_settings.llm.proxy = None

        prompt_map = {
            "research_findings_colaizzi_outline_prompt.md": "OUTLINE::{research_context_json}::{language_instruction}",
            "research_findings_colaizzi_full_prompt.md": "FULL::{research_context_json}::{approved_outline}::{language_instruction}",
            "research_findings_revision_prompt.md": "REVISION::{revision_instructions}",
        }
        mock_load_prompt.side_effect = lambda filename: prompt_map[filename]

        completion = MagicMock()
        completion.usage = MagicMock(prompt_tokens=12, completion_tokens=18)
        completion.choices = [MagicMock(message=MagicMock(content="# Full Chapter"))]

        client = MagicMock()
        client.chat.completions.create.return_value = completion
        mock_ai.configure_openai.return_value = client

        service = ResearchWritingService(
            section="findings",
            method="thematic-colaizzi",
            revision_note="Use direct quotes and split the themes table by theme.",
        )
        result = service.generate_full_text(
            research_inputs={"materials": {"themes_table": "x"}},
            approved_outline="# Approved outline",
        )

        self.assertIn("Full Chapter", result)
        prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("REVISION::Use direct quotes", prompt)
        self.assertIn("FULL::", prompt)

    @patch("versline.services.research_writing.settings")
    @patch("versline.services.research_writing.ai")
    @patch("versline.services.research_writing.load_prompt")
    def test_full_generation_includes_all_revision_history(self, mock_load_prompt, mock_ai, mock_settings):
        mock_settings.llm.provider = "openai"
        mock_settings.llm.model = "gpt-4o-mini"
        mock_settings.llm.api_key = "fake"
        mock_settings.llm.api_endpoint = None
        mock_settings.llm.proxy = None

        prompt_map = {
            "research_findings_colaizzi_outline_prompt.md": "OUTLINE::{research_context_json}::{language_instruction}",
            "research_findings_colaizzi_full_prompt.md": "FULL::{research_context_json}::{approved_outline}::{language_instruction}",
            "research_findings_revision_prompt.md": "REVISION::{revision_instructions}",
        }
        mock_load_prompt.side_effect = lambda filename: prompt_map[filename]

        completion = MagicMock()
        completion.usage = MagicMock(prompt_tokens=12, completion_tokens=18)
        completion.choices = [MagicMock(message=MagicMock(content="# Full Chapter"))]

        client = MagicMock()
        client.chat.completions.create.return_value = completion
        mock_ai.configure_openai.return_value = client

        service = ResearchWritingService(
            section="findings",
            method="thematic-colaizzi",
            revision_notes=[
                "Keep demographics pending.",
                "Use direct quotes for each sub-theme.",
            ],
        )
        service.generate_full_text(
            research_inputs={"materials": {"themes_table": "x"}},
            approved_outline="# Approved outline",
        )

        prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("[Revision 1]", prompt)
        self.assertIn("Keep demographics pending.", prompt)
        self.assertIn("[Revision 2]", prompt)
        self.assertIn("Use direct quotes for each sub-theme.", prompt)

    def test_full_generation_requires_approved_outline(self):
        service = ResearchWritingService(section="findings", method="colaizzi")
        with self.assertRaises(ValueError):
            service.generate_full_text(research_inputs={"materials": {}}, approved_outline="")


if __name__ == "__main__":
    unittest.main()
