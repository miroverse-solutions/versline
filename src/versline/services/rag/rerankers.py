from __future__ import annotations

import json
from typing import Dict, List, Optional

import cohere
import httpx
from openai import OpenAI

from versline.config import settings
from versline.services.pricing import TokenTracker
from versline.services.rag.base import BaseReranker, RetrievedChunk
from versline.services.rag.runtime import (
    RateLimiter,
    TokenRateLimiter,
    estimate_tokens_from_text,
    estimate_tokens_from_texts,
    retry_call,
    scoped_proxy,
)


class CohereReranker(BaseReranker):
    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        proxy: Optional[str] = None,
        rate_limiter: Optional[RateLimiter] = None,
        token_rate_limiter: Optional[TokenRateLimiter] = None,
    ):
        self.model = model
        self.proxy = proxy if proxy is not None else settings.rag.rerank_proxy
        self.rate_limiter = rate_limiter or RateLimiter(settings.rag.rate_limit_rerank_rpm)
        self.token_rate_limiter = token_rate_limiter or TokenRateLimiter(settings.rag.rate_limit_rerank_tpm)

        resolved_api_key = api_key or settings.rag.rerank_api_key or settings.llm.api_key
        resolved_base_url = base_url or settings.rag.rerank_api_endpoint

        http_client = httpx.Client(proxy=self.proxy) if self.proxy else None
        self.client = cohere.Client(
            api_key=resolved_api_key,
            base_url=resolved_base_url,
            httpx_client=http_client,
        )

    def rerank(self, query: str, items: List[RetrievedChunk], top_k: int) -> List[RetrievedChunk]:
        if not items:
            return []

        docs = [item.text for item in items]
        self.rate_limiter.wait()
        reservation_id = self.token_rate_limiter.reserve(
            estimate_tokens_from_text(query) + estimate_tokens_from_texts(docs)
        )
        rerank_top_n = min(max(1, top_k), len(items))

        def operation():
            with scoped_proxy(self.proxy):
                return self.client.rerank(
                    query=query,
                    documents=docs,
                    model=self.model,
                    top_n=rerank_top_n,
                    return_documents=False,
                )

        response = retry_call(
            operation,
            max_retries=settings.rag.retry_max_retries,
            base_delay_seconds=settings.rag.retry_base_delay_seconds,
            max_delay_seconds=settings.rag.retry_max_delay_seconds,
            operation_name="rerank_request",
        )

        billed_tokens = None
        meta = getattr(response, "meta", None)
        if meta and hasattr(meta, "billed_units") and meta.billed_units:
            search_units = getattr(meta.billed_units, "search_units", None)
            if search_units is not None:
                billed_tokens = int(search_units)
        if billed_tokens is not None:
            self.token_rate_limiter.finalize(
                reservation_id,
                actual_tokens=billed_tokens,
                mode=settings.rag.token_limit_mode,
            )

        ranked_items: List[RetrievedChunk] = []
        by_index: Dict[int, RetrievedChunk] = {index: item for index, item in enumerate(items)}

        results = getattr(response, "results", []) or []
        for entry in results:
            entry_index = getattr(entry, "index", None)
            if entry_index is None and isinstance(entry, dict):
                entry_index = entry.get("index")
            if entry_index is None:
                continue

            original = by_index.get(int(entry_index))
            if original is None:
                continue

            relevance = getattr(entry, "relevance_score", None)
            if relevance is None and isinstance(entry, dict):
                relevance = entry.get("relevance_score")
            score = float(relevance) if relevance is not None else float(original.score)

            ranked_items.append(
                RetrievedChunk(
                    id=original.id,
                    text=original.text,
                    score=score,
                    metadata=original.metadata,
                )
            )

        if ranked_items:
            return ranked_items[:top_k]

        return items[:top_k]


