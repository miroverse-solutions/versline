import unittest
from types import SimpleNamespace
from unittest.mock import patch

from versline.config import settings
from versline.services.rag.base import RetrievedChunk
from versline.services.rag.rerankers import CohereReranker, JinaReranker, OpenAICompatibleReranker


class _FakeCohereClient:
    def __init__(self, results):
        self._results = results

    def rerank(self, **kwargs):
        return SimpleNamespace(results=self._results)


class _FakeOpenAICompletions:
    def __init__(self, content: str):
        self._content = content

    def create(self, **kwargs):
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=4),
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))],
        )


class _FakeOpenAIClient:
    def __init__(self, content: str):
        self.base_url = "https://api.openai.com/v1"
        self.chat = SimpleNamespace(completions=_FakeOpenAICompletions(content=content))


class _FakeHTTPResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeHTTPClient:
    def __init__(self, payload):
        self._payload = payload

    def post(self, *args, **kwargs):
        return _FakeHTTPResponse(self._payload)


class TestRAGRerankers(unittest.TestCase):
    @patch("versline.services.rag.rerankers.cohere.Client", autospec=True)
    def test_cohere_reranker_orders_by_response(self, client_ctor):
        results = [
            SimpleNamespace(index=2, relevance_score=0.99),
            {"index": 0, "relevance_score": 0.77},
        ]
        client_ctor.return_value = _FakeCohereClient(results)

        reranker = CohereReranker(model="rerank-v3.5", api_key="x")
        items = [
            RetrievedChunk(id="a", text="doc a", score=0.1, metadata={}),
            RetrievedChunk(id="b", text="doc b", score=0.2, metadata={}),
            RetrievedChunk(id="c", text="doc c", score=0.3, metadata={}),
        ]

        ranked = reranker.rerank(query="q", items=items, top_k=2)

        self.assertEqual([item.id for item in ranked], ["c", "a"])
        self.assertAlmostEqual(ranked[0].score, 0.99)

    @patch("versline.services.rag.rerankers.cohere.Client", autospec=True)
    def test_cohere_reranker_fallback_when_no_results(self, client_ctor):
        client_ctor.return_value = _FakeCohereClient(results=[])

        reranker = CohereReranker(model="rerank-v3.5", api_key="x")
        items = [RetrievedChunk(id="a", text="doc a", score=0.5, metadata={})]

        ranked = reranker.rerank(query="q", items=items, top_k=1)

        self.assertEqual([item.id for item in ranked], ["a"])

    @patch("versline.services.rag.rerankers.OpenAI", autospec=True)
    def test_openai_reranker_orders_by_ranked_indices(self, openai_ctor):
        openai_ctor.return_value = _FakeOpenAIClient('{"ranked_indices": [2, 0]}')

        reranker = OpenAICompatibleReranker(model="gpt-4o-mini", api_key="x")
        items = [
            RetrievedChunk(id="a", text="doc a", score=0.1, metadata={}),
            RetrievedChunk(id="b", text="doc b", score=0.2, metadata={}),
            RetrievedChunk(id="c", text="doc c", score=0.3, metadata={}),
        ]

        ranked = reranker.rerank(query="q", items=items, top_k=2)

        self.assertEqual([item.id for item in ranked], ["c", "a"])

    @patch("versline.services.rag.rerankers.OpenAI", autospec=True)
    def test_openai_reranker_fallback_on_bad_json(self, openai_ctor):
        openai_ctor.return_value = _FakeOpenAIClient('not-json')

        previous_retries = settings.rag.retry_max_retries
        previous_base = settings.rag.retry_base_delay_seconds
        previous_max = settings.rag.retry_max_delay_seconds
        settings.rag.retry_max_retries = 1
        settings.rag.retry_base_delay_seconds = 0.0
        settings.rag.retry_max_delay_seconds = 0.0
        try:
            reranker = OpenAICompatibleReranker(model="gpt-4o-mini", api_key="x")
            items = [RetrievedChunk(id="a", text="doc a", score=0.5, metadata={})]

            ranked = reranker.rerank(query="q", items=items, top_k=1)

            self.assertEqual([item.id for item in ranked], ["a"])
        finally:
            settings.rag.retry_max_retries = previous_retries
            settings.rag.retry_base_delay_seconds = previous_base
            settings.rag.retry_max_delay_seconds = previous_max

    @patch("versline.services.rag.rerankers.OpenAI", autospec=True)
    def test_local_reranker_uses_local_defaults_without_api_key(self, openai_ctor):
        previous_provider = settings.rag.rerank_provider
        previous_endpoint = settings.rag.rerank_api_endpoint
        previous_rerank_key = settings.rag.rerank_api_key
        previous_llm_key = settings.llm.api_key
        settings.rag.rerank_provider = "local"
        settings.rag.rerank_api_endpoint = None
        settings.rag.rerank_api_key = None
        settings.llm.api_key = None
        try:
            OpenAICompatibleReranker(model="bge-reranker-v2-m3")

            _, kwargs = openai_ctor.call_args
            self.assertEqual(kwargs.get("base_url"), "http://localhost:11434/v1")
            self.assertEqual(kwargs.get("api_key"), "local")
        finally:
            settings.rag.rerank_provider = previous_provider
            settings.rag.rerank_api_endpoint = previous_endpoint
            settings.rag.rerank_api_key = previous_rerank_key
            settings.llm.api_key = previous_llm_key

    @patch("versline.services.rag.rerankers.httpx.Client", autospec=True)
    def test_jina_reranker_orders_by_response(self, http_client_ctor):
        payload = {
            "results": [
                {"index": 1, "relevance_score": 0.91},
                {"index": 0, "relevance_score": 0.80},
            ]
        }
        http_client_ctor.return_value = _FakeHTTPClient(payload)

        reranker = JinaReranker(model="jina-reranker-v2-base-multilingual", api_key="x")
        items = [
            RetrievedChunk(id="a", text="doc a", score=0.1, metadata={}),
            RetrievedChunk(id="b", text="doc b", score=0.2, metadata={}),
        ]

        ranked = reranker.rerank(query="q", items=items, top_k=2)

        self.assertEqual([item.id for item in ranked], ["b", "a"])


if __name__ == "__main__":
    unittest.main()
