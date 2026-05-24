import unittest
from unittest.mock import patch

from versline.services.document_processor import PPTXProcessor, get_file_processor


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
        rmtree_mock.assert_called_once_with("/tmp/versline_ppt_convert_x", ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
