from __future__ import annotations

from typing import List, Optional

import httpx
from fastembed import SparseTextEmbedding
from loguru import logger
from openai import OpenAI

from versline.config import settings
from versline.services.pricing import TokenTracker
from versline.services.rag.base import BaseEmbedder
from versline.services.rag.runtime import (
    RateLimiter,
    TokenRateLimiter,
    estimate_tokens_from_texts,
    retry_call,
    scoped_proxy,
)


class OpenAICompatibleEmbedder(BaseEmbedder):
    def __init__(
        self,
        model: str,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        api_endpoint: Optional[str] = None,
        proxy: Optional[str] = None,
        rate_limiter: Optional[RateLimiter] = None,
        token_rate_limiter: Optional[TokenRateLimiter] = None,
        tracker: Optional[TokenTracker] = None,
    ):
        self.model = model
        self.provider = (provider or settings.rag.embedding_provider or settings.llm.provider or "openai").lower()
        self.proxy = proxy if proxy is not None else settings.rag.embedding_proxy
        self.rate_limiter = rate_limiter or RateLimiter(settings.rag.rate_limit_embedding_rpm)
        self.token_rate_limiter = token_rate_limiter or TokenRateLimiter(settings.rag.rate_limit_embedding_tpm)
        self.tracker = tracker

        resolved_api_key = api_key or settings.rag.embedding_api_key or settings.llm.api_key
        resolved_endpoint = api_endpoint or settings.rag.embedding_api_endpoint or settings.llm.api_endpoint

        if self.provider in {"google", "gemini"}:
            raise ValueError("Embedding provider must be OpenAI-compatible for current embedder")

        if self.provider == "openrouter" and not resolved_endpoint:
            resolved_endpoint = "https://openrouter.ai/api/v1"
        if self.provider == "avalai" and not resolved_endpoint:
            resolved_endpoint = "https://api.avalai.ir/v1/embeddings"

        http_client = httpx.Client(proxy=self.proxy) if self.proxy else None
        self.client = OpenAI(
            api_key=resolved_api_key,
            base_url=resolved_endpoint,
            http_client=http_client,
        )

        logger.info(f"Embedding model: {self.model} ({self.provider})")

    def _is_avalai(self) -> bool:
        if self.provider == "avalai":
            return True
        base_url = getattr(self.client, "base_url", None)
        return bool(base_url and ("avalai.ir" in str(base_url) or "avalapis.ir" in str(base_url)))

    def _embed(self, texts: List[str]) -> List[List[float]]:
        self.rate_limiter.wait()
        estimated_tokens = estimate_tokens_from_texts(texts)
        reservation_id = self.token_rate_limiter.reserve(estimated_tokens)

        def operation():
            with scoped_proxy(self.proxy):
                if self._is_avalai() and hasattr(self.client.embeddings, "with_raw_response"):
                    response_raw = self.client.embeddings.with_raw_response.create(
                        model=self.model,
                        input=texts,
                    )
                    request_id = response_raw.headers.get("x-request-id")
                    if self.tracker and request_id:
                        self.tracker.add_avalai_request(request_id)
                    response = response_raw.parse()
                else:
                    response = self.client.embeddings.create(model=self.model, input=texts)
            usage_prompt_tokens = None
            if self.tracker and hasattr(response, "usage") and response.usage:
                prompt_tokens = int(getattr(response.usage, "prompt_tokens", 0) or 0)
                self.tracker.add_usage(prompt_tokens, 0)
                usage_prompt_tokens = prompt_tokens

            if usage_prompt_tokens is not None:
                self.token_rate_limiter.finalize(
                    reservation_id,
                    actual_tokens=usage_prompt_tokens,
                    mode=settings.rag.token_limit_mode,
                )
            return [item.embedding for item in response.data]

        return retry_call(
            operation,
            max_retries=settings.rag.retry_max_retries,
            base_delay_seconds=settings.rag.retry_base_delay_seconds,
            max_delay_seconds=settings.rag.retry_max_delay_seconds,
            operation_name="embedding_request",
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        return self._embed(texts)

    def embed_query(self, text: str) -> List[float]:
        vectors = self._embed([text])
        return vectors[0] if vectors else []


class FastEmbedSparseEmbedder:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = SparseTextEmbedding(model_name=model_name)

    def embed_documents(self, texts: List[str]) -> List[dict]:
        if not texts:
            return []
        vectors = list(self._model.embed(texts))
        return [
            {
                "indices": [int(idx) for idx in vector.indices],
                "values": [float(value) for value in vector.values],
            }
            for vector in vectors
        ]

    def embed_query(self, text: str) -> dict:
        vectors = self.embed_documents([text])
        return vectors[0] if vectors else {"indices": [], "values": []}
