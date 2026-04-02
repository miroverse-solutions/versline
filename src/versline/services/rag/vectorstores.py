from __future__ import annotations

from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchValue,
    PointStruct,
    Prefetch,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from versline.config import settings
from versline.services.rag.base import BaseVectorStore, Chunk, RetrievedChunk
from versline.services.rag.runtime import RateLimiter, retry_call, scoped_proxy


class QdrantVectorStore(BaseVectorStore):
    DENSE_VECTOR_NAME = "dense"
    SPARSE_VECTOR_NAME = "sparse"

    def __init__(
        self,
        url: str,
        api_key: Optional[str] = None,
        distance: str = "cosine",
        proxy: Optional[str] = None,
        rate_limiter: Optional[RateLimiter] = None,
        timeout_seconds: Optional[float] = None,
    ):
        self.proxy = proxy if proxy is not None else settings.rag.qdrant_proxy
        self.distance = self._parse_distance(distance)
        self.rate_limiter = rate_limiter or RateLimiter(settings.rag.rate_limit_qdrant_rpm)
        self.timeout_seconds = float(timeout_seconds or settings.rag.qdrant_timeout_seconds)

        with scoped_proxy(self.proxy):
            self.client = QdrantClient(url=url, api_key=api_key, timeout=self.timeout_seconds)

    def _parse_distance(self, distance: str) -> Distance:
        key = (distance or "cosine").lower()
        if key == "dot":
            return Distance.DOT
        if key == "euclid":
            return Distance.EUCLID
        return Distance.COSINE

    def ensure_collection(self, collection_name: str, vector_size: int) -> None:
        def operation():
            self.rate_limiter.wait()
            with scoped_proxy(self.proxy):
                collections = self.client.get_collections().collections
                if any(c.name == collection_name for c in collections):
                    return
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config={
                        self.DENSE_VECTOR_NAME: VectorParams(size=vector_size, distance=self.distance),
                    },
                    sparse_vectors_config={
                        self.SPARSE_VECTOR_NAME: SparseVectorParams(),
                    },
                )

        retry_call(
            operation,
            max_retries=settings.rag.retry_max_retries,
            base_delay_seconds=settings.rag.retry_base_delay_seconds,
            max_delay_seconds=settings.rag.retry_max_delay_seconds,
            operation_name="qdrant_ensure_collection",
        )

    def reset_collection(self, collection_name: str) -> None:
        def operation():
            self.rate_limiter.wait()
            with scoped_proxy(self.proxy):
                collections = self.client.get_collections().collections
                if any(c.name == collection_name for c in collections):
                    self.client.delete_collection(collection_name=collection_name)

        retry_call(
            operation,
            max_retries=settings.rag.retry_max_retries,
            base_delay_seconds=settings.rag.retry_base_delay_seconds,
            max_delay_seconds=settings.rag.retry_max_delay_seconds,
            operation_name="qdrant_reset_collection",
        )

    def upsert(self, collection_name: str, chunks: List[Chunk], vectors: List[List[float]]) -> None:
        points: List[PointStruct] = []
        for chunk, vector in zip(chunks, vectors):
            payload = {
                "text": chunk.text,
                "metadata": chunk.metadata,
            }
            points.append(
                PointStruct(
                    id=chunk.id,
                    vector={self.DENSE_VECTOR_NAME: vector},
                    payload=payload,
                )
            )

        if points:
            def operation():
                self.rate_limiter.wait()
                with scoped_proxy(self.proxy):
                    self.client.upsert(collection_name=collection_name, points=points)

            retry_call(
                operation,
                max_retries=settings.rag.retry_max_retries,
                base_delay_seconds=settings.rag.retry_base_delay_seconds,
                max_delay_seconds=settings.rag.retry_max_delay_seconds,
                operation_name="qdrant_upsert",
            )

    def upsert_hybrid(
        self,
        collection_name: str,
        chunks: List[Chunk],
        dense_vectors: List[List[float]],
        sparse_vectors: List[Dict[str, List[float]]],
    ) -> None:
        points: List[PointStruct] = []
        for chunk, dense, sparse in zip(chunks, dense_vectors, sparse_vectors):
            payload = {
                "text": chunk.text,
                "metadata": chunk.metadata,
            }
            sparse_vector = SparseVector(
                indices=[int(index) for index in sparse.get("indices", [])],
                values=[float(value) for value in sparse.get("values", [])],
            )
            points.append(
                PointStruct(
                    id=chunk.id,
                    vector={
                        self.DENSE_VECTOR_NAME: dense,
                        self.SPARSE_VECTOR_NAME: sparse_vector,
                    },
                    payload=payload,
                )
            )

        if points:
            def operation():
                self.rate_limiter.wait()
                with scoped_proxy(self.proxy):
                    self.client.upsert(collection_name=collection_name, points=points)

            retry_call(
                operation,
                max_retries=settings.rag.retry_max_retries,
                base_delay_seconds=settings.rag.retry_base_delay_seconds,
                max_delay_seconds=settings.rag.retry_max_delay_seconds,
                operation_name="qdrant_upsert_hybrid",
            )

    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievedChunk]:
        query_filter = None
        if filters:
            conditions = [
                FieldCondition(key=f"metadata.{key}", match=MatchValue(value=value))
                for key, value in filters.items()
            ]
            query_filter = Filter(must=conditions)

        def operation():
            self.rate_limiter.wait()
            with scoped_proxy(self.proxy):
                return self.client.query_points(
                    collection_name=collection_name,
                    query=query_vector,
                    using=self.DENSE_VECTOR_NAME,
                    limit=top_k,
                    query_filter=query_filter,
                )

        hits = retry_call(
            operation,
            max_retries=settings.rag.retry_max_retries,
            base_delay_seconds=settings.rag.retry_base_delay_seconds,
            max_delay_seconds=settings.rag.retry_max_delay_seconds,
            operation_name="qdrant_search",
        )

        points = getattr(hits, "points", [])

        return [
            RetrievedChunk(
                id=str(hit.id),
                text=str(hit.payload.get("text", "")),
                score=float(hit.score),
                metadata=dict(hit.payload.get("metadata", {})),
            )
            for hit in points
        ]

    def search_hybrid(
        self,
        collection_name: str,
        dense_query_vector: List[float],
        sparse_query_vector: Dict[str, List[float]],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        fetch_k: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        query_filter = None
        if filters:
            conditions = [
                FieldCondition(key=f"metadata.{key}", match=MatchValue(value=value))
                for key, value in filters.items()
            ]
            query_filter = Filter(must=conditions)

        candidate_limit = max(top_k, int(fetch_k or top_k))

        sparse_vector = SparseVector(
            indices=[int(index) for index in sparse_query_vector.get("indices", [])],
            values=[float(value) for value in sparse_query_vector.get("values", [])],
        )

        prefetch = [
            Prefetch(
                query=dense_query_vector,
                using=self.DENSE_VECTOR_NAME,
                filter=query_filter,
                limit=candidate_limit,
            ),
            Prefetch(
                query=sparse_vector,
                using=self.SPARSE_VECTOR_NAME,
                filter=query_filter,
                limit=candidate_limit,
            ),
        ]

        def operation():
            self.rate_limiter.wait()
            with scoped_proxy(self.proxy):
                return self.client.query_points(
                    collection_name=collection_name,
                    prefetch=prefetch,
                    query=FusionQuery(fusion=Fusion.RRF),
                    limit=top_k,
                    with_payload=True,
                    with_vectors=False,
                )

        hits = retry_call(
            operation,
            max_retries=settings.rag.retry_max_retries,
            base_delay_seconds=settings.rag.retry_base_delay_seconds,
            max_delay_seconds=settings.rag.retry_max_delay_seconds,
            operation_name="qdrant_search_hybrid",
        )

        points = getattr(hits, "points", [])
        return [
            RetrievedChunk(
                id=str(hit.id),
                text=str(hit.payload.get("text", "")),
                score=float(hit.score),
                metadata=dict(hit.payload.get("metadata", {})),
            )
            for hit in points
        ]
