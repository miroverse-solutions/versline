from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from versline.config import settings
from versline.services.rag.base import BaseChunker, BaseEmbedder, BaseGenerator, Chunk, RetrievedChunk
from versline.services.rag.chunkers import SlidingWindowChunker
from versline.services.rag.embedders import OpenAICompatibleEmbedder
from versline.services.rag.generators import PromptRAGGenerator
from versline.services.rag.preprocessors import DEFAULT_EXTENSION_TO_INPUT_TYPE, MarkdownPreprocessor
from versline.services.rag.registry import PreprocessorRegistry, VectorStoreRegistry
from versline.services.rag.vectorstores import QdrantVectorStore


class RAGPipeline:
    def __init__(
        self,
        chunker: Optional[BaseChunker] = None,
        embedder: Optional[BaseEmbedder] = None,
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
        self.chunker = chunker or SlidingWindowChunker(
            chunk_size=settings.rag.chunk_size,
            overlap=settings.rag.chunk_overlap,
        )
        self.embedder = embedder or OpenAICompatibleEmbedder(
            model=embedding_model or settings.rag.embedding_model
        )
        self.generator = generator or PromptRAGGenerator(
            model=generation_model or settings.llm.model,
            prompt_file=settings.rag.generation_prompt_file,
        )

        self.preprocessors = preprocessor_registry or PreprocessorRegistry()
        self.preprocessors.register("markdown", MarkdownPreprocessor())

        self.vector_stores = vector_store_registry or VectorStoreRegistry()
        self.vector_stores.register(
            "qdrant",
            QdrantVectorStore(
                url=qdrant_url or settings.rag.qdrant_url,
                api_key=qdrant_api_key or settings.rag.qdrant_api_key,
                distance=qdrant_distance or settings.rag.qdrant_distance,
            ),
        )

        self.vector_backend = (vector_backend or settings.rag.vector_backend).lower()
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

    def ingest_file(
        self,
        file_path: str,
        input_type: Optional[str] = None,
        collection_name: Optional[str] = None,
        reset_collection: bool = False,
    ) -> Dict[str, Any]:
        active_collection = collection_name or self.collection_name
        resolved_input_type = self._resolve_input_type(file_path, input_type)
        preprocessor = self.preprocessors.get(resolved_input_type)

        documents = preprocessor.preprocess(file_path)
        chunks = self.chunker.chunk(documents)
        if not chunks:
            return {
                "collection": active_collection,
                "documents": len(documents),
                "chunks": 0,
            }

        vectors = self.embedder.embed_documents([chunk.text for chunk in chunks])
        if not vectors:
            return {
                "collection": active_collection,
                "documents": len(documents),
                "chunks": len(chunks),
            }

        vector_size = len(vectors[0])

        if reset_collection:
            logger.info(f"Resetting collection: {active_collection}")
            self._active_store.reset_collection(active_collection)

        self._active_store.ensure_collection(active_collection, vector_size=vector_size)
        self._active_store.upsert(active_collection, chunks=chunks, vectors=vectors)

        return {
            "collection": active_collection,
            "documents": len(documents),
            "chunks": len(chunks),
            "vector_size": vector_size,
        }

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        collection_name: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievedChunk]:
        active_collection = collection_name or self.collection_name
        query_vector = self.embedder.embed_query(query)
        return self._active_store.search(
            collection_name=active_collection,
            query_vector=query_vector,
            top_k=top_k,
            filters=filters,
        )

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
        answer = self.generator.generate(query=query, context_chunks=context_chunks)
        return {
            "query": query,
            "answer": answer,
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
