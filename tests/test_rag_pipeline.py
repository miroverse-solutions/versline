import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from versline.config import settings
from versline.services.rag.base import BaseChunker, BaseEmbedder, BaseGenerator, BasePreprocessor, Chunk, Document, RetrievedChunk
from versline.services.rag.pipeline import RAGPipeline
from versline.services.rag.registry import PreprocessorRegistry, VectorStoreRegistry


class FakePreprocessor(BasePreprocessor):
    def preprocess(self, file_path: str, **kwargs) -> List[Document]:
        text = Path(file_path).read_text(encoding="utf-8")
        return [Document(text=text, metadata={"source": file_path})]


class FakeChunker(BaseChunker):
    def chunk(self, documents: List[Document], **kwargs) -> List[Chunk]:
        chunks: List[Chunk] = []
        for index, doc in enumerate(documents):
            for part_index, part in enumerate(doc.text.split("\n")):
                if part.strip():
                    chunks.append(
                        Chunk(
                            id=f"{index}-{part_index}",
                            text=part,
                            metadata={"source": doc.metadata.get("source", "unknown")},
                        )
                    )
        return chunks


class FakeEmbedder(BaseEmbedder):
    def __init__(self):
        self.calls = 0

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        self.calls += 1
        return [[float(len(item)), 1.0] for item in texts]

    def embed_query(self, text: str) -> List[float]:
        return [float(len(text)), 1.0]


class FakeGenerator(BaseGenerator):
    def generate(self, query: str, context_chunks: List[RetrievedChunk], **kwargs) -> str:
        return f"answer:{query}:{len(context_chunks)}"


class FakeSparseEmbedder:
    def embed_documents(self, texts: List[str]) -> List[dict]:
        return [
            {
                "indices": [1, 2],
                "values": [0.9, 0.7],
            }
            for _ in texts
        ]

    def embed_query(self, text: str) -> dict:
        return {"indices": [1, 2], "values": [0.9, 0.7]}


class FakeReranker:
    def __init__(self):
        self.calls = 0

    def rerank(self, query: str, items: List[RetrievedChunk], top_k: int) -> List[RetrievedChunk]:
        self.calls += 1
        sorted_items = sorted(items, key=lambda item: item.id, reverse=True)
        return sorted_items[:top_k]


class FakeVectorStore:
    def __init__(self, fail_once_on_upsert_call: int = 0):
        self.collection = None
        self.upsert_calls = 0
        self.upsert_hybrid_calls = 0
        self.search_results: List[RetrievedChunk] = []
        self.hybrid_search_results: List[RetrievedChunk] = []
        self.hybrid_search_calls = 0
        self.fail_once_on_upsert_call = fail_once_on_upsert_call
        self.failed = False

    def ensure_collection(self, collection_name: str, vector_size: int) -> None:
        self.collection = collection_name

    def reset_collection(self, collection_name: str) -> None:
        self.collection = collection_name

    def upsert(self, collection_name: str, chunks: List[Chunk], vectors: List[List[float]]) -> None:
        self.upsert_calls += 1
        if (
            self.fail_once_on_upsert_call > 0
            and self.upsert_calls == self.fail_once_on_upsert_call
            and not self.failed
        ):
            self.failed = True
            raise RuntimeError("simulated network failure")

    def upsert_hybrid(
        self,
        collection_name: str,
        chunks: List[Chunk],
        dense_vectors: List[List[float]],
        sparse_vectors: List[Dict[str, List[float]]],
    ) -> None:
        self.upsert_hybrid_calls += 1
        self.upsert(collection_name, chunks, dense_vectors)

    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        top_k: int = 5,
        filters: Dict[str, Any] = None,
    ) -> List[RetrievedChunk]:
        return self.search_results[:top_k]

    def search_hybrid(
        self,
        collection_name: str,
        dense_query_vector: List[float],
        sparse_query_vector: Dict[str, List[float]],
        top_k: int = 5,
        filters: Dict[str, Any] = None,
        fetch_k: int = None,
    ) -> List[RetrievedChunk]:
        self.hybrid_search_calls += 1
        return self.hybrid_search_results[:top_k]


