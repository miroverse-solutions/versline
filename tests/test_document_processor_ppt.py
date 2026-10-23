import unittest
from pathlib import Path
from unittest.mock import patch

from versline.services.document_processor import (
    PPTXProcessor,
    _import_pymupdf,
    get_file_processor,
    process_pdf,
)


class TestDocumentProcessorPptSupport(unittest.TestCase):
    def test_get_file_processor_accepts_ppt(self):
        processor = get_file_processor("legacy.ppt")
        self.assertIsInstance(processor, PPTXProcessor)

    @patch("versline.services.document_processor.process_pptx", autospec=True)
    @patch("versline.services.document_processor.convert_ppt_to_pptx", autospec=True)
    @patch("versline.services.document_processor.os.path.isdir", autospec=True)
    @patch("versline.services.document_processor.shutil.rmtree", autospec=True)
    def test_ppt_converts_then_processes_as_pptx(
        self,
        rmtree_mock,
        isdir_mock,
        convert_ppt_to_pptx_mock,
        process_pptx_mock,
    ):
        convert_ppt_to_pptx_mock.return_value = "/tmp/versline_ppt_convert_x/legacy.pptx"
        # `process_pptx` returns list of tuples in production; keep mocked shape explicit.
        process_pptx_mock.return_value = ([("slide content", "Batch 1", 1)], [])
        isdir_mock.return_value = True

        processor = PPTXProcessor()
        chunks = processor.extract_text("legacy.ppt", slides_per_batch=5)

        convert_ppt_to_pptx_mock.assert_called_once_with("legacy.ppt")
        process_pptx_mock.assert_called_once_with(
            "/tmp/versline_ppt_convert_x/legacy.pptx",
            slides_per_batch=5,
        )
        self.assertEqual(chunks, [{"text": "slide content", "page": "Batch 1"}])
        rmtree_mock.assert_called_once_with(
            str(Path("/tmp/versline_ppt_convert_x/legacy.pptx").parent), ignore_errors=True
        )


class TestPyMuPDFImport(unittest.TestCase):
    @patch("versline.services.document_processor.importlib.import_module", autospec=True)
    def test_prefers_pymupdf_module(self, import_module_mock):
        pymupdf_module = object()
        import_module_mock.return_value = pymupdf_module

        result = _import_pymupdf()

        self.assertIs(result, pymupdf_module)
        import_module_mock.assert_called_once_with("pymupdf")

    @patch("versline.services.document_processor.importlib.import_module", autospec=True)
    def test_raises_clear_error_for_conflicting_fitz(self, import_module_mock):
        class BadFitz:
            pass

        import_module_mock.side_effect = [ModuleNotFoundError("no pymupdf"), BadFitz()]

        with self.assertRaises(RuntimeError) as exc_info:
            _import_pymupdf()

        self.assertIn("incompatible 'fitz'", str(exc_info.exception))


class TestPdfFallback(unittest.TestCase):
    @patch("versline.services.document_processor.convert_to_markdown", autospec=True)
    @patch("versline.services.document_processor.split_pdf_to_batches", autospec=True)
    def test_process_pdf_falls_back_to_full_document_when_pymupdf_unavailable(
        self,
        split_pdf_to_batches_mock,
        convert_to_markdown_mock,
    ):
        split_pdf_to_batches_mock.side_effect = RuntimeError(
            "Failed to import PyMuPDF. A conflicting 'fitz' package may be installed."
        )
        convert_to_markdown_mock.return_value = "full document text"

        batches, temp_files = process_pdf("file.pdf", pages_per_batch=5)

        self.assertEqual(temp_files, [])
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0][0], "full document text")
        self.assertEqual(batches[0][1], "Batch 1 of 1 (Full document fallback)")
        self.assertEqual(batches[0][3], "full")


if __name__ == "__main__":
    unittest.main()
