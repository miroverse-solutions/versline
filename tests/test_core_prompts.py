import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from versline.core.prompts import load_prompt, resolve_text_input


class TestCorePrompts(unittest.TestCase):
    def tearDown(self):
        load_prompt.cache_clear()

    def test_load_prompt_is_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompt_path = Path(tmp) / "cached.md"
            prompt_path.write_text("prompt-body", encoding="utf-8")

            read_count = 0
            original_read_text = Path.read_text

            def counting_read_text(self, *args, **kwargs):
                nonlocal read_count
                read_count += 1
                return original_read_text(self, *args, **kwargs)

            with patch("versline.core.prompts.get_default_prompt_path", return_value=prompt_path), patch.object(
                Path, "read_text", new=counting_read_text
            ):
                load_prompt.cache_clear()
                first = load_prompt("cached.md")
                second = load_prompt("cached.md")

        self.assertEqual(first, "prompt-body")
        self.assertEqual(second, "prompt-body")
        self.assertEqual(read_count, 1)

    def test_resolve_text_input_reads_revision_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            revision_path = Path(tmp) / "revisions.md"
            revision_path.write_text("  revise this  ", encoding="utf-8")

            result = resolve_text_input(text_file=str(revision_path), label="Revision", allowed_suffixes=(".md", ".txt"))

        self.assertEqual(result, "revise this")


if __name__ == "__main__":
    unittest.main()