class TestRAGPipeline(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

        self.prev_state_dir = settings.rag.state_directory
        self.prev_batch = settings.rag.ingestion_batch_size
        self.prev_hybrid = settings.rag.hybrid_enabled
        self.prev_fetch = settings.rag.retrieve_fetch_k

        settings.rag.state_directory = self.base_path / "state"
        settings.rag.ingestion_batch_size = 2
        settings.rag.hybrid_enabled = True
        settings.rag.retrieve_fetch_k = 10

    def tearDown(self):
        settings.rag.state_directory = self.prev_state_dir
        settings.rag.ingestion_batch_size = self.prev_batch
        settings.rag.hybrid_enabled = self.prev_hybrid
        settings.rag.retrieve_fetch_k = self.prev_fetch
        self.temp_dir.cleanup()

    def _make_pipeline(self, store: FakeVectorStore, reranker=None) -> RAGPipeline:
        preprocessors = PreprocessorRegistry()
        preprocessors.register("markdown", FakePreprocessor())

        stores = VectorStoreRegistry()
        stores.register("fake", store)

        return RAGPipeline(
            chunker=FakeChunker(),
            embedder=FakeEmbedder(),
            sparse_embedder=FakeSparseEmbedder(),
            reranker=reranker,
            generator=FakeGenerator(),
            preprocessor_registry=preprocessors,
            vector_store_registry=stores,
            vector_backend="fake",
            collection_name="test_collection",
        )

    def test_ingest_directory(self):
        source_dir = self.base_path / "docs"
        source_dir.mkdir(parents=True, exist_ok=True)
        (source_dir / "a.md").write_text("line1\nline2", encoding="utf-8")
        (source_dir / "b.md").write_text("line3\nline4", encoding="utf-8")

        store = FakeVectorStore()
        pipeline = self._make_pipeline(store)

        result = pipeline.ingest_path(str(source_dir), input_type="markdown")

        self.assertEqual(result["files"], 2)
        self.assertEqual(result["chunks"], 4)
        self.assertGreaterEqual(store.upsert_hybrid_calls, 2)

    def test_resume_after_interruption(self):
        source_file = self.base_path / "resume.md"
        source_file.write_text("a\nb\nc\nd\ne", encoding="utf-8")

        store1 = FakeVectorStore(fail_once_on_upsert_call=2)
        pipeline1 = self._make_pipeline(store1)

        with self.assertRaises(RuntimeError):
            pipeline1.ingest_file(str(source_file), input_type="markdown", resume=True)

        store2 = FakeVectorStore()
        pipeline2 = self._make_pipeline(store2)
        result = pipeline2.ingest_file(str(source_file), input_type="markdown", resume=True)

        self.assertEqual(result["chunks"], 5)
        self.assertGreaterEqual(store2.upsert_calls, 2)

    def test_hybrid_retrieval_changes_order(self):
        store = FakeVectorStore()
        store.hybrid_search_results = [
            RetrievedChunk(id="2", text="specialterm specialterm", score=0.65, metadata={"source": "b"}),
            RetrievedChunk(id="1", text="alpha beta", score=0.90, metadata={"source": "a"}),
        ]
        pipeline = self._make_pipeline(store)

        result = pipeline.retrieve(query="specialterm", top_k=1)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "2")
        self.assertEqual(store.hybrid_search_calls, 1)

    def test_retrieval_uses_dedicated_reranker(self):
        previous_rerank_enabled = settings.rag.rerank_enabled
        settings.rag.rerank_enabled = True
        try:
            store = FakeVectorStore()
            store.hybrid_search_results = [
                RetrievedChunk(id="1", text="alpha", score=0.95, metadata={"source": "a"}),
                RetrievedChunk(id="2", text="beta", score=0.90, metadata={"source": "b"}),
                RetrievedChunk(id="3", text="gamma", score=0.85, metadata={"source": "c"}),
            ]
            reranker = FakeReranker()
            pipeline = self._make_pipeline(store, reranker=reranker)

            result = pipeline.retrieve(query="anything", top_k=2)

            self.assertEqual(reranker.calls, 1)
            self.assertEqual([item.id for item in result], ["3", "2"])
        finally:
            settings.rag.rerank_enabled = previous_rerank_enabled


if __name__ == "__main__":
    unittest.main()
