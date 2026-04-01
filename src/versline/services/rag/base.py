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

    @abstractmethod
    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievedChunk]:
        raise NotImplementedError


class BaseGenerator(ABC):
    @abstractmethod
    def generate(self, query: str, context_chunks: List[RetrievedChunk], **kwargs) -> str:
        raise NotImplementedError
