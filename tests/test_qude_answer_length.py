"""Tests for answer_length option in QuestionDesigner (descriptive type)."""

import tempfile
import unittest
from unittest.mock import patch


class TestAnswerLengthInstruction(unittest.TestCase):
    def _make_designer(self, tmpdir, question_type="descriptive", answer_length=None):
        from versline.services.question_generator import QuestionDesigner

        with patch("versline.services.question_generator.CacheManager"), \
             patch("versline.services.question_generator.AIClient"):
            designer = QuestionDesigner(
                input_path=str(tmpdir),
                output_dir=str(tmpdir),
                question_type=question_type,
                answer_length=answer_length,
            )
        return designer

    # --- Preset values ---

    def test_short_preset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self._make_designer(tmpdir, answer_length="short")
            self.assertIn("50", d.system_prompt)
            self.assertIn("100", d.system_prompt)

    def test_medium_preset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self._make_designer(tmpdir, answer_length="medium")
            self.assertIn("150", d.system_prompt)
            self.assertIn("200", d.system_prompt)

    def test_long_preset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self._make_designer(tmpdir, answer_length="long")
            self.assertIn("300", d.system_prompt)
            self.assertIn("400", d.system_prompt)

    def test_mixed_preset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self._make_designer(tmpdir, answer_length="mixed")
            self.assertIn("mix", d.system_prompt.lower())
            self.assertIn("50", d.system_prompt)
            self.assertIn("300", d.system_prompt)
            self.assertIn("must not dominate", d.system_prompt)
            self.assertIn("Do not pad", d.system_prompt)

    # --- Numeric word count ---

    def test_numeric_word_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self._make_designer(tmpdir, answer_length="200")
            self.assertIn("200", d.system_prompt)

    def test_numeric_word_count_large(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self._make_designer(tmpdir, answer_length="500")
            self.assertIn("500", d.system_prompt)

    # --- Case insensitivity ---

    def test_preset_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self._make_designer(tmpdir, answer_length="MEDIUM")
            self.assertIn("150", d.system_prompt)

    def test_preset_mixed_case(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self._make_designer(tmpdir, answer_length="Long")
            self.assertIn("300", d.system_prompt)

    # --- No answer_length (default) ---

    def test_no_answer_length_does_not_pollute_prompt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self._make_designer(tmpdir, answer_length=None)
            self.assertNotIn("{{answer_length}}", d.system_prompt)
            # No word count instruction injected
            self.assertNotIn("approximately", d.system_prompt)

    # --- Non-descriptive types ignore answer_length ---

    def test_answer_length_ignored_for_mcq(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self._make_designer(tmpdir, question_type="mcq", answer_length="200")
            self.assertNotIn("approximately 200 words", d.system_prompt)

    def test_answer_length_ignored_for_mcq_mixed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self._make_designer(tmpdir, question_type="mcq", answer_length="mixed")
            self.assertNotIn("mix", d.system_prompt.lower())

    # --- Placeholder is always replaced ---

    def test_placeholder_replaced_when_no_answer_length(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self._make_designer(tmpdir, answer_length=None)
            self.assertNotIn("{{answer_length}}", d.system_prompt)

    def test_placeholder_replaced_with_instruction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self._make_designer(tmpdir, answer_length="300")
            self.assertNotIn("{{answer_length}}", d.system_prompt)

    # --- answer_length attribute is stored ---

    def test_answer_length_stored_on_designer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self._make_designer(tmpdir, answer_length="medium")
            self.assertEqual(d.answer_length, "medium")

    def test_answer_length_none_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self._make_designer(tmpdir)
            self.assertIsNone(d.answer_length)

    def test_padded_short_answer_is_collapsed_to_short_answer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self._make_designer(tmpdir, answer_length="mixed")
            normalized = d._normalize_question_record(
                {
                    "question": "What is the capital of France?",
                    "answer": "The capital of France is Paris.",
                    "type": "descriptive",
                }
            )
            self.assertIsNotNone(normalized)
            self.assertEqual(normalized["answer"], "Paris")
            self.assertEqual(normalized["type"], "short_answer")

    def test_mixed_rebalance_limits_short_answer_dominance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self._make_designer(tmpdir, answer_length="mixed")
            medium_answer = " ".join(["medium"] * 140)
            long_answer = " ".join(["long"] * 260)
            questions = [
                {"question": "Q1", "answer": "short item", "type": "short_answer"},
                {"question": "Q2", "answer": "another short item", "type": "short_answer"},
                {"question": "Q3", "answer": "third short item", "type": "short_answer"},
                {"question": "Q4", "answer": medium_answer, "type": "descriptive"},
                {"question": "Q5", "answer": long_answer, "type": "descriptive"},
            ]
            rebalanced = d._rebalance_mixed_answer_lengths(questions)

            self.assertEqual(len(rebalanced), 3)
            short_count = sum(1 for item in rebalanced if item["type"] == "short_answer")
            self.assertEqual(short_count, 1)

    def test_empty_questions_are_removed_in_post_processing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self._make_designer(tmpdir, answer_length="mixed")
            processed = d._post_process_questions(
                [
                    {"question": "", "answer": "x", "type": "descriptive"},
                    {"question": "Valid?", "answer": "Yes", "type": "descriptive"},
                ]
            )

            self.assertEqual(len(processed), 1)
            self.assertEqual(processed[0]["type"], "short_answer")


if __name__ == "__main__":
    unittest.main()