class OpenAICompatibleReranker(BaseReranker):
    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        proxy: Optional[str] = None,
        rate_limiter: Optional[RateLimiter] = None,
        token_rate_limiter: Optional[TokenRateLimiter] = None,
        tracker: Optional[TokenTracker] = None,
    ):
        self.model = model
        self.proxy = proxy if proxy is not None else settings.rag.rerank_proxy
        self.rate_limiter = rate_limiter or RateLimiter(settings.rag.rate_limit_rerank_rpm)
        self.token_rate_limiter = token_rate_limiter or TokenRateLimiter(settings.rag.rate_limit_rerank_tpm)
        self.tracker = tracker

        resolved_api_key = api_key or settings.rag.rerank_api_key or settings.llm.api_key
        resolved_base_url = base_url or settings.rag.rerank_api_endpoint

        provider = (settings.rag.rerank_provider or "openai").lower()
        if provider == "openrouter" and not resolved_base_url:
            resolved_base_url = "https://openrouter.ai/api/v1"
        elif provider == "avalai" and not resolved_base_url:
            resolved_base_url = "https://api.avalai.ir/v1"

        http_client = httpx.Client(proxy=self.proxy) if self.proxy else None
        self.client = OpenAI(
            api_key=resolved_api_key,
            base_url=resolved_base_url,
            http_client=http_client,
        )
        self.provider = provider

    def _is_avalai(self) -> bool:
        if self.provider == "avalai":
            return True
        base_url = getattr(self.client, "base_url", None)
        return bool(base_url and ("avalai.ir" in str(base_url) or "avalapis.ir" in str(base_url)))

    def _build_prompt(self, query: str, items: List[RetrievedChunk], top_k: int) -> str:
        lines = [
            "You are a reranking engine.",
            "Return JSON only with schema: {\"ranked_indices\": [int, ...]}",
            "Indices must refer to the candidate list below and be ordered by relevance descending.",
            f"Return at most {top_k} indices.",
            f"Query: {query}",
            "Candidates:",
        ]
        for idx, item in enumerate(items):
            lines.append(f"[{idx}] {item.text}")
        return "\n".join(lines)

    def rerank(self, query: str, items: List[RetrievedChunk], top_k: int) -> List[RetrievedChunk]:
        if not items:
            return []

        self.rate_limiter.wait()
        candidate_texts = [item.text for item in items]
        reservation_id = self.token_rate_limiter.reserve(
            estimate_tokens_from_text(query) + estimate_tokens_from_texts(candidate_texts)
        )
        rerank_top_n = min(max(1, top_k), len(items))
        prompt = self._build_prompt(query=query, items=items, top_k=rerank_top_n)

        def operation():
            with scoped_proxy(self.proxy):
                if self._is_avalai() and hasattr(self.client.chat.completions, "with_raw_response"):
                    response_raw = self.client.chat.completions.with_raw_response.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"},
                        temperature=0,
                    )
                    request_id = response_raw.headers.get("x-request-id")
                    if self.tracker and request_id:
                        self.tracker.add_avalai_request(request_id)
                    completion = response_raw.parse()
                else:
                    completion = self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"},
                        temperature=0,
                    )

            if self.tracker and completion.usage:
                prompt_tokens = int(completion.usage.prompt_tokens or 0)
                completion_tokens = int(completion.usage.completion_tokens or 0)
                self.tracker.add_usage(
                    prompt_tokens,
                    completion_tokens,
                )
                self.token_rate_limiter.finalize(
                    reservation_id,
                    actual_tokens=prompt_tokens + completion_tokens,
                    mode=settings.rag.token_limit_mode,
                )

            content = completion.choices[0].message.content or "{}"
            payload = json.loads(content)
            ranked_indices = payload.get("ranked_indices", [])
            return ranked_indices

        try:
            ranked_indices = retry_call(
                operation,
                max_retries=settings.rag.retry_max_retries,
                base_delay_seconds=settings.rag.retry_base_delay_seconds,
                max_delay_seconds=settings.rag.retry_max_delay_seconds,
                operation_name="openai_rerank_request",
            )
        except Exception:
            return items[:top_k]

        ranked_items: List[RetrievedChunk] = []
        for idx in ranked_indices:
            try:
                candidate = items[int(idx)]
            except Exception:
                continue
            ranked_items.append(candidate)

        if ranked_items:
            return ranked_items[:top_k]
        return items[:top_k]


