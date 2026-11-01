import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import typer

from versline.cli import hoist_global_options
from versline.commands import _batch
from versline.commands._batch import (
    DONE, SKIPPED, TEXT_EXTENSIONS, expand_inputs, resolve_batch_output, run_batch,
)
from versline.services import resume as resume_module
from versline.services.resume import ChunkResume
from versline.services.translation import TextTranslator


class ExpandInputsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "b.md").write_text("b")
        (self.root / "a.txt").write_text("a")
        (self.root / "image.png").write_text("x")
        (self.root / "a_translated.md").write_text("generated")
        (self.root / "talk_summary_outline.md").write_text("generated")
        (self.root / "sub").mkdir()
        (self.root / "sub" / "c.md").write_text("c")

    def tearDown(self):
        self._tmp.cleanup()

    def names(self, items):
        return [Path(i).name for i in items]

    def test_folder_filters_extensions_and_generated_outputs(self):
        result = expand_inputs([self.root], TEXT_EXTENSIONS)
        self.assertEqual(self.names(result), ["a.txt", "b.md"])

    def test_recursive_includes_subfolders(self):
        result = expand_inputs([self.root], TEXT_EXTENSIONS, recursive=True)
        self.assertEqual(self.names(result), ["a.txt", "b.md", "c.md"])

    def test_explicit_file_kept_regardless_of_extension(self):
        result = expand_inputs([self.root / "image.png"], TEXT_EXTENSIONS)
        self.assertEqual(self.names(result), ["image.png"])

    def test_dedupes_and_keeps_order(self):
        result = expand_inputs([self.root / "b.md", self.root, self.root / "b.md"], TEXT_EXTENSIONS)
        self.assertEqual(self.names(result), ["b.md", "a.txt"])

    def test_glob_pattern_expanded(self):
        result = expand_inputs([str(self.root / "*.md")], TEXT_EXTENSIONS)
        self.assertEqual(self.names(result), ["a_translated.md", "b.md", "talk_summary_outline.md"])

    def test_missing_path_is_an_error(self):
        with self.assertRaises(typer.BadParameter):
            expand_inputs([self.root / "nope.md"], TEXT_EXTENSIONS)

    def test_urls_pass_through_only_when_allowed(self):
        self.assertEqual(expand_inputs(["https://x.test/a.mp3"], [], allow_urls=True), ["https://x.test/a.mp3"])
        with self.assertRaises(typer.BadParameter):
            expand_inputs(["https://x.test/a.mp3"], [])

    def test_batch_output_must_be_directory_for_many_inputs(self):
        target = self.root / "b.md"
        self.assertEqual(resolve_batch_output(target, 1), target)
        with self.assertRaises(typer.BadParameter):
            resolve_batch_output(target, 2)
        out = self.root / "out"
        self.assertEqual(resolve_batch_output(out, 2), out)
        self.assertTrue(out.is_dir())


class RunBatchTests(unittest.TestCase):
    def test_continues_after_failure_and_exits_nonzero(self):
        seen = []

        def process(item):
            seen.append(item)
            if item == "bad":
                raise RuntimeError("boom")
            return SKIPPED if item == "skip" else DONE

        with self.assertRaises(typer.Exit) as ctx:
            run_batch(["ok", "bad", "skip", "ok2"], process)
        self.assertEqual(ctx.exception.exit_code, 1)
        self.assertEqual(seen, ["ok", "bad", "skip", "ok2"])

    def test_all_success_does_not_raise(self):
        run_batch(["a", "b"], lambda item: DONE)

    def test_typer_exit_zero_is_not_a_failure(self):
        def process(item):
            raise typer.Exit()

        run_batch(["a"], process)


