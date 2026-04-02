import unittest

from versline.config import settings
from versline.services.rag.base import BaseChunker, BaseEmbedder, BaseGenerator, BaseWebSearcher, Chunk, RetrievedChunk, WebSearchResult
from versline.services.rag.pipeline import RAGPipeline
from versline.services.rag.registry import VectorStoreRegistry


class _FakeChunker(BaseChunker):
    def chunk(self, documents, **kwargs):
        return [Chunk(id="c1", text="chunk", metadata={"source": "test"})]


class _FakeEmbedder(BaseEmbedder):
    def embed_documents(self, texts):
        return [[0.1, 0.2] for _ in texts]

    def embed_query(self, text):
        return [0.1, 0.2]


class _CaptureGenerator(BaseGenerator):
    def __init__(self):
        self.last_external_context = None

    def generate(self, query, context_chunks, **kwargs):
        self.last_external_context = kwargs.get("external_context")
        return "ok"


class _NoopSparseEmbedder:
    def embed_documents(self, texts):
        return []

    def embed_query(self, text):
        return {}


class _FakeStore:
    def ensure_collection(self, collection_name, vector_size):
        return None

    def reset_collection(self, collection_name):
        return None

    def upsert(self, collection_name, chunks, vectors):
        return None

    def search(self, collection_name, query_vector, top_k=5, filters=None):
        return [RetrievedChunk(id="r1", text="dense context", score=0.9, metadata={"source": "x"})]


class _FakeWebSearcher(BaseWebSearcher):
    def __init__(self, results):
        self._results = results

    def search(self, query: str, top_k: int = 3):
        return self._results[:top_k]


class TestRAGWebSearch(unittest.TestCase):
    def test_pipeline_passes_web_context_to_generator(self):
        prev_enabled = settings.rag.web_search_enabled
        prev_top_k = settings.rag.web_search_top_k
        prev_max_chars = settings.rag.web_search_max_context_chars
        prev_hybrid_enabled = settings.rag.hybrid_enabled
        settings.rag.web_search_enabled = True
        settings.rag.web_search_top_k = 2
        settings.rag.web_search_max_context_chars = 2000
        settings.rag.hybrid_enabled = False

        try:
            stores = VectorStoreRegistry()
            stores.register("fake", _FakeStore())

            generator = _CaptureGenerator()
            web_searcher = _FakeWebSearcher(
                [
                    WebSearchResult(title="T1", url="https://a.example", snippet="S1"),
                    WebSearchResult(title="T2", url="https://b.example", snippet="S2"),
                ]
            )
            pipeline = RAGPipeline(
                chunker=_FakeChunker(),
                embedder=_FakeEmbedder(),
                sparse_embedder=_NoopSparseEmbedder(),
                reranker=None,
                mcp_client=None,
                web_searcher=web_searcher,
                generator=generator,
                vector_store_registry=stores,
                vector_backend="fake",
                collection_name="c",
            )

            result = pipeline.generate(query="latest news", top_k=1)

            self.assertEqual(result["answer"], "ok")
            self.assertTrue(result["external_context_used"])
            self.assertTrue(result["web_context_used"])
            self.assertEqual(len(result["web_sources"]), 2)
            self.assertIn("[Web Search Context]", generator.last_external_context)
            self.assertIn("https://a.example", generator.last_external_context)
        finally:
            settings.rag.web_search_enabled = prev_enabled
            settings.rag.web_search_top_k = prev_top_k
            settings.rag.web_search_max_context_chars = prev_max_chars
            settings.rag.hybrid_enabled = prev_hybrid_enabled

    def test_pipeline_handles_empty_web_results(self):
        prev_enabled = settings.rag.web_search_enabled
        prev_hybrid_enabled = settings.rag.hybrid_enabled
        settings.rag.web_search_enabled = True
        settings.rag.hybrid_enabled = False

        try:
            stores = VectorStoreRegistry()
            stores.register("fake", _FakeStore())

            generator = _CaptureGenerator()
            web_searcher = _FakeWebSearcher([])
            pipeline = RAGPipeline(
                chunker=_FakeChunker(),
                embedder=_FakeEmbedder(),
                sparse_embedder=_NoopSparseEmbedder(),
                reranker=None,
                mcp_client=None,
                web_searcher=web_searcher,
                generator=generator,
                vector_store_registry=stores,
                vector_backend="fake",
                collection_name="c",
            )

            result = pipeline.generate(query="anything", top_k=1)

            self.assertFalse(result["web_context_used"])
            self.assertEqual(result["web_sources"], [])
        finally:
            settings.rag.web_search_enabled = prev_enabled
            settings.rag.hybrid_enabled = prev_hybrid_enabled


if __name__ == "__main__":
    unittest.main()
