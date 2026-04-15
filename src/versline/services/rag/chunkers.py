from __future__ import annotations

import uuid
from typing import List, Optional, Tuple

from versline.services.rag.base import BaseChunker, Chunk, Document


class SlidingWindowChunker(BaseChunker):
    def __init__(self, chunk_size: int = 1200, overlap: int = 200):
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if overlap < 0:
            raise ValueError("overlap must be >= 0")
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, documents: List[Document], **kwargs) -> List[Chunk]:
        chunks: List[Chunk] = []
        for doc_index, doc in enumerate(documents):
            text = doc.text.strip()
            if not text:
                continue

            start = 0
            part_index = 0
            while start < len(text):
                end = min(start + self.chunk_size, len(text))
                chunk_text = text[start:end].strip()
                if chunk_text:
                    source = str(doc.metadata.get("source", "unknown"))
                    stable_key = f"{source}:{doc_index}:{part_index}:{chunk_text[:50]}"
                    chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, stable_key))
                    chunk_meta = {
                        **doc.metadata,
                        "doc_index": doc_index,
                        "chunk_index": part_index,
                        "char_start": start,
                        "char_end": end,
                    }
                    chunks.append(Chunk(id=chunk_id, text=chunk_text, metadata=chunk_meta))

                if end == len(text):
                    break

                start = max(0, end - self.overlap)
                part_index += 1

        return chunks


def _split_text_with_overlap(
    text: str,
    chunk_size: int,
    overlap: int,
    delimiters: Optional[List[str]] = None,
) -> List[Tuple[int, int, str]]:
    normalized_delimiters = [item for item in (delimiters or []) if item]

    def _find_boundary_end(start: int, candidate_end: int) -> int:
        if not normalized_delimiters:
            return candidate_end
        best_end = candidate_end
        best_index = -1
        for delimiter in normalized_delimiters:
            index = text.rfind(delimiter, start + 1, candidate_end)
            if index > best_index:
                best_index = index
                best_end = index + len(delimiter)
        if best_end <= start:
            return candidate_end
        return best_end

    slices: List[Tuple[int, int, str]] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        end = _find_boundary_end(start, end)
        chunk_text = text[start:end].strip()
        if chunk_text:
            slices.append((start, end, chunk_text))
        if end == len(text):
            break
        start = max(0, end - overlap)
    return slices


class HierarchicalChunker(BaseChunker):
    def __init__(
        self,
        parent_chunk_size: int = 2400,
        parent_overlap: int = 200,
        child_chunk_size: int = 1200,
        child_overlap: int = 200,
        parent_delimiters: Optional[List[str]] = None,
        child_delimiters: Optional[List[str]] = None,
        paragraph_mode: bool = False,
    ):
        if parent_chunk_size <= 0:
            raise ValueError("parent_chunk_size must be > 0")
        if child_chunk_size <= 0:
            raise ValueError("child_chunk_size must be > 0")
        if parent_overlap < 0:
            raise ValueError("parent_overlap must be >= 0")
        if child_overlap < 0:
            raise ValueError("child_overlap must be >= 0")
        if parent_overlap >= parent_chunk_size:
            raise ValueError("parent_overlap must be smaller than parent_chunk_size")
        if child_overlap >= child_chunk_size:
            raise ValueError("child_overlap must be smaller than child_chunk_size")
        self.parent_chunk_size = parent_chunk_size
        self.parent_overlap = parent_overlap
        self.child_chunk_size = child_chunk_size
        self.child_overlap = child_overlap
        if paragraph_mode:
            paragraph_delimiters = ["\n\n", "\r\n\r\n"]
            self.parent_delimiters = parent_delimiters or paragraph_delimiters
            self.child_delimiters = child_delimiters or paragraph_delimiters
        else:
            self.parent_delimiters = parent_delimiters or []
            self.child_delimiters = child_delimiters or []

    def chunk_with_parents(self, documents: List[Document], **kwargs) -> Tuple[List[Chunk], List[Chunk]]:
        parent_chunks: List[Chunk] = []
        child_chunks: List[Chunk] = []

        for doc_index, doc in enumerate(documents):
            text = doc.text.strip()
            if not text:
                continue
            source = str(doc.metadata.get("source", "unknown"))

            parent_slices = _split_text_with_overlap(
                text,
                self.parent_chunk_size,
                self.parent_overlap,
                delimiters=self.parent_delimiters,
            )
            for parent_index, (parent_start, parent_end, parent_text) in enumerate(parent_slices):
                parent_stable_key = f"parent:{source}:{doc_index}:{parent_index}:{parent_text[:50]}"
                parent_id = str(uuid.uuid5(uuid.NAMESPACE_URL, parent_stable_key))
                parent_meta = {
                    **doc.metadata,
                    "doc_index": doc_index,
                    "parent_index": parent_index,
                    "char_start": parent_start,
                    "char_end": parent_end,
                    "chunk_level": "parent",
                }
                parent_chunks.append(Chunk(id=parent_id, text=parent_text, metadata=parent_meta))

                child_slices = _split_text_with_overlap(
                    parent_text,
                    self.child_chunk_size,
                    self.child_overlap,
                    delimiters=self.child_delimiters,
                )
                for child_index, (child_rel_start, child_rel_end, child_text) in enumerate(child_slices):
                    child_abs_start = parent_start + child_rel_start
                    child_abs_end = parent_start + child_rel_end
                    child_stable_key = f"child:{source}:{doc_index}:{parent_index}:{child_index}:{child_text[:50]}"
                    child_id = str(uuid.uuid5(uuid.NAMESPACE_URL, child_stable_key))
                    child_meta = {
                        **doc.metadata,
                        "doc_index": doc_index,
                        "parent_index": parent_index,
                        "child_index": child_index,
                        "parent_id": parent_id,
                        "char_start": child_abs_start,
                        "char_end": child_abs_end,
                        "chunk_level": "child",
                    }
                    child_chunks.append(Chunk(id=child_id, text=child_text, metadata=child_meta))

        return parent_chunks, child_chunks

    def chunk(self, documents: List[Document], **kwargs) -> List[Chunk]:
        _, child_chunks = self.chunk_with_parents(documents, **kwargs)
        return child_chunks
