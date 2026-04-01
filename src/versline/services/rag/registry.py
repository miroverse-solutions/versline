from __future__ import annotations

from typing import Dict

from versline.services.rag.base import BasePreprocessor, BaseVectorStore


class PreprocessorRegistry:
    def __init__(self):
        self._items: Dict[str, BasePreprocessor] = {}

    def register(self, input_type: str, preprocessor: BasePreprocessor) -> None:
        self._items[input_type.lower()] = preprocessor

    def get(self, input_type: str) -> BasePreprocessor:
        key = input_type.lower()
        if key not in self._items:
            available = ", ".join(sorted(self._items.keys())) or "none"
            raise ValueError(f"No preprocessor registered for '{input_type}'. Available: {available}")
        return self._items[key]


class VectorStoreRegistry:
    def __init__(self):
        self._items: Dict[str, BaseVectorStore] = {}

    def register(self, backend_type: str, store: BaseVectorStore) -> None:
        self._items[backend_type.lower()] = store

    def get(self, backend_type: str) -> BaseVectorStore:
        key = backend_type.lower()
        if key not in self._items:
            available = ", ".join(sorted(self._items.keys())) or "none"
            raise ValueError(f"No vector store registered for '{backend_type}'. Available: {available}")
        return self._items[key]
