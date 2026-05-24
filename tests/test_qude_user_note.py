"""Tests for user_note support in QuestionDesigner."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestQuestionDesignerUserNote(unittest.TestCase):
    def _make_designer(self, tmpdir, user_note=None, **kwargs):
        from versline.services.question_generator import QuestionDesigner

        with patch("versline.services.question_generator.CacheManager"), \
             patch("versline.services.question_generator.AIClient"):
            designer = QuestionDesigner(
                input_path=str(tmpdir),
                output_dir=str(tmpdir),
                user_note=user_note,
                **kwargs,
            )
        return designer

    def test_user_note_stored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            designer = self._make_designer(tmpdir, user_note="Focus on definitions.")
            self.assertEqual(designer.user_note, "Focus on definitions.")

    def test_no_user_note_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            designer = self._make_designer(tmpdir)
            self.assertIsNone(designer.user_note)

    def test_user_note_appended_to_system_prompt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            designer = self._make_designer(tmpdir, user_note="Focus on definitions.")
            self.assertIn("Focus on definitions.", designer.system_prompt)
            self.assertIn("Additional instructions from user", designer.system_prompt)

    def test_no_user_note_does_not_pollute_prompt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            designer = self._make_designer(tmpdir)
            self.assertNotIn("Additional instructions from user", designer.system_prompt)

    def test_user_note_appears_after_base_prompt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            designer = self._make_designer(tmpdir, user_note="Use simple language.")
            idx_note = designer.system_prompt.find("Use simple language.")
            # The note must come after some base prompt content
            self.assertGreater(idx_note, 0)


class TestResolveUserNoteIntegration(unittest.TestCase):
    """Test that resolve_user_note feeds correctly into QuestionDesigner."""

    def test_note_file_content_used(self):
        from versline.core.prompts import resolve_user_note
        from versline.services.question_generator import QuestionDesigner

        with tempfile.TemporaryDirectory() as tmpdir:
            note_path = Path(tmpdir) / "note.md"
            note_path.write_text("Always include examples.", encoding="utf-8")

            resolved = resolve_user_note(note_file=str(note_path))
            self.assertEqual(resolved, "Always include examples.")

            with patch("versline.services.question_generator.CacheManager"), \
                 patch("versline.services.question_generator.AIClient"):
                designer = QuestionDesigner(
                    input_path=tmpdir,
                    output_dir=tmpdir,
                    user_note=resolved,
                )
            self.assertIn("Always include examples.", designer.system_prompt)

    def test_inline_note_takes_precedence_over_none_file(self):
        from versline.core.prompts import resolve_user_note

        resolved = resolve_user_note(note="Inline note", note_file=None)
        self.assertEqual(resolved, "Inline note")


class TestQuestionTypeAliases(unittest.TestCase):
    def test_open_alias_maps_to_descriptive(self):
        from versline.core.types import QuestionType

        self.assertEqual(QuestionType("open"), QuestionType.DESCRIPTIVE)

    def test_mixed_case_alias_is_supported(self):
        from versline.core.types import QuestionType

        self.assertEqual(QuestionType("Open"), QuestionType.DESCRIPTIVE)


class TestQuestionDesignerProviderPassing(unittest.TestCase):
    def test_provider_passed_to_ai_client_as_string(self):
        from versline.services.question_generator import QuestionDesigner

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("versline.services.question_generator.CacheManager"), \
                 patch("versline.services.question_generator.AIClient") as mock_ai:
                QuestionDesigner(
                    input_path=tmpdir,
                    output_dir=tmpdir,
                    provider="openai",
                )

            self.assertEqual(mock_ai.call_count, 1)
            call_kwargs = mock_ai.call_args.kwargs
            self.assertEqual(call_kwargs["provider"], "openai")


if __name__ == "__main__":
    unittest.main()