class JinaReranker(BaseReranker):
    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        proxy: Optional[str] = None,
        rate_limiter: Optional[RateLimiter] = None,
        token_rate_limiter: Optional[TokenRateLimiter] = None,
    ):
        self.model = model
        self.proxy = proxy if proxy is not None else settings.rag.rerank_proxy
        self.rate_limiter = rate_limiter or RateLimiter(settings.rag.rate_limit_rerank_rpm)
        self.token_rate_limiter = token_rate_limiter or TokenRateLimiter(settings.rag.rate_limit_rerank_tpm)

        self.api_key = api_key or settings.rag.rerank_api_key or settings.llm.api_key
        self.base_url = base_url or settings.rag.rerank_api_endpoint or "https://api.jina.ai/v1/rerank"

        self.http_client = httpx.Client(proxy=self.proxy) if self.proxy else httpx.Client()

    def rerank(self, query: str, items: List[RetrievedChunk], top_k: int) -> List[RetrievedChunk]:
        if not items:
            return []

        docs = [item.text for item in items]
        self.rate_limiter.wait()
        reservation_id = self.token_rate_limiter.reserve(
            estimate_tokens_from_text(query) + estimate_tokens_from_texts(docs)
        )
        rerank_top_n = min(max(1, top_k), len(items))

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "query": query,
            "documents": docs,
            "top_n": rerank_top_n,
        }

        def operation():
            with scoped_proxy(self.proxy):
                response = self.http_client.post(self.base_url, headers=headers, json=payload, timeout=60.0)
            response.raise_for_status()
            return response.json()

        try:
            data = retry_call(
                operation,
                max_retries=settings.rag.retry_max_retries,
                base_delay_seconds=settings.rag.retry_base_delay_seconds,
                max_delay_seconds=settings.rag.retry_max_delay_seconds,
                operation_name="jina_rerank_request",
            )
        except Exception:
            return items[:top_k]

        usage = data.get("usage") if isinstance(data, dict) else None
        total_tokens = None
        if isinstance(usage, dict):
            total_tokens = usage.get("total_tokens")
            if total_tokens is None:
                prompt_tokens = usage.get("prompt_tokens")
                completion_tokens = usage.get("completion_tokens")
                if prompt_tokens is not None or completion_tokens is not None:
                    total_tokens = int(prompt_tokens or 0) + int(completion_tokens or 0)

        if total_tokens is not None:
            self.token_rate_limiter.finalize(
                reservation_id,
                actual_tokens=int(total_tokens),
                mode=settings.rag.token_limit_mode,
            )

        by_index: Dict[int, RetrievedChunk] = {index: item for index, item in enumerate(items)}
        raw_results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(raw_results, list):
            return items[:top_k]

        ranked_items: List[RetrievedChunk] = []
        for entry in raw_results:
            if not isinstance(entry, dict):
                continue
            idx = entry.get("index")
            if idx is None:
                doc = entry.get("document")
                if isinstance(doc, dict):
                    idx = doc.get("index")
            if idx is None:
                continue

            original = by_index.get(int(idx))
            if original is None:
                continue

            score = entry.get("relevance_score")
            if score is None:
                score = entry.get("score")
            if score is None and isinstance(entry.get("document"), dict):
                score = entry["document"].get("score")
            final_score = float(score) if score is not None else float(original.score)

            ranked_items.append(
                RetrievedChunk(
                    id=original.id,
                    text=original.text,
                    score=final_score,
                    metadata=original.metadata,
                )
            )

        if ranked_items:
            return ranked_items[:top_k]
        return items[:top_k]
