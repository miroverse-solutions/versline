from __future__ import annotations

from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from versline.services.rag.base import BaseVectorStore, Chunk, RetrievedChunk


class QdrantVectorStore(BaseVectorStore):
    def __init__(self, url: str, api_key: Optional[str] = None, distance: str = "cosine"):
        self.client = QdrantClient(url=url, api_key=api_key)
        self.distance = self._parse_distance(distance)

    def _parse_distance(self, distance: str) -> Distance:
        key = (distance or "cosine").lower()
        if key == "dot":
            return Distance.DOT
        if key == "euclid":
            return Distance.EUCLID
        return Distance.COSINE

    def ensure_collection(self, collection_name: str, vector_size: int) -> None:
        collections = self.client.get_collections().collections
        if any(c.name == collection_name for c in collections):
            return
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=self.distance),
        )

    def reset_collection(self, collection_name: str) -> None:
        collections = self.client.get_collections().collections
        if any(c.name == collection_name for c in collections):
            self.client.delete_collection(collection_name=collection_name)

    def upsert(self, collection_name: str, chunks: List[Chunk], vectors: List[List[float]]) -> None:
        points: List[PointStruct] = []
        for chunk, vector in zip(chunks, vectors):
            payload = {
                "text": chunk.text,
                "metadata": chunk.metadata,
            }
            points.append(PointStruct(id=chunk.id, vector=vector, payload=payload))

        if points:
            self.client.upsert(collection_name=collection_name, points=points)

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

        hits = self.client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=top_k,
            query_filter=query_filter,
        )

        return [
            RetrievedChunk(
                id=str(hit.id),
                text=str(hit.payload.get("text", "")),
                score=float(hit.score),
                metadata=dict(hit.payload.get("metadata", {})),
            )
            for hit in hits
        ]
