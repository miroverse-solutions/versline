from __future__ import annotations

import json
import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

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


@contextmanager
def _scoped_model_environment(
    proxy: Optional[str],
    cache_dir: Optional[str],
    local_files_only: bool,
    openvino_cache_dir: Optional[str] = None,
):
    keys = [
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
        "HUGGINGFACE_HUB_CACHE",
        "TRANSFORMERS_CACHE",
        "OPENVINO_CACHE_DIR",
        "OV_CACHE_DIR",
    ]
    previous = {key: os.environ.get(key) for key in keys}
    try:
        if local_files_only:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
        if cache_dir:
            os.environ["HUGGINGFACE_HUB_CACHE"] = cache_dir
            os.environ["TRANSFORMERS_CACHE"] = cache_dir
        if openvino_cache_dir:
            os.environ["OPENVINO_CACHE_DIR"] = openvino_cache_dir
            os.environ["OV_CACHE_DIR"] = openvino_cache_dir
        with scoped_proxy(proxy):
            yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


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
        self.timeout_seconds = float(settings.rag.rerank_timeout_seconds)

        resolved_api_key = api_key or settings.rag.rerank_api_key or settings.llm.api_key
        resolved_base_url = base_url or settings.rag.rerank_api_endpoint

        http_timeout = httpx.Timeout(self.timeout_seconds)
        http_client = httpx.Client(proxy=self.proxy, timeout=http_timeout) if self.proxy else httpx.Client(timeout=http_timeout)
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
        self.timeout_seconds = float(settings.rag.rerank_timeout_seconds)

        provider = (settings.rag.rerank_provider or "openai").lower()
        resolved_api_key = api_key or settings.rag.rerank_api_key or settings.llm.api_key
        resolved_base_url = base_url or settings.rag.rerank_api_endpoint
        if provider == "openrouter" and not resolved_base_url:
            resolved_base_url = "https://openrouter.ai/api/v1"
        elif provider == "avalai" and not resolved_base_url:
            resolved_base_url = "https://api.avalai.ir/v1"
        elif provider == "local":
            if not resolved_base_url:
                resolved_base_url = "http://localhost:11434/v1"
            if not resolved_api_key:
                resolved_api_key = "local"

        http_timeout = httpx.Timeout(self.timeout_seconds)
        http_client = httpx.Client(proxy=self.proxy, timeout=http_timeout) if self.proxy else httpx.Client(timeout=http_timeout)
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
                        timeout=self.timeout_seconds,
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
                        timeout=self.timeout_seconds,
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
        self.timeout_seconds = float(settings.rag.rerank_timeout_seconds)

        self.api_key = api_key or settings.rag.rerank_api_key or settings.llm.api_key
        self.base_url = base_url or settings.rag.rerank_api_endpoint or "https://api.jina.ai/v1/rerank"

        http_timeout = httpx.Timeout(self.timeout_seconds)
        self.http_client = httpx.Client(proxy=self.proxy, timeout=http_timeout) if self.proxy else httpx.Client(timeout=http_timeout)

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
                response = self.http_client.post(self.base_url, headers=headers, json=payload, timeout=self.timeout_seconds)
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


