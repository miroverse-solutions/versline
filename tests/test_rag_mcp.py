import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from versline.config import settings
from versline.services.rag.base import BaseChunker, BaseEmbedder, BaseGenerator, BasePreprocessor, Chunk, Document, RetrievedChunk
from versline.services.rag.mcp_client import MCPClientConfig, MCPContextClient
from versline.services.rag.pipeline import RAGPipeline
from versline.services.rag.registry import PreprocessorRegistry, VectorStoreRegistry


class _FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _FakeHTTPClient:
    def __init__(self, payload):
        self.payload = payload

    def post(self, *args, **kwargs):
        return _FakeHTTPResponse(self.payload)


class _FakePreprocessor(BasePreprocessor):
    def preprocess(self, file_path: str, **kwargs):
        text = Path(file_path).read_text(encoding="utf-8")
        return [Document(text=text, metadata={"source": file_path})]


class _FakeChunker(BaseChunker):
    def chunk(self, documents, **kwargs):
        return [Chunk(id="c1", text=documents[0].text, metadata=documents[0].metadata)]


class _FakeEmbedder(BaseEmbedder):
    def embed_documents(self, texts):
        return [[0.1, 0.2] for _ in texts]

    def embed_query(self, text):
        return [0.1, 0.2]


class _FakeSparseEmbedder:
    def embed_documents(self, texts):
        return [{"indices": [1], "values": [1.0]} for _ in texts]

    def embed_query(self, text):
        return {"indices": [1], "values": [1.0]}


class _CaptureGenerator(BaseGenerator):
    def __init__(self):
        self.last_external_context = None

    def generate(self, query, context_chunks, **kwargs):
        self.last_external_context = kwargs.get("external_context")
        return "ok"


class _FakeStore:
    def ensure_collection(self, collection_name, vector_size):
        return None

    def reset_collection(self, collection_name):
        return None

    def upsert(self, collection_name, chunks, vectors):
        return None

    def search(self, collection_name, query_vector, top_k=5, filters=None):
        return [RetrievedChunk(id="r1", text="dense context", score=0.9, metadata={"source": "x"})]


class _FakeMCPClient:
    def fetch_context(self, query: str, top_k: int = 5, metadata=None):
        return "external mcp context"


class TestRAGMCP(unittest.TestCase):
    @patch("versline.services.rag.mcp_client.httpx.Client", autospec=True)
    def test_mcp_http_fetch_context(self, http_client_ctor):
        http_client_ctor.return_value = _FakeHTTPClient({"context": "hello from mcp"})
        client = MCPContextClient(
            MCPClientConfig(
                transport="http",
                tool_name="retrieve_context",
                timeout_seconds=10,
                max_context_chars=1000,
                server_url="http://localhost:8080/mcp/context",
            )
        )

        context = client.fetch_context(query="q", top_k=3)

        self.assertEqual(context, "hello from mcp")

    def test_pipeline_passes_mcp_context_to_generator(self):
        prev_mcp_enabled = settings.rag.mcp_enabled
        settings.rag.mcp_enabled = True
        try:
            temp_dir = tempfile.TemporaryDirectory()
            base = Path(temp_dir.name)
            source_file = base / "a.md"
            source_file.write_text("hello", encoding="utf-8")

            preprocessors = PreprocessorRegistry()
            preprocessors.register("markdown", _FakePreprocessor())
            stores = VectorStoreRegistry()
            stores.register("fake", _FakeStore())

            generator = _CaptureGenerator()
            pipeline = RAGPipeline(
                chunker=_FakeChunker(),
                embedder=_FakeEmbedder(),
                sparse_embedder=_FakeSparseEmbedder(),
                reranker=None,
                mcp_client=_FakeMCPClient(),
                generator=generator,
                preprocessor_registry=preprocessors,
                vector_store_registry=stores,
                vector_backend="fake",
                collection_name="c",
            )

            result = pipeline.generate(query="test", top_k=1)
            self.assertEqual(result["answer"], "ok")
            self.assertTrue(result["external_context_used"])
            self.assertEqual(generator.last_external_context, "external mcp context")
            temp_dir.cleanup()
        finally:
            settings.rag.mcp_enabled = prev_mcp_enabled


if __name__ == "__main__":
    unittest.main()
