import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from versline.services.summarizer import (
    MODES,
    TextSummarizer,
    _AUTO_LANG,
    _split_at_pattern,
    _split_by_paragraphs,
    _subsplit_section,
)
import re


# ---------------------------------------------------------------------------
# Unit tests for chunking helpers
# ---------------------------------------------------------------------------

class TestSplitAtPattern(unittest.TestCase):
    def test_no_headings_returns_full_text(self):
        text = "Just a paragraph.\n\nAnother paragraph."
        result = _split_at_pattern(text, re.compile(r"^#{1,2}\s+.+", re.MULTILINE))
        self.assertEqual(result, [text])

    def test_splits_at_h1_boundaries(self):
        text = "Intro\n\n# Section A\ncontent A\n\n# Section B\ncontent B"
        result = _split_at_pattern(text, re.compile(r"^#{1,2}\s+.+", re.MULTILINE))
        self.assertEqual(len(result), 3)
        self.assertIn("Intro", result[0])
        self.assertIn("Section A", result[1])
        self.assertIn("Section B", result[2])

    def test_splits_at_h2_boundaries(self):
        text = "## Intro\n\n## Part 2"
        result = _split_at_pattern(text, re.compile(r"^#{1,2}\s+.+", re.MULTILINE))
        self.assertEqual(len(result), 2)


class TestSplitByParagraphs(unittest.TestCase):
    def test_small_text_is_single_chunk(self):
        text = "Para one.\n\nPara two."
        result = _split_by_paragraphs(text, max_chars=500)
        self.assertEqual(len(result), 1)

    def test_large_text_is_split(self):
        # 5 paragraphs × ~60 chars each = ~300 chars; use max_chars=100 to force splits
        text = "\n\n".join([f"Paragraph {i}: " + "x" * 50 for i in range(5)])
        result = _split_by_paragraphs(text, max_chars=100)
        self.assertGreater(len(result), 1)

    def test_context_header_prepended(self):
        text = "Para one.\n\nPara two.\n\nPara three."
        result = _split_by_paragraphs(text, max_chars=20, context_header="## Context\n")
        for chunk in result:
            self.assertTrue(chunk.startswith("## Context\n"))


class TestSubsplitSection(unittest.TestCase):
    def test_small_section_not_split(self):
        section = "## Heading\nSmall content."
        result = _subsplit_section(section, max_chars=1000)
        self.assertEqual(len(result), 1)

    def test_large_section_split_at_h3(self):
        section = (
            "## Big Section\n"
            "### Part A\n" + "word " * 200 + "\n"
            "### Part B\n" + "word " * 200 + "\n"
        )
        result = _subsplit_section(section, max_chars=500)
        self.assertGreater(len(result), 1)


class TestTextSummarizerInit(unittest.TestCase):
    def test_valid_modes_accepted(self):
        for mode in MODES:
            summarizer = TextSummarizer(mode=mode)
            self.assertEqual(summarizer.mode, mode)

    def test_invalid_mode_raises(self):
        with self.assertRaises(ValueError):
            TextSummarizer(mode="nonsense")


class TestSplitBySections(unittest.TestCase):
    def test_text_under_max_is_single_chunk(self):
        text = "# Title\n\nShort content."
        chunks = TextSummarizer.split_by_sections(text, max_chars=500)
        self.assertEqual(len(chunks), 1)

    def test_multiheading_text_chunked(self):
        parts = [f"## Section {i}\n" + "word " * 100 for i in range(4)]
        text = "\n\n".join(parts)
        chunks = TextSummarizer.split_by_sections(text, max_chars=300)
        self.assertGreaterEqual(len(chunks), 2)

    def test_empty_chunks_filtered(self):
        text = "## A\n\ncontent A\n\n## B\n\ncontent B"
        chunks = TextSummarizer.split_by_sections(text, max_chars=10000)
        for chunk in chunks:
            self.assertTrue(chunk.strip())

    def test_crlf_normalised(self):
        text = "## A\r\ncontent A\r\n\r\n## B\r\ncontent B"
        chunks = TextSummarizer.split_by_sections(text, max_chars=10000)
        self.assertGreaterEqual(len(chunks), 1)


# ---------------------------------------------------------------------------
# Integration-style tests with mocked LLM
# ---------------------------------------------------------------------------