class SentenceTransformersReranker(BaseReranker):
    def __init__(
        self,
        model: str,
        proxy: Optional[str] = None,
        cache_dir: Optional[str] = None,
        local_files_only: Optional[bool] = None,
        model_path: Optional[str] = None,
        device: Optional[str] = None,
        batch_size: Optional[int] = None,
        inference_backend: Optional[str] = None,
        rate_limiter: Optional[RateLimiter] = None,
        token_rate_limiter: Optional[TokenRateLimiter] = None,
    ):
        self.model = model
        self.proxy = proxy if proxy is not None else settings.rag.rerank_proxy
        self.cache_dir = cache_dir if cache_dir is not None else settings.rag.rerank_cache_dir
        configured_local_only = settings.rag.rerank_local_files_only if local_files_only is None else bool(local_files_only)
        self.local_files_only = True if self.cache_dir else configured_local_only
        self.model_path = model_path if model_path is not None else settings.rag.rerank_model_path
        self.device = device if device is not None else settings.rag.rerank_device
        self.batch_size = max(1, int(batch_size if batch_size is not None else settings.rag.rerank_batch_size))
        self.inference_backend = (inference_backend if inference_backend is not None else settings.rag.rerank_inference_backend or "auto").lower()
        self.rate_limiter = rate_limiter or RateLimiter(settings.rag.rate_limit_rerank_rpm)
        self.token_rate_limiter = token_rate_limiter or TokenRateLimiter(settings.rag.rate_limit_rerank_tpm)

        model_source = self.model_path or self.model
        try:
            from sentence_transformers import CrossEncoder
        except Exception as error:
            raise RuntimeError(
                "sentence-transformers rerank backend selected but package is not installed. "
                "Install it with: pip install sentence-transformers"
            ) from error

        with _scoped_model_environment(
            self.proxy,
            self.cache_dir,
            self.local_files_only,
            settings.rag.openvino_cache_dir,
        ):
            kwargs = {
                "model_name": model_source,
                "device": self.device,
                "cache_folder": self.cache_dir,
                "local_files_only": self.local_files_only,
            }
            if self.inference_backend == "openvino":
                kwargs["backend"] = "openvino"
            self._model = CrossEncoder(**kwargs)

    def rerank(self, query: str, items: List[RetrievedChunk], top_k: int) -> List[RetrievedChunk]:
        if not items:
            return []

        self.rate_limiter.wait()
        docs = [item.text for item in items]
        self.token_rate_limiter.reserve(
            estimate_tokens_from_text(query) + estimate_tokens_from_texts(docs)
        )

        pairs = [[query, item.text] for item in items]
        with _scoped_model_environment(
            self.proxy,
            self.cache_dir,
            self.local_files_only,
            settings.rag.openvino_cache_dir,
        ):
            raw_scores = self._model.predict(
                pairs,
                batch_size=self.batch_size,
                show_progress_bar=False,
            )

        scores: List[float]
        if hasattr(raw_scores, "tolist"):
            scores = [float(value) for value in raw_scores.tolist()]
        else:
            scores = [float(value) for value in raw_scores]

        ranked_indices = sorted(range(len(items)), key=lambda idx: scores[idx], reverse=True)
        limit = min(max(1, top_k), len(items))
        ranked_items: List[RetrievedChunk] = []
        for idx in ranked_indices[:limit]:
            original = items[idx]
            ranked_items.append(
                RetrievedChunk(
                    id=original.id,
                    text=original.text,
                    score=scores[idx],
                    metadata=original.metadata,
                )
            )
        return ranked_items