class HoistGlobalOptionsTests(unittest.TestCase):
    def test_moves_flags_after_subcommand_to_front(self):
        self.assertEqual(
            hoist_global_options(["translate", "a.md", "-v", "--env-file", ".env", "-l", "fr"]),
            ["-v", "--env-file", ".env", "translate", "a.md", "-l", "fr"],
        )

    def test_equals_form_and_leading_globals(self):
        self.assertEqual(
            hoist_global_options(["-v", "transcribe", "a.mp3", "--env-file=.env"]),
            ["-v", "--env-file=.env", "transcribe", "a.mp3"],
        )

    def test_leaves_double_dash_tail_alone(self):
        self.assertEqual(
            hoist_global_options(["summarize", "a.md", "--", "-v"]),
            ["summarize", "a.md", "--", "-v"],
        )

    def test_no_subcommand(self):
        self.assertEqual(hoist_global_options(["--version"]), ["--version"])
        self.assertEqual(hoist_global_options([]), [])


class TranslateResumeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        patcher = mock.patch.object(resume_module, "WORK_DIR", self.root / "work_dir")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)
        self.source = self.root / "doc.md"
        # write_bytes: write_text would turn "\n\n" into CRLF on Windows and the text would no longer split into chunks
        self.source.write_bytes("\n\n".join(f"paragraph {i} " + "x" * 1500 for i in range(4)).encode("utf-8"))

    def make_translator(self):
        translator = TextTranslator()
        return translator

    def test_resumes_from_saved_chunks_after_interruption(self):
        calls = []

        def flaky(chunk, lang, model):
            calls.append(chunk)
            if len(calls) == 3:
                raise RuntimeError("interrupted")
            return f"T[{chunk[:11]}]"

        translator = self.make_translator()
        with mock.patch.object(translator, "translate_chunk", side_effect=flaky):
            with self.assertRaises(RuntimeError):
                translator.process_file(str(self.source), target_language="French")
        self.assertEqual(len(calls), 3)

        second = []

        def fine(chunk, lang, model):
            second.append(chunk)
            return f"T[{chunk[:11]}]"

        translator = self.make_translator()
        with mock.patch.object(translator, "translate_chunk", side_effect=fine):
            result = translator.process_file(str(self.source), target_language="French")

        total_chunks = len(translator.split_text(self.source.read_text(encoding="utf-8")))
        self.assertEqual(len(second), total_chunks - 2)
        self.assertEqual(result.count("T["), total_chunks)
        self.assertFalse(list((self.root / "work_dir").rglob("*progress*.json")))

    def test_changed_settings_do_not_reuse_progress(self):
        a = ChunkResume("translate", str(self.source), "text", ["French"])
        b = ChunkResume("translate", str(self.source), "text", ["German"])
        a.save(0, "bonjour")
        self.assertEqual(a.load(), {0: "bonjour"})
        self.assertEqual(b.load(), {})


if __name__ == "__main__":
    unittest.main()


class CliInvocationTests(unittest.TestCase):
    def test_options_after_inputs_and_batch_skip(self):
        from typer.testing import CliRunner
        from versline.cli import app

        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            docs.mkdir()
            (docs / "a.md").write_text("hello", encoding="utf-8")
            (docs / "b.md").write_text("world", encoding="utf-8")
            calls = []

            def fake(self, chunk, lang, model):
                calls.append((chunk, lang))
                return f"FR:{chunk}"

            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with mock.patch.object(TextTranslator, "translate_chunk", fake), \
                        mock.patch("versline.commands.setup.maybe_notify_update"):
                    runner = CliRunner()
                    first = runner.invoke(app, ["translate", str(docs / "a.md"), str(docs / "b.md"), "-l", "French", "-o", str(Path(tmp) / "out")])
                    second = runner.invoke(app, ["translate", str(docs), "-l", "French", "-o", str(Path(tmp) / "out")])
            finally:
                os.chdir(cwd)

            self.assertEqual(first.exit_code, 0, first.output)
            self.assertEqual(second.exit_code, 0, second.output)
            self.assertEqual(sorted(p.name for p in (Path(tmp) / "out").glob("*.md")), ["a_translated.md", "b_translated.md"])
            self.assertEqual(calls, [("hello", "French"), ("world", "French")])
