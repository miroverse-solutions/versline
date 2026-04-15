from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Document:
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievedChunk:
    id: str
    text: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WebSearchResult:
    title: str
    url: str
    snippet: str
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class BasePreprocessor(ABC):
    @abstractmethod
    def preprocess(self, file_path: str, **kwargs) -> List[Document]:
        raise NotImplementedError


class BaseChunker(ABC):
    @abstractmethod
    def chunk(self, documents: List[Document], **kwargs) -> List[Chunk]:
        raise NotImplementedError


class BaseEmbedder(ABC):
    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        raise NotImplementedError


class BaseVectorStore(ABC):
    @abstractmethod
    def ensure_collection(self, collection_name: str, vector_size: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def reset_collection(self, collection_name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert(self, collection_name: str, chunks: List[Chunk], vectors: List[List[float]]) -> None:
        raise NotImplementedError

    def upsert_hybrid(
        self,
        collection_name: str,
        chunks: List[Chunk],
        dense_vectors: List[List[float]],
        sparse_vectors: List[Dict[str, List[float]]],
    ) -> None:
        self.upsert(collection_name=collection_name, chunks=chunks, vectors=dense_vectors)

    @abstractmethod
    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievedChunk]:
        raise NotImplementedError

    def search_hybrid(
        self,
        collection_name: str,
        dense_query_vector: List[float],
        sparse_query_vector: Dict[str, List[float]],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        fetch_k: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        return self.search(
            collection_name=collection_name,
            query_vector=dense_query_vector,
            top_k=top_k,
            filters=filters,
        )

    def get_by_ids(self, collection_name: str, ids: List[str]) -> List[RetrievedChunk]:
        raise NotImplementedError


class BaseGenerator(ABC):
    @abstractmethod
    def generate(self, query: str, context_chunks: List[RetrievedChunk], **kwargs) -> str:
        raise NotImplementedError


class BaseReranker(ABC):
    @abstractmethod
    def rerank(self, query: str, items: List[RetrievedChunk], top_k: int) -> List[RetrievedChunk]:
        raise NotImplementedError


class BaseWebSearcher(ABC):
    @abstractmethod
    def search(self, query: str, top_k: int = 5, **kwargs) -> List[WebSearchResult]:
        raise NotImplementedError