class FastEmbedReranker(BaseReranker):
    def __init__(
        self,
        model: str,
        proxy: Optional[str] = None,
        cache_dir: Optional[str] = None,
        local_files_only: Optional[bool] = None,
        providers: Optional[List[Any]] = None,
        rate_limiter: Optional[RateLimiter] = None,
        token_rate_limiter: Optional[TokenRateLimiter] = None,
    ):
        self.model = model
        self.proxy = proxy if proxy is not None else settings.rag.rerank_proxy
        self.cache_dir = cache_dir if cache_dir is not None else settings.rag.rerank_cache_dir
        configured_local_only = settings.rag.rerank_local_files_only if local_files_only is None else bool(local_files_only)
        self.local_files_only = True if self.cache_dir else configured_local_only
        self.providers: List[Any] = []
        for provider in providers or []:
            if isinstance(provider, str):
                cleaned = provider.strip()
                if cleaned:
                    self.providers.append(cleaned)
            elif provider:
                self.providers.append(provider)
        self.rate_limiter = rate_limiter or RateLimiter(settings.rag.rate_limit_rerank_rpm)
        self.token_rate_limiter = token_rate_limiter or TokenRateLimiter(settings.rag.rate_limit_rerank_tpm)

        try:
            from fastembed import TextCrossEncoder as _FastEmbedCrossEncoder  # type: ignore
        except Exception:
            try:
                from fastembed.rerank.cross_encoder import TextCrossEncoder as _FastEmbedCrossEncoder  # type: ignore
            except Exception as error:
                raise RuntimeError(
                    "fastembed rerank backend selected but TextCrossEncoder is unavailable. "
                    "Upgrade fastembed to a version that provides TextCrossEncoder."
                ) from error

        with _scoped_model_environment(
            self.proxy,
            self.cache_dir,
            self.local_files_only,
            settings.rag.openvino_cache_dir,
        ):
            try:
                kwargs = {
                    "model_name": self.model,
                    "cache_dir": self.cache_dir,
                    "local_files_only": self.local_files_only,
                }
                if self.providers:
                    kwargs["providers"] = self.providers
                self._model = _FastEmbedCrossEncoder(**kwargs)
            except TypeError as error:
                if self.providers:
                    raise RuntimeError(
                        "Current fastembed version does not support custom ONNX providers for rerank. "
                        "Please upgrade fastembed to use OpenVINOExecutionProvider."
                    ) from error
                raise

    @staticmethod
    def _score_from_entry(entry: object) -> Optional[float]:
        if isinstance(entry, dict):
            for key in ("score", "relevance_score"):
                value = entry.get(key)
                if value is not None:
                    return float(value)
            return None
        for key in ("score", "relevance_score"):
            value = getattr(entry, key, None)
            if value is not None:
                return float(value)
        return None

    @staticmethod
    def _index_from_entry(entry: object) -> Optional[int]:
        if isinstance(entry, dict):
            value = entry.get("index")
            if value is not None:
                return int(value)
            return None
        value = getattr(entry, "index", None)
        if value is not None:
            return int(value)
        return None

    def rerank(self, query: str, items: List[RetrievedChunk], top_k: int) -> List[RetrievedChunk]:
        if not items:
            return []

        self.rate_limiter.wait()
        docs = [item.text for item in items]
        self.token_rate_limiter.reserve(
            estimate_tokens_from_text(query) + estimate_tokens_from_texts(docs)
        )
        rerank_top_n = min(max(1, top_k), len(items))

        try:
            with _scoped_model_environment(
                self.proxy,
                self.cache_dir,
                self.local_files_only,
                settings.rag.openvino_cache_dir,
            ):
                if hasattr(self._model, "rerank"):
                    raw = self._model.rerank(query=query, documents=docs, top_n=rerank_top_n)
                elif hasattr(self._model, "predict"):
                    pairs = [[query, item.text] for item in items]
                    raw = self._model.predict(pairs)
                else:
                    return items[:top_k]
        except Exception:
            return items[:top_k]

        ranked_items: List[RetrievedChunk] = []
        if isinstance(raw, list):
            if raw and self._index_from_entry(raw[0]) is not None:
                for entry in raw:
                    idx = self._index_from_entry(entry)
                    if idx is None or idx < 0 or idx >= len(items):
                        continue
                    original = items[idx]
                    score = self._score_from_entry(entry)
                    ranked_items.append(
                        RetrievedChunk(
                            id=original.id,
                            text=original.text,
                            score=float(score) if score is not None else float(original.score),
                            metadata=original.metadata,
                        )
                    )
            else:
                try:
                    scores = [float(value) for value in raw]
                except Exception:
                    scores = []
                if scores:
                    ranked_indices = sorted(range(len(items)), key=lambda idx: scores[idx], reverse=True)
                    for idx in ranked_indices[:rerank_top_n]:
                        original = items[idx]
                        ranked_items.append(
                            RetrievedChunk(
                                id=original.id,
                                text=original.text,
                                score=scores[idx],
                                metadata=original.metadata,
                            )
                        )

        if ranked_items:
            return ranked_items[:top_k]
        return items[:top_k]
