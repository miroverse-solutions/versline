from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from versline.config import settings
from versline.services.pricing import TokenTracker
from versline.services.rag.base import BaseChunker, BaseEmbedder, BaseGenerator, BaseReranker, Chunk, RetrievedChunk
from versline.services.rag.chunkers import SlidingWindowChunker
from versline.services.rag.embedders import FastEmbedSparseEmbedder, OpenAICompatibleEmbedder
from versline.services.rag.generators import PromptRAGGenerator
from versline.services.rag.mcp_client import MCPClientConfig, MCPContextClient
from versline.services.rag.preprocessors import DEFAULT_EXTENSION_TO_INPUT_TYPE, MarkdownPreprocessor
from versline.services.rag.rerankers import CohereReranker, JinaReranker, OpenAICompatibleReranker
from versline.services.rag.registry import PreprocessorRegistry, VectorStoreRegistry
from versline.services.rag.runtime import ProgressStateStore, RateLimiter, TokenRateLimiter
from versline.services.rag.vectorstores import QdrantVectorStore


class RAGPipeline:
    def __init__(
        self,
        chunker: Optional[BaseChunker] = None,
        embedder: Optional[BaseEmbedder] = None,
        sparse_embedder: Optional[Any] = None,
        reranker: Optional[BaseReranker] = None,
        mcp_client: Optional[Any] = None,
        generator: Optional[BaseGenerator] = None,
        preprocessor_registry: Optional[PreprocessorRegistry] = None,
        vector_store_registry: Optional[VectorStoreRegistry] = None,
        vector_backend: Optional[str] = None,
        collection_name: Optional[str] = None,
        qdrant_url: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
        qdrant_distance: str = "cosine",
        embedding_model: Optional[str] = None,
        generation_model: Optional[str] = None,
    ):
        self.tracker = TokenTracker()
        self.embedding_rate_limiter = RateLimiter(settings.rag.rate_limit_embedding_rpm)
        self.embedding_token_rate_limiter = TokenRateLimiter(settings.rag.rate_limit_embedding_tpm)
        self.generation_rate_limiter = RateLimiter(settings.rag.rate_limit_generation_rpm)
        self.generation_token_rate_limiter = TokenRateLimiter(settings.rag.rate_limit_generation_tpm)
        self.qdrant_rate_limiter = RateLimiter(settings.rag.rate_limit_qdrant_rpm)
        self.rerank_rate_limiter = RateLimiter(settings.rag.rate_limit_rerank_rpm)
        self.rerank_token_rate_limiter = TokenRateLimiter(settings.rag.rate_limit_rerank_tpm)

        self.chunker = chunker or SlidingWindowChunker(
            chunk_size=settings.rag.chunk_size,
            overlap=settings.rag.chunk_overlap,
        )
        self.embedder = embedder or OpenAICompatibleEmbedder(
            model=embedding_model or settings.rag.embedding_model,
            rate_limiter=self.embedding_rate_limiter,
            token_rate_limiter=self.embedding_token_rate_limiter,
            tracker=self.tracker,
        )
        self.sparse_embedder = sparse_embedder
        if self.sparse_embedder is None and settings.rag.hybrid_enabled:
            self.sparse_embedder = FastEmbedSparseEmbedder(settings.rag.sparse_embedding_model)
        self.generator = generator or PromptRAGGenerator(
            model=generation_model or settings.llm.model,
            prompt_file=settings.rag.generation_prompt_file,
            rate_limiter=self.generation_rate_limiter,
            token_rate_limiter=self.generation_token_rate_limiter,
            tracker=self.tracker,
        )
        self.reranker = reranker
        if self.reranker is None and settings.rag.rerank_enabled:
            provider = (settings.rag.rerank_provider or "cohere").lower()
            if provider == "cohere":
                self.reranker = CohereReranker(
                    model=settings.rag.rerank_model,
                    rate_limiter=self.rerank_rate_limiter,
                    token_rate_limiter=self.rerank_token_rate_limiter,
                )
            elif provider == "jina":
                self.reranker = JinaReranker(
                    model=settings.rag.rerank_model,
                    rate_limiter=self.rerank_rate_limiter,
                    token_rate_limiter=self.rerank_token_rate_limiter,
                )
            elif provider in {"openai", "openrouter", "avalai", "openaicompatible"}:
                self.reranker = OpenAICompatibleReranker(
                    model=settings.rag.rerank_model,
                    rate_limiter=self.rerank_rate_limiter,
                    token_rate_limiter=self.rerank_token_rate_limiter,
                    tracker=self.tracker,
                )
            else:
                logger.warning(f"Unsupported rerank provider: {provider}. Reranking disabled.")

        self.mcp_client = mcp_client
        if self.mcp_client is None and settings.rag.mcp_enabled:
            self.mcp_client = MCPContextClient(
                MCPClientConfig(
                    transport=settings.rag.mcp_transport,
                    tool_name=settings.rag.mcp_tool_name,
                    timeout_seconds=settings.rag.mcp_timeout_seconds,
                    max_context_chars=settings.rag.mcp_max_context_chars,
                    server_url=settings.rag.mcp_server_url,
                    server_command=settings.rag.mcp_server_command,
                    server_args=settings.rag.mcp_server_args,
                    proxy=settings.rag.mcp_proxy,
                )
            )

        self.preprocessors = preprocessor_registry or PreprocessorRegistry()
        self.preprocessors.register("markdown", MarkdownPreprocessor())

        self.vector_stores = vector_store_registry or VectorStoreRegistry()
        self.vector_backend = (vector_backend or settings.rag.vector_backend).lower()

        if self.vector_backend == "qdrant":
            self.vector_stores.register(
                "qdrant",
                QdrantVectorStore(
                    url=qdrant_url or settings.rag.qdrant_url,
                    api_key=qdrant_api_key or settings.rag.qdrant_api_key,
                    distance=qdrant_distance or settings.rag.qdrant_distance,
                    rate_limiter=self.qdrant_rate_limiter,
                ),
            )

        self.collection_name = collection_name or settings.rag.collection_name
        self._active_store = self.vector_stores.get(self.vector_backend)

    def register_preprocessor(self, input_type: str, preprocessor) -> None:
        self.preprocessors.register(input_type=input_type, preprocessor=preprocessor)

    def register_vector_store(self, backend_type: str, store) -> None:
        self.vector_stores.register(backend_type=backend_type, store=store)

    def _resolve_input_type(self, file_path: str, input_type: Optional[str] = None) -> str:
        if input_type:
            return input_type.lower()
        suffix = Path(file_path).suffix.lower()
        if suffix in DEFAULT_EXTENSION_TO_INPUT_TYPE:
            return DEFAULT_EXTENSION_TO_INPUT_TYPE[suffix]
        raise ValueError(
            f"Unsupported file extension '{suffix}'. Provide explicit input_type and matching preprocessor."
        )

    def _lexical_score(self, query: str, text: str) -> float:
        query_terms = [item for item in query.lower().split() if item]
        if not query_terms:
            return 0.0
        text_terms = text.lower().split()
        if not text_terms:
            return 0.0

        text_len = len(text_terms)
        score = 0.0
        for term in query_terms:
            tf = text_terms.count(term)
            if tf > 0:
                score += (tf / max(1, text_len)) * (1.0 + math.log(1.0 + tf))
        return score

    def _hybrid_rank(self, query: str, items: List[RetrievedChunk], top_k: int) -> List[RetrievedChunk]:
        if not items:
            return []

        dense_max = max((item.score for item in items), default=1.0) or 1.0
        lexical_scores = [self._lexical_score(query, item.text) for item in items]
        lexical_max = max(lexical_scores, default=1.0) or 1.0

        dense_weight = settings.rag.hybrid_dense_weight
        lexical_weight = settings.rag.hybrid_lexical_weight

        ranked: List[Tuple[float, RetrievedChunk]] = []
        for item, lexical in zip(items, lexical_scores):
            dense_component = float(item.score) / dense_max
            lexical_component = float(lexical) / lexical_max if lexical_max > 0 else 0.0
            hybrid_score = (dense_weight * dense_component) + (lexical_weight * lexical_component)
            ranked.append((hybrid_score, item))

        ranked.sort(key=lambda entry: entry[0], reverse=True)
        return [entry[1] for entry in ranked[:top_k]]

    def _iter_input_files(self, input_path: str, input_type: Optional[str]) -> List[Path]:
        path = Path(input_path)
        if path.is_file():
            return [path]

        if not path.is_dir():
            raise ValueError(f"Input path does not exist: {input_path}")

        allowed_ext = set(DEFAULT_EXTENSION_TO_INPUT_TYPE.keys())
        files = [
            child for child in sorted(path.rglob("*"))
            if child.is_file() and (input_type is not None or child.suffix.lower() in allowed_ext)
        ]
        if not files:
            raise ValueError("No supported files found in input directory")
        return files

    def _state_store(self, source_file: Path, collection_name: str) -> ProgressStateStore:
        signature_payload = {
            "source": str(source_file.resolve()),
            "collection": collection_name,
            "chunk_size": settings.rag.chunk_size,
            "chunk_overlap": settings.rag.chunk_overlap,
            "embedding_model": settings.rag.embedding_model,
        }
        raw = json.dumps(signature_payload, ensure_ascii=False, sort_keys=True)
        signature = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        state_dir = settings.rag.state_directory / source_file.stem
        return ProgressStateStore(state_file=state_dir / f"rag_ingest_{signature}.json")

    def ingest_path(
        self,
        input_path: str,
        input_type: Optional[str] = None,
        collection_name: Optional[str] = None,
        reset_collection: bool = False,
        resume: bool = True,
        force: bool = False,
        progress_callback=None,
    ) -> Dict[str, Any]:
        active_collection = collection_name or self.collection_name
        files = self._iter_input_files(input_path, input_type)

        total_chunks = 0
        total_docs = 0
        indexed_files = 0
        collection_reset_done = False

        for file_index, file_path in enumerate(files, start=1):
            resolved_input_type = self._resolve_input_type(str(file_path), input_type)
            preprocessor = self.preprocessors.get(resolved_input_type)

            documents = preprocessor.preprocess(str(file_path))
            chunks = self.chunker.chunk(documents)
            total_docs += len(documents)

            if not chunks:
                if progress_callback:
                    progress_callback(file_index, len(files), f"Skipping empty file: {file_path.name}")
                continue

            vectors_probe = self.embedder.embed_documents([chunks[0].text])
            if not vectors_probe:
                raise RuntimeError("Embedding model returned empty vectors")
            vector_size = len(vectors_probe[0])

            if reset_collection and not collection_reset_done:
                self._active_store.reset_collection(active_collection)
                collection_reset_done = True

            self._active_store.ensure_collection(active_collection, vector_size=vector_size)

            store = self._state_store(file_path, active_collection)
            state = store.load() if resume else {}
            if force:
                state = {}

            completed = int(state.get("completed_chunks", 0))
            batch_size = max(1, settings.rag.ingestion_batch_size)
            start_index = completed if resume else 0

            for start in range(start_index, len(chunks), batch_size):
                end = min(start + batch_size, len(chunks))
                batch_chunks = chunks[start:end]

                dense_vectors = self.embedder.embed_documents([item.text for item in batch_chunks])
                if (
                    settings.rag.hybrid_enabled
                    and self.sparse_embedder is not None
                    and hasattr(self._active_store, "upsert_hybrid")
                ):
                    sparse_vectors = self.sparse_embedder.embed_documents([item.text for item in batch_chunks])
                    self._active_store.upsert_hybrid(
                        active_collection,
                        chunks=batch_chunks,
                        dense_vectors=dense_vectors,
                        sparse_vectors=sparse_vectors,
                    )
                else:
                    self._active_store.upsert(active_collection, chunks=batch_chunks, vectors=dense_vectors)

                state["completed_chunks"] = end
                state["total_chunks"] = len(chunks)
                state["source"] = str(file_path)
                state["collection"] = active_collection
                store.save(state)

                if progress_callback:
                    progress_callback(
                        file_index - 1 + (end / max(1, len(chunks))),
                        len(files),
                        f"Indexing {file_path.name}: {end}/{len(chunks)} chunks",
                    )

            total_chunks += len(chunks)
            indexed_files += 1

        return {
            "collection": active_collection,
            "files": indexed_files,
            "documents": total_docs,
            "chunks": total_chunks,
        }

    def ingest_file(
        self,
        file_path: str,
        input_type: Optional[str] = None,
        collection_name: Optional[str] = None,
        reset_collection: bool = False,
        resume: bool = True,
        force: bool = False,
        progress_callback=None,
    ) -> Dict[str, Any]:
        return self.ingest_path(
            input_path=file_path,
            input_type=input_type,
            collection_name=collection_name,
            reset_collection=reset_collection,
            resume=resume,
            force=force,
            progress_callback=progress_callback,
        )

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        collection_name: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievedChunk]:
        active_collection = collection_name or self.collection_name
        query_vector = self.embedder.embed_query(query)
        fetch_k = max(top_k, int(settings.rag.retrieve_fetch_k or top_k))
        rerank_enabled = bool(settings.rag.rerank_enabled and self.reranker is not None)
        candidate_top_k = fetch_k if rerank_enabled else top_k

        if (
            settings.rag.hybrid_enabled
            and self.sparse_embedder is not None
            and hasattr(self._active_store, "search_hybrid")
        ):
            sparse_query = self.sparse_embedder.embed_query(query)
            hybrid_hits = self._active_store.search_hybrid(
                collection_name=active_collection,
                dense_query_vector=query_vector,
                sparse_query_vector=sparse_query,
                top_k=candidate_top_k,
                filters=filters,
                fetch_k=fetch_k,
            )
            if hybrid_hits:
                if rerank_enabled:
                    return self.reranker.rerank(query=query, items=hybrid_hits, top_k=top_k)
                return hybrid_hits[:top_k]

        dense_hits = self._active_store.search(
            collection_name=active_collection,
            query_vector=query_vector,
            top_k=fetch_k,
            filters=filters,
        )

        if rerank_enabled:
            return self.reranker.rerank(query=query, items=dense_hits, top_k=top_k)

        if not settings.rag.hybrid_enabled:
            return dense_hits[:top_k]

        return self._hybrid_rank(query=query, items=dense_hits, top_k=top_k)

    def generate(
        self,
        query: str,
        top_k: int = 5,
        collection_name: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context_chunks = self.retrieve(
            query=query,
            top_k=top_k,
            collection_name=collection_name,
            filters=filters,
        )
        mcp_context = ""
        if settings.rag.mcp_enabled and self.mcp_client is not None:
            try:
                mcp_context = self.mcp_client.fetch_context(
                    query=query,
                    top_k=top_k,
                    metadata={
                        "collection_name": collection_name or self.collection_name,
                    },
                )
            except Exception as error:
                logger.warning(f"MCP context fetch failed: {error}")

        answer = self.generator.generate(
            query=query,
            context_chunks=context_chunks,
            external_context=mcp_context,
        )
        return {
            "query": query,
            "answer": answer,
            "external_context_used": bool(mcp_context),
            "sources": [
                {
                    "id": item.id,
                    "score": item.score,
                    "metadata": item.metadata,
                    "text": item.text,
                }
                for item in context_chunks
            ],
        }
