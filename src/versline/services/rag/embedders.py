from __future__ import annotations

from typing import List

from loguru import logger

from versline.config import settings
from versline.services import ai
from versline.services.rag.base import BaseEmbedder


class OpenAICompatibleEmbedder(BaseEmbedder):
    def __init__(self, model: str):
        self.model = model
        provider = settings.llm.provider.lower() if settings.llm.provider else "openai"

        if provider == "google":
            raise ValueError(
                "Current embedder is OpenAI-compatible. Set --provider to OpenAI/OpenRouter/AvalAI/OpenAICompatible."
            )

        if provider == "openrouter":
            original_endpoint = settings.llm.api_endpoint
            if not original_endpoint:
                settings.llm.api_endpoint = "https://openrouter.ai/api/v1"
            try:
                self.client = ai.configure_openai(settings.llm)
            finally:
                settings.llm.api_endpoint = original_endpoint
        elif provider == "avalai":
            original_endpoint = settings.llm.api_endpoint
            settings.llm.api_endpoint = "https://api.avalai.ir/v1"
            try:
                self.client = ai.configure_openai(settings.llm)
            finally:
                settings.llm.api_endpoint = original_endpoint
        else:
            self.client = ai.configure_openai(settings.llm)

        if self.client is None:
            raise RuntimeError("Embedding client initialization failed")

        logger.info(f"Embedding model: {self.model}")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        response = self.client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> List[float]:
        response = self.client.embeddings.create(model=self.model, input=[text])
        return response.data[0].embedding
