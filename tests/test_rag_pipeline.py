import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

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


class OOMOnLargeBatchEmbedder(BaseEmbedder):
    def __init__(self, fail_above: int = 2):
        self.fail_above = fail_above
        self.calls = 0
        self.failures = 0

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        self.calls += 1
        if len(texts) > self.fail_above:
            self.failures += 1
            raise RuntimeError("CUDA out of memory")
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
        self.vector_size = None
        self.upsert_calls = 0
        self.upsert_hybrid_calls = 0
        self.search_results: List[RetrievedChunk] = []
        self.hybrid_search_results: List[RetrievedChunk] = []
        self.hybrid_search_calls = 0
        self.fail_once_on_upsert_call = fail_once_on_upsert_call
        self.failed = False
        self.points: Dict[str, RetrievedChunk] = {}

    def ensure_collection(self, collection_name: str, vector_size: int) -> None:
        self.collection = collection_name
        self.vector_size = vector_size

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
        for chunk in chunks:
            self.points[str(chunk.id)] = RetrievedChunk(
                id=str(chunk.id),
                text=chunk.text,
                score=0.0,
                metadata=dict(chunk.metadata),
            )

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

    def get_by_ids(self, collection_name: str, ids: List[str]) -> List[RetrievedChunk]:
        return [self.points[item_id] for item_id in ids if item_id in self.points]


