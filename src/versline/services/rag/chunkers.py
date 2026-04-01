from __future__ import annotations

import hashlib
from typing import List

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
                    chunk_id = hashlib.sha1(stable_key.encode("utf-8")).hexdigest()
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
