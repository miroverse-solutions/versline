import unittest
from types import SimpleNamespace
from unittest.mock import patch

from versline.services.pricing import TokenTracker
from versline.services.rag.embedders import OpenAICompatibleEmbedder
from versline.services.rag.generators import PromptRAGGenerator


class _FakeRawResponse:
    def __init__(self, parsed):
        self._parsed = parsed
        self.headers = {"x-request-id": "req_test_123"}

    def parse(self):
        return self._parsed


class _FakeOpenAIClient:
    def __init__(self):
        embedding_parsed = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=12),
            data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])],
        )
        completion_parsed = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=7),
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        )

        self.base_url = "https://api.avalai.ir/v1"
        self.embeddings = SimpleNamespace(
            with_raw_response=SimpleNamespace(
                create=lambda **kwargs: _FakeRawResponse(embedding_parsed)
            )
        )
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(
                with_raw_response=SimpleNamespace(
                    create=lambda **kwargs: _FakeRawResponse(completion_parsed)
                )
            )
        )


class TestRagAvalaiTracking(unittest.TestCase):
    @patch("versline.services.rag.embedders.OpenAI", autospec=True)
    def test_embedder_tracks_avalai_request_id(self, openai_ctor):
        openai_ctor.return_value = _FakeOpenAIClient()
        tracker = TokenTracker()
        embedder = OpenAICompatibleEmbedder(model="dummy", provider="avalai", tracker=tracker)

        vectors = embedder.embed_documents(["hello"])

        self.assertEqual(len(vectors), 1)
        self.assertIn("req_test_123", tracker.avalai_request_ids)

    @patch("versline.services.rag.generators.OpenAI", autospec=True)
    def test_generator_tracks_avalai_request_id(self, openai_ctor):
        openai_ctor.return_value = _FakeOpenAIClient()
        tracker = TokenTracker()
        generator = PromptRAGGenerator(model="dummy", provider="avalai", tracker=tracker)

        result = generator.generate(query="q", context_chunks=[])

        self.assertEqual(result, "ok")
        self.assertIn("req_test_123", tracker.avalai_request_ids)


if __name__ == "__main__":
    unittest.main()