class TestRAGPipeline(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

        self.prev_state_dir = settings.rag.state_directory
        self.prev_batch = settings.rag.ingestion_batch_size
        self.prev_hybrid = settings.rag.hybrid_enabled
        self.prev_fetch = settings.rag.retrieve_fetch_k
        self.prev_vector_size = settings.rag.vector_size
        self.prev_parent_child_enabled = settings.rag.parent_child_enabled
        self.prev_parent_chunk_size = settings.rag.parent_chunk_size
        self.prev_parent_chunk_overlap = settings.rag.parent_chunk_overlap
        self.prev_parent_child_fetch_k = settings.rag.parent_child_fetch_k
        self.prev_rerank_enabled = settings.rag.rerank_enabled

        settings.rag.state_directory = self.base_path / "state"
        settings.rag.ingestion_batch_size = 2
        settings.rag.hybrid_enabled = True
        settings.rag.retrieve_fetch_k = 10
        settings.rag.vector_size = None
        settings.rag.parent_child_enabled = False
        settings.rag.parent_chunk_size = 2400
        settings.rag.parent_chunk_overlap = 200
        settings.rag.parent_child_fetch_k = 12
        settings.rag.rerank_enabled = False

    def tearDown(self):
        settings.rag.state_directory = self.prev_state_dir
        settings.rag.ingestion_batch_size = self.prev_batch
        settings.rag.hybrid_enabled = self.prev_hybrid
        settings.rag.retrieve_fetch_k = self.prev_fetch
        settings.rag.vector_size = self.prev_vector_size
        settings.rag.parent_child_enabled = self.prev_parent_child_enabled
        settings.rag.parent_chunk_size = self.prev_parent_chunk_size
        settings.rag.parent_chunk_overlap = self.prev_parent_chunk_overlap
        settings.rag.parent_child_fetch_k = self.prev_parent_child_fetch_k
        settings.rag.rerank_enabled = self.prev_rerank_enabled
        self.temp_dir.cleanup()

    def _make_pipeline(self, store: FakeVectorStore, reranker=None, embedder: BaseEmbedder | None = None) -> RAGPipeline:
        preprocessors = PreprocessorRegistry()
        preprocessors.register("markdown", FakePreprocessor())

        stores = VectorStoreRegistry()
        stores.register("fake", store)

        return RAGPipeline(
            chunker=FakeChunker(),
            embedder=embedder or FakeEmbedder(),
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

    def test_ingest_respects_configured_vector_size(self):
        source_file = self.base_path / "vector_size.md"
        source_file.write_text("line1\nline2", encoding="utf-8")

        store = FakeVectorStore()
        pipeline = self._make_pipeline(store)
        settings.rag.vector_size = 2

        result = pipeline.ingest_file(str(source_file), input_type="markdown")

        self.assertEqual(result["chunks"], 2)
        self.assertEqual(store.vector_size, 2)

    def test_ingest_raises_on_vector_size_mismatch(self):
        source_file = self.base_path / "vector_size_mismatch.md"
        source_file.write_text("line1", encoding="utf-8")

        store = FakeVectorStore()
        pipeline = self._make_pipeline(store)
        settings.rag.vector_size = 1536

        with self.assertRaises(ValueError):
            pipeline.ingest_file(str(source_file), input_type="markdown")

    def test_ingest_adapts_batch_size_after_memory_pressure(self):
        source_file = self.base_path / "adaptive_oom.md"
        source_file.write_text("a\nb\nc\nd\ne", encoding="utf-8")

        store = FakeVectorStore()
        oom_embedder = OOMOnLargeBatchEmbedder(fail_above=2)
        pipeline = self._make_pipeline(store, embedder=oom_embedder)

        settings.rag.ingestion_batch_size = 4
        result = pipeline.ingest_file(str(source_file), input_type="markdown")

        self.assertEqual(result["chunks"], 5)
        self.assertGreaterEqual(oom_embedder.failures, 1)
        self.assertGreaterEqual(store.upsert_calls, 2)

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

    def test_parent_child_ingest_indexes_parent_and_child_chunks(self):
        previous_parent_chunk_size = settings.rag.parent_chunk_size
        previous_parent_chunk_overlap = settings.rag.parent_chunk_overlap
        previous_chunk_size = settings.rag.chunk_size
        previous_chunk_overlap = settings.rag.chunk_overlap
        previous_parent_child_enabled = settings.rag.parent_child_enabled
        settings.rag.parent_child_enabled = True
        settings.rag.parent_chunk_size = 20
        settings.rag.parent_chunk_overlap = 4
        settings.rag.chunk_size = 10
        settings.rag.chunk_overlap = 2
        try:
            source_file = self.base_path / "parent_child_ingest.md"
            source_file.write_text("alpha beta gamma delta epsilon zeta eta theta", encoding="utf-8")

            preprocessors = PreprocessorRegistry()
            preprocessors.register("markdown", FakePreprocessor())

            stores = VectorStoreRegistry()
            store = FakeVectorStore()
            stores.register("fake", store)
            pipeline = RAGPipeline(
                embedder=FakeEmbedder(),
                sparse_embedder=FakeSparseEmbedder(),
                generator=FakeGenerator(),
                preprocessor_registry=preprocessors,
                vector_store_registry=stores,
                vector_backend="fake",
                collection_name="test_collection",
            )
            result = pipeline.ingest_file(str(source_file), input_type="markdown")

            parent_count = sum(1 for point in store.points.values() if point.metadata.get("chunk_level") == "parent")
            child_count = sum(1 for point in store.points.values() if point.metadata.get("chunk_level") == "child")

            self.assertGreater(parent_count, 0)
            self.assertGreater(child_count, 0)
            self.assertEqual(result["parent_chunks"], parent_count)
            self.assertEqual(result["child_chunks"], child_count)
        finally:
            settings.rag.parent_chunk_size = previous_parent_chunk_size
            settings.rag.parent_chunk_overlap = previous_parent_chunk_overlap
            settings.rag.chunk_size = previous_chunk_size
            settings.rag.chunk_overlap = previous_chunk_overlap
            settings.rag.parent_child_enabled = previous_parent_child_enabled

    def test_parent_child_retrieve_expands_to_parent_chunks(self):
        previous_parent_child_enabled = settings.rag.parent_child_enabled
        settings.rag.parent_child_enabled = True
        try:
            store = FakeVectorStore()
            pipeline = self._make_pipeline(store)

            parent_chunk = Chunk(
                id="parent-1",
                text="parent text with broad context",
                metadata={"source": "a.md", "chunk_level": "parent"},
            )
            child_chunk = RetrievedChunk(
                id="child-1",
                text="narrow child context",
                score=0.9,
                metadata={"source": "a.md", "chunk_level": "child", "parent_id": "parent-1"},
            )
            store.upsert("test_collection", [parent_chunk], [[1.0, 1.0]])
            store.hybrid_search_results = [child_chunk]

            result = pipeline.retrieve(query="narrow", top_k=1)

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].id, "parent-1")
            self.assertEqual(result[0].metadata.get("chunk_level"), "parent")
            self.assertTrue(result[0].metadata.get("matched_children"))
        finally:
            settings.rag.parent_child_enabled = previous_parent_child_enabled

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

    def test_preflight_normalizes_empty_qdrant_proxy(self):
        class DummyResponse:
            status_code = 200

        class DummyClient:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def get(self, *args, **kwargs):
                return DummyResponse()

        previous_proxy = settings.rag.qdrant_proxy
        previous_url = settings.rag.qdrant_url
        settings.rag.qdrant_proxy = ""
        settings.rag.qdrant_url = "https://example.com"

        try:
            with patch("versline.services.rag.pipeline.httpx.Client", side_effect=DummyClient) as client_mock:
                pipeline = self._make_pipeline(FakeVectorStore())
                result = pipeline._validate_initial_configuration(
                    check_network=True,
                    vector_backend="qdrant",
                    require_llm_api_keys=False,
                    require_web_api_keys=False,
                    timeout_seconds=1.0,
                )

                self.assertTrue(result["ok"])
                _, kwargs = client_mock.call_args
                self.assertIsNone(kwargs.get("proxy"))
        finally:
            settings.rag.qdrant_proxy = previous_proxy
            settings.rag.qdrant_url = previous_url

    def test_sentence_transformers_provider_aliases(self):
        previous_provider = settings.rag.embedding_provider
        previous_model = settings.rag.embedding_model

        stores = VectorStoreRegistry()
        stores.register("fake", FakeVectorStore())

        class DummySTEmbedder:
            def __init__(self, *args, **kwargs):
                pass

        try:
            for provider_value in ["sentence-transformers", "sentence_transformers", "sentencetransformers", "sentence-transformer", "sentence"]:
                settings.rag.embedding_provider = provider_value
                settings.rag.embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
                with patch("versline.services.rag.pipeline.SentenceTransformersDenseEmbedder", DummySTEmbedder):
                    pipeline = RAGPipeline(
                        embedder=None,
                        sparse_embedder=FakeSparseEmbedder(),
                        generator=FakeGenerator(),
                        vector_store_registry=stores,
                        vector_backend="fake",
                        preflight=False,
                    )
                    self.assertIsInstance(pipeline.embedder, DummySTEmbedder)
        finally:
            settings.rag.embedding_provider = previous_provider
            settings.rag.embedding_model = previous_model

    def test_local_rerank_with_model_path_uses_sentence_transformers_reranker(self):
        previous_rerank_enabled = settings.rag.rerank_enabled
        previous_rerank_provider = settings.rag.rerank_provider
        previous_rerank_model_path = settings.rag.rerank_model_path

        stores = VectorStoreRegistry()
        stores.register("fake", FakeVectorStore())

        class DummySTReranker:
            def __init__(self, *args, **kwargs):
                pass

            def rerank(self, query, items, top_k):
                return items[:top_k]

        settings.rag.rerank_enabled = True
        settings.rag.rerank_provider = "local"
        settings.rag.rerank_model_path = "/models/bge-reranker-v2-m3"
        try:
            with patch("versline.services.rag.pipeline.SentenceTransformersReranker", DummySTReranker):
                pipeline = RAGPipeline(
                    embedder=FakeEmbedder(),
                    sparse_embedder=FakeSparseEmbedder(),
                    generator=FakeGenerator(),
                    vector_store_registry=stores,
                    vector_backend="fake",
                    preflight=False,
                )
                self.assertIsInstance(pipeline.reranker, DummySTReranker)
        finally:
            settings.rag.rerank_enabled = previous_rerank_enabled
            settings.rag.rerank_provider = previous_rerank_provider
            settings.rag.rerank_model_path = previous_rerank_model_path

    def test_openvino_embedding_backend_does_not_override_openai_provider(self):
        previous_provider = settings.rag.embedding_provider
        previous_backend = settings.rag.embedding_inference_backend

        stores = VectorStoreRegistry()
        stores.register("fake", FakeVectorStore())

        class DummyOpenAIEmbedder:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs

            def embed_documents(self, texts):
                return [[1.0] for _ in texts]

            def embed_query(self, text):
                return [1.0]

        settings.rag.embedding_provider = "openai"
        settings.rag.embedding_inference_backend = "openvino"
        try:
            with patch("versline.services.rag.pipeline.OpenAICompatibleEmbedder", DummyOpenAIEmbedder):
                pipeline = RAGPipeline(
                    sparse_embedder=FakeSparseEmbedder(),
                    generator=FakeGenerator(),
                    vector_store_registry=stores,
                    vector_backend="fake",
                    preflight=False,
                )
                self.assertIsInstance(pipeline.embedder, DummyOpenAIEmbedder)
        finally:
            settings.rag.embedding_provider = previous_provider
            settings.rag.embedding_inference_backend = previous_backend

    def test_fastembed_openvino_backend_passes_onnx_providers(self):
        previous_provider = settings.rag.embedding_provider
        previous_backend = settings.rag.embedding_inference_backend
        previous_providers = settings.rag.embedding_onnx_providers
        previous_device = settings.rag.embedding_device
        previous_ov_cache = settings.rag.openvino_cache_dir

        stores = VectorStoreRegistry()
        stores.register("fake", FakeVectorStore())

        class DummyFastEmbedder:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs

            def embed_documents(self, texts):
                return [[1.0] for _ in texts]

            def embed_query(self, text):
                return [1.0]

        settings.rag.embedding_provider = "fastembed"
        settings.rag.embedding_inference_backend = "openvino"
        settings.rag.embedding_onnx_providers = None
        settings.rag.embedding_device = "cuda"
        settings.rag.openvino_cache_dir = "/tmp/ov_cache"
        try:
            with patch("versline.services.rag.pipeline.FastEmbedDenseEmbedder", DummyFastEmbedder):
                pipeline = RAGPipeline(
                    sparse_embedder=FakeSparseEmbedder(),
                    generator=FakeGenerator(),
                    vector_store_registry=stores,
                    vector_backend="fake",
                    preflight=False,
                )
                self.assertIsInstance(pipeline.embedder, DummyFastEmbedder)
                self.assertEqual(
                    pipeline.embedder.kwargs.get("providers"),
                    [("OpenVINOExecutionProvider", {"device_type": "GPU", "cache_dir": "/tmp/ov_cache"}), "CPUExecutionProvider"],
                )
        finally:
            settings.rag.embedding_provider = previous_provider
            settings.rag.embedding_inference_backend = previous_backend
            settings.rag.embedding_onnx_providers = previous_providers
            settings.rag.embedding_device = previous_device
            settings.rag.openvino_cache_dir = previous_ov_cache

    def test_sparse_provider_sentence_alias_uses_sentence_sparse_backend(self):
        previous_hybrid = settings.rag.hybrid_enabled
        previous_sparse_provider = settings.rag.sparse_embedding_provider

        stores = VectorStoreRegistry()
        stores.register("fake", FakeVectorStore())

        class DummySentenceSparse:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs

            def embed_documents(self, texts):
                return [{"indices": [1], "values": [0.1]} for _ in texts]

            def embed_query(self, text):
                return {"indices": [1], "values": [0.1]}

        settings.rag.hybrid_enabled = True
        settings.rag.sparse_embedding_provider = "sentence-transformers"
        try:
            with patch("versline.services.rag.pipeline.SentenceTransformersSparseEmbedder", DummySentenceSparse):
                pipeline = RAGPipeline(
                    embedder=FakeEmbedder(),
                    generator=FakeGenerator(),
                    vector_store_registry=stores,
                    vector_backend="fake",
                    preflight=False,
                )
                self.assertIsInstance(pipeline.sparse_embedder, DummySentenceSparse)
        finally:
            settings.rag.hybrid_enabled = previous_hybrid
            settings.rag.sparse_embedding_provider = previous_sparse_provider

    def test_openvino_rerank_backend_does_not_override_cohere_provider(self):
        previous_rerank_enabled = settings.rag.rerank_enabled
        previous_rerank_provider = settings.rag.rerank_provider
        previous_rerank_backend = settings.rag.rerank_inference_backend

        stores = VectorStoreRegistry()
        stores.register("fake", FakeVectorStore())

        class DummyCohereReranker:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs

            def rerank(self, query, items, top_k):
                return items[:top_k]

        settings.rag.rerank_enabled = True
        settings.rag.rerank_provider = "cohere"
        settings.rag.rerank_inference_backend = "openvino"
        try:
            with patch("versline.services.rag.pipeline.CohereReranker", DummyCohereReranker):
                pipeline = RAGPipeline(
                    embedder=FakeEmbedder(),
                    sparse_embedder=FakeSparseEmbedder(),
                    generator=FakeGenerator(),
                    vector_store_registry=stores,
                    vector_backend="fake",
                    preflight=False,
                )
                self.assertIsInstance(pipeline.reranker, DummyCohereReranker)
        finally:
            settings.rag.rerank_enabled = previous_rerank_enabled
            settings.rag.rerank_provider = previous_rerank_provider
            settings.rag.rerank_inference_backend = previous_rerank_backend

    def test_openvino_rerank_backend_applies_with_local_model_files(self):
        previous_rerank_enabled = settings.rag.rerank_enabled
        previous_rerank_provider = settings.rag.rerank_provider
        previous_rerank_backend = settings.rag.rerank_inference_backend
        previous_rerank_model_path = settings.rag.rerank_model_path

        stores = VectorStoreRegistry()
        stores.register("fake", FakeVectorStore())

        class DummySTReranker:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs

            def rerank(self, query, items, top_k):
                return items[:top_k]

        settings.rag.rerank_enabled = True
        settings.rag.rerank_provider = "local"
        settings.rag.rerank_inference_backend = "openvino"
        settings.rag.rerank_model_path = "/models/bge-reranker-v2-m3"
        try:
            with patch("versline.services.rag.pipeline.SentenceTransformersReranker", DummySTReranker):
                pipeline = RAGPipeline(
                    embedder=FakeEmbedder(),
                    sparse_embedder=FakeSparseEmbedder(),
                    generator=FakeGenerator(),
                    vector_store_registry=stores,
                    vector_backend="fake",
                    preflight=False,
                )
                self.assertIsInstance(pipeline.reranker, DummySTReranker)
                self.assertEqual(pipeline.reranker.kwargs.get("inference_backend"), "openvino")
        finally:
            settings.rag.rerank_enabled = previous_rerank_enabled
            settings.rag.rerank_provider = previous_rerank_provider
            settings.rag.rerank_inference_backend = previous_rerank_backend
            settings.rag.rerank_model_path = previous_rerank_model_path

    def test_rerank_provider_flagembedding_maps_to_sentence_transformers(self):
        previous_rerank_enabled = settings.rag.rerank_enabled
        previous_rerank_provider = settings.rag.rerank_provider

        stores = VectorStoreRegistry()
        stores.register("fake", FakeVectorStore())

        class DummySTReranker:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs

            def rerank(self, query, items, top_k):
                return items[:top_k]

        settings.rag.rerank_enabled = True
        settings.rag.rerank_provider = "flagembedding"
        try:
            with patch("versline.services.rag.pipeline.SentenceTransformersReranker", DummySTReranker):
                pipeline = RAGPipeline(
                    embedder=FakeEmbedder(),
                    sparse_embedder=FakeSparseEmbedder(),
                    generator=FakeGenerator(),
                    vector_store_registry=stores,
                    vector_backend="fake",
                    preflight=False,
                )
                self.assertIsInstance(pipeline.reranker, DummySTReranker)
        finally:
            settings.rag.rerank_enabled = previous_rerank_enabled
            settings.rag.rerank_provider = previous_rerank_provider

    def test_fastembed_rerank_openvino_backend_passes_onnx_providers(self):
        previous_rerank_enabled = settings.rag.rerank_enabled
        previous_rerank_provider = settings.rag.rerank_provider
        previous_rerank_backend = settings.rag.rerank_inference_backend
        previous_rerank_onnx = settings.rag.rerank_onnx_providers
        previous_rerank_device = settings.rag.rerank_device
        previous_ov_cache = settings.rag.openvino_cache_dir

        stores = VectorStoreRegistry()
        stores.register("fake", FakeVectorStore())

        class DummyFastEmbedReranker:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs

            def rerank(self, query, items, top_k):
                return items[:top_k]

        settings.rag.rerank_enabled = True
        settings.rag.rerank_provider = "fastembed"
        settings.rag.rerank_inference_backend = "openvino"
        settings.rag.rerank_onnx_providers = None
        settings.rag.rerank_device = "gpu"
        settings.rag.openvino_cache_dir = "/tmp/ov_rerank_cache"
        try:
            with patch("versline.services.rag.pipeline.FastEmbedReranker", DummyFastEmbedReranker):
                pipeline = RAGPipeline(
                    embedder=FakeEmbedder(),
                    sparse_embedder=FakeSparseEmbedder(),
                    generator=FakeGenerator(),
                    vector_store_registry=stores,
                    vector_backend="fake",
                    preflight=False,
                )
                self.assertIsInstance(pipeline.reranker, DummyFastEmbedReranker)
                self.assertEqual(
                    pipeline.reranker.kwargs.get("providers"),
                    [("OpenVINOExecutionProvider", {"device_type": "GPU", "cache_dir": "/tmp/ov_rerank_cache"}), "CPUExecutionProvider"],
                )
        finally:
            settings.rag.rerank_enabled = previous_rerank_enabled
            settings.rag.rerank_provider = previous_rerank_provider
            settings.rag.rerank_inference_backend = previous_rerank_backend
            settings.rag.rerank_onnx_providers = previous_rerank_onnx
            settings.rag.rerank_device = previous_rerank_device
            settings.rag.openvino_cache_dir = previous_ov_cache


if __name__ == "__main__":
    unittest.main()