class TestSummarizerProcessFile(unittest.TestCase):
    def _make_summarizer(self, mode="detailed"):
        summarizer = TextSummarizer(mode=mode)
        return summarizer

    @patch("versline.services.summarizer.settings")
    @patch("versline.services.summarizer.ai")
    def test_process_file_md_passthrough(self, mock_ai, mock_settings):
        """Markdown files should be read directly without conversion."""
        mock_settings.llm.provider = "openai"
        mock_settings.llm.model = "gpt-4o-mini"
        mock_settings.llm.api_key = "fake"
        mock_settings.llm.api_endpoint = None
        mock_settings.llm.proxy = None

        fake_completion = MagicMock()
        fake_completion.usage = MagicMock(prompt_tokens=10, completion_tokens=20)
        fake_completion.choices = [
            MagicMock(message=MagicMock(content="## Summary\n\nThis is a summary."))
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = fake_completion
        mock_ai.configure_openai.return_value = mock_client

        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write("# Test Document\n\nThis is test content for summarization.\n")
            tmp_path = f.name

        try:
            summarizer = self._make_summarizer(mode="detailed")
            result = summarizer.process_file(tmp_path)
            self.assertIn("Summary", result)
            mock_ai.configure_openai.assert_called()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @patch("versline.services.summarizer.settings")
    @patch("versline.services.summarizer.ai")
    def test_process_file_multi_chunk(self, mock_ai, mock_settings):
        """Documents with multiple sections should produce a joined result."""
        mock_settings.llm.provider = "openai"
        mock_settings.llm.model = "gpt-4o-mini"
        mock_settings.llm.api_key = "fake"
        mock_settings.llm.api_endpoint = None
        mock_settings.llm.proxy = None

        call_count = [0]

        def fake_create(**kwargs):
            call_count[0] += 1
            fake = MagicMock()
            fake.usage = MagicMock(prompt_tokens=5, completion_tokens=10)
            fake.choices = [
                MagicMock(
                    message=MagicMock(content=f"Chunk {call_count[0]} summary.")
                )
            ]
            return fake

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = fake_create
        mock_ai.configure_openai.return_value = mock_client

        # Build a multi-section document large enough to create several chunks
        sections = [f"## Section {i}\n" + "content " * 50 for i in range(3)]
        content = "\n\n".join(sections)

        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write(content)
            tmp_path = f.name

        try:
            summarizer = self._make_summarizer(mode="outline")
            result = summarizer.process_file(tmp_path)
            # All chunk summaries should appear in final joined output
            self.assertIn("Chunk 1 summary", result)
            self.assertGreaterEqual(call_count[0], 1)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_process_file_empty_raises(self):
        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write("   \n")
            tmp_path = f.name
        try:
            summarizer = self._make_summarizer()
            with self.assertRaises(ValueError, msg="Should raise on empty file"):
                summarizer.process_file(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @patch("versline.services.summarizer.settings")
    @patch("versline.services.summarizer.ai")
    def test_progress_callback_called(self, mock_ai, mock_settings):
        """Progress callback should be invoked during processing."""
        mock_settings.llm.provider = "openai"
        mock_settings.llm.model = "gpt-4o-mini"
        mock_settings.llm.api_key = "fake"
        mock_settings.llm.api_endpoint = None
        mock_settings.llm.proxy = None

        fake_completion = MagicMock()
        fake_completion.usage = MagicMock(prompt_tokens=5, completion_tokens=5)
        fake_completion.choices = [
            MagicMock(message=MagicMock(content="Done."))
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = fake_completion
        mock_ai.configure_openai.return_value = mock_client

        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write("# Doc\n\nSome content here.\n")
            tmp_path = f.name

        calls = []
        try:
            summarizer = self._make_summarizer(mode="slides")
            summarizer.process_file(
                tmp_path,
                progress_callback=lambda c, t, m: calls.append((c, t, m)),
            )
            self.assertGreater(len(calls), 0)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @patch("versline.services.summarizer.settings")
    @patch("versline.services.summarizer.ai")
    def test_non_md_file_converted(self, mock_ai, mock_settings):
        """Text files that are not markdown should still be processed."""
        mock_settings.llm.provider = "openai"
        mock_settings.llm.model = "gpt-4o-mini"
        mock_settings.llm.api_key = "fake"
        mock_settings.llm.api_endpoint = None
        mock_settings.llm.proxy = None

        fake_completion = MagicMock()
        fake_completion.usage = MagicMock(prompt_tokens=5, completion_tokens=5)
        fake_completion.choices = [
            MagicMock(message=MagicMock(content="Text summary."))
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = fake_completion
        mock_ai.configure_openai.return_value = mock_client

        with tempfile.NamedTemporaryFile(
            suffix=".txt", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write("Plain text content that should be summarized.\n")
            tmp_path = f.name

        try:
            summarizer = self._make_summarizer()
            result = summarizer.process_file(tmp_path)
            self.assertIn("summary", result.lower())
        finally:
            Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Tests for didactic mode
# ---------------------------------------------------------------------------

class TestDidacticMode(unittest.TestCase):
    def test_didactic_flag_stored(self):
        s = TextSummarizer(mode="detailed", didactic=True)
        self.assertTrue(s.didactic)

    def test_non_didactic_default(self):
        s = TextSummarizer(mode="detailed")
        self.assertFalse(s.didactic)

    def test_didactic_instruction_non_empty(self):
        s = TextSummarizer(mode="detailed", didactic=True)
        instr = s._didactic_instruction()
        self.assertIn("Reorder", instr)
        self.assertIn("prerequisite", instr)

    def test_non_didactic_instruction_neutral(self):
        s = TextSummarizer(mode="detailed", didactic=False)
        instr = s._didactic_instruction()
        self.assertIn("source document order", instr)
        self.assertNotIn("Reorder", instr)

    def test_chunk_prompt_includes_didactic_instruction(self):
        """summarize_chunk should always embed the didactic_instruction placeholder."""
        from unittest.mock import patch, MagicMock

        with patch("versline.services.summarizer.settings") as mock_s, \
             patch("versline.services.summarizer.ai") as mock_ai:
            mock_s.llm.provider = "openai"
            mock_s.llm.model = "gpt-4o-mini"
            mock_s.llm.api_key = "fake"
            mock_s.llm.api_endpoint = None
            mock_s.llm.proxy = None

            fake = MagicMock()
            fake.usage = MagicMock(prompt_tokens=5, completion_tokens=5)
            fake.choices = [MagicMock(message=MagicMock(content="ok"))]
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = fake
            mock_ai.configure_openai.return_value = mock_client

            s = TextSummarizer(mode="detailed", didactic=True)
            s.summarize_chunk("Some text.", "gpt-4o-mini")

            sent = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
            self.assertIn("Reorder", sent)

    @patch("versline.services.summarizer.settings")
    @patch("versline.services.summarizer.ai")
    def test_didactic_process_file_two_phases(self, mock_ai, mock_settings):
        """Didactic mode must call the LLM twice: analysis then generation."""
        mock_settings.llm.provider = "openai"
        mock_settings.llm.model = "gpt-4o-mini"
        mock_settings.llm.api_key = "fake"
        mock_settings.llm.api_endpoint = None
        mock_settings.llm.proxy = None

        call_count = [0]

        def fake_prefix_call(client, model, document_text, instruction, tracker,
                             is_avalai=False):
            call_count[0] += 1
            if call_count[0] == 1:
                return "Blueprint: teach A before B."
            return "## Pedagogically restructured output"

        mock_ai.call_openai_with_document_prefix.side_effect = fake_prefix_call
        mock_ai.configure_openai.return_value = MagicMock()

        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write("# Doc\n\n" + "content " * 50)
            tmp_path = f.name

        try:
            s = TextSummarizer(mode="detailed", didactic=True)
            result = s.process_file(tmp_path)
            self.assertEqual(call_count[0], 2, "Expected exactly 2 LLM calls for didactic mode")
            self.assertIn("restructured", result)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @patch("versline.services.summarizer.settings")
    @patch("versline.services.summarizer.ai")
    def test_didactic_progress_callback_two_steps(self, mock_ai, mock_settings):
        """Progress callback should report two phases in didactic mode."""
        mock_settings.llm.provider = "openai"
        mock_settings.llm.model = "gpt-4o-mini"
        mock_settings.llm.api_key = "fake"
        mock_settings.llm.api_endpoint = None
        mock_settings.llm.proxy = None

        mock_ai.call_openai_with_document_prefix.side_effect = [
            "Blueprint.", "Final output."
        ]
        mock_ai.configure_openai.return_value = MagicMock()

        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write("# Doc\n\ncontent here\n")
            tmp_path = f.name

        calls = []
        try:
            s = TextSummarizer(mode="outline", didactic=True)
            s.process_file(tmp_path, progress_callback=lambda c, t, m: calls.append(m))
            messages = " ".join(calls)
            self.assertIn("Phase 1", messages)
            self.assertIn("Phase 2", messages)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @patch("versline.services.summarizer.settings")
    @patch("versline.services.summarizer.ai")
    def test_didactic_gemini_uses_cache(self, mock_ai, mock_settings):
        """For Google provider, didactic mode should attempt to create a context cache."""
        mock_settings.llm.provider = "google"
        mock_settings.llm.model = "gemini-1.5-pro"
        mock_settings.llm.api_key = "fake"
        mock_settings.llm.api_endpoint = None
        mock_settings.llm.proxy = None

        # Phase 1: analysis via regular generate_content
        fake_response1 = MagicMock()
        fake_response1.usage_metadata = MagicMock(
            prompt_token_count=10, candidates_token_count=20
        )
        fake_response1.text = "Blueprint: A before B."

        # Phase 2: generation via cache
        mock_ai.create_gemini_context_cache.return_value = "cachedContent/abc123"
        mock_ai.call_gemini_with_cache.return_value = "## Restructured output"
        mock_ai.delete_gemini_context_cache.return_value = None

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = fake_response1
        mock_ai.configure_gemini.return_value = mock_client

        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write("# Doc\n\n" + "content " * 50)
            tmp_path = f.name

        try:
            s = TextSummarizer(mode="detailed", didactic=True)
            result = s.process_file(tmp_path)
            mock_ai.create_gemini_context_cache.assert_called_once()
            mock_ai.call_gemini_with_cache.assert_called_once()
            mock_ai.delete_gemini_context_cache.assert_called_once_with(
                mock_client, "cachedContent/abc123"
            )
            self.assertIn("Restructured", result)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @patch("versline.services.summarizer.settings")
    @patch("versline.services.summarizer.ai")
    def test_didactic_gemini_fallback_when_cache_unavailable(self, mock_ai, mock_settings):
        """If Gemini cache creation returns None, fall back to inline full-text call."""
        mock_settings.llm.provider = "google"
        mock_settings.llm.model = "gemini-2.0-flash"
        mock_settings.llm.api_key = "fake"
        mock_settings.llm.api_endpoint = None
        mock_settings.llm.proxy = None

        fake_blueprint = MagicMock()
        fake_blueprint.usage_metadata = MagicMock(
            prompt_token_count=5, candidates_token_count=10
        )
        fake_blueprint.text = "Blueprint: teach sequentially."

        fake_gen = MagicMock()
        fake_gen.usage_metadata = MagicMock(
            prompt_token_count=100, candidates_token_count=50
        )
        fake_gen.text = "## Fallback output"

        mock_ai.create_gemini_context_cache.return_value = None  # cache unavailable
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [fake_blueprint, fake_gen]
        mock_ai.configure_gemini.return_value = mock_client

        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write("# Doc\n\n" + "content " * 50)
            tmp_path = f.name

        try:
            s = TextSummarizer(mode="detailed", didactic=True)
            result = s.process_file(tmp_path)
            mock_ai.call_gemini_with_cache.assert_not_called()
            self.assertIn("Fallback", result)
        finally:
            Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Tests for output language and term preservation
# ---------------------------------------------------------------------------

class TestLanguageInstructions(unittest.TestCase):
    def test_auto_lang_instruction(self):
        s = TextSummarizer(mode="detailed", output_lang="auto")
        instr = s._language_instruction()
        self.assertIn("same language", instr)

    def test_explicit_lang_instruction(self):
        s = TextSummarizer(mode="detailed", output_lang="Persian")
        instr = s._language_instruction()
        self.assertIn("Persian", instr)
        self.assertNotIn("same language", instr)

    def test_auto_terms_instruction_no_preserve(self):
        """With auto lang, terms instruction should NOT ask for parenthetical originals."""
        s = TextSummarizer(mode="detailed", output_lang="auto", preserve_terms=True)
        instr = s._terms_instruction()
        self.assertNotIn("parentheses", instr)

    def test_explicit_lang_preserve_terms(self):
        s = TextSummarizer(mode="detailed", output_lang="English", preserve_terms=True)
        instr = s._terms_instruction()
        self.assertIn("parentheses", instr)

    def test_explicit_lang_no_preserve_terms(self):
        s = TextSummarizer(mode="detailed", output_lang="English", preserve_terms=False)
        instr = s._terms_instruction()
        self.assertNotIn("parentheses", instr)

    def test_default_output_lang_is_auto(self):
        s = TextSummarizer(mode="outline")
        self.assertEqual(s.output_lang.lower(), _AUTO_LANG)

    def test_default_preserve_terms_is_true(self):
        s = TextSummarizer(mode="slides")
        self.assertTrue(s.preserve_terms)

    @patch("versline.services.summarizer.settings")
    @patch("versline.services.summarizer.ai")
    def test_prompt_contains_language_instruction(self, mock_ai, mock_settings):
        """The prompt sent to the LLM must embed the language instruction."""
        mock_settings.llm.provider = "openai"
        mock_settings.llm.model = "gpt-4o-mini"
        mock_settings.llm.api_key = "fake"
        mock_settings.llm.api_endpoint = None
        mock_settings.llm.proxy = None

        fake_completion = MagicMock()
        fake_completion.usage = MagicMock(prompt_tokens=5, completion_tokens=5)
        fake_completion.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = fake_completion
        mock_ai.configure_openai.return_value = mock_client

        s = TextSummarizer(mode="detailed", output_lang="French", preserve_terms=True)
        s.summarize_chunk("Some content.", "gpt-4o-mini")

        call_args = mock_client.chat.completions.create.call_args
        sent_prompt = call_args.kwargs["messages"][0]["content"]
        self.assertIn("French", sent_prompt)
        self.assertIn("parentheses", sent_prompt)


if __name__ == "__main__":
    unittest.main()
