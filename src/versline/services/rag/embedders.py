from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import httpx
from fastembed import SparseTextEmbedding, TextEmbedding
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
        self.timeout_seconds = float(settings.rag.embedding_timeout_seconds)

        resolved_api_key = api_key or settings.rag.embedding_api_key or settings.llm.api_key
        resolved_endpoint = api_endpoint or settings.rag.embedding_api_endpoint or settings.llm.api_endpoint

        if self.provider in {"google", "gemini"}:
            raise ValueError("Embedding provider must be OpenAI-compatible for current embedder")

        if self.provider == "openrouter" and not resolved_endpoint:
            resolved_endpoint = "https://openrouter.ai/api/v1"
        if self.provider == "avalai" and not resolved_endpoint:
            resolved_endpoint = "https://api.avalai.ir/v1/embeddings"

        http_timeout = httpx.Timeout(self.timeout_seconds)
        http_client = httpx.Client(proxy=self.proxy, timeout=http_timeout) if self.proxy else httpx.Client(timeout=http_timeout)
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
                    response = self.client.embeddings.create(model=self.model, input=texts, timeout=self.timeout_seconds)
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


class FastEmbedDenseEmbedder(BaseEmbedder):
    def __init__(
        self,
        model_name: str,
        proxy: Optional[str] = None,
        cache_dir: Optional[str] = None,
        local_files_only: Optional[bool] = None,
        providers: Optional[List[Any]] = None,
    ):
        self.model_name = model_name
        self.proxy = proxy if proxy is not None else settings.rag.embedding_proxy
        self.cache_dir = cache_dir if cache_dir is not None else settings.rag.embedding_cache_dir
        configured_local_only = settings.rag.embedding_local_files_only if local_files_only is None else bool(local_files_only)
        self.local_files_only = True if self.cache_dir else configured_local_only
        self.providers: List[Any] = []
        for provider in providers or []:
            if isinstance(provider, str):
                cleaned = provider.strip()
                if cleaned:
                    self.providers.append(cleaned)
            elif provider:
                self.providers.append(provider)

        with _scoped_model_environment(
            self.proxy,
            self.cache_dir,
            self.local_files_only,
            settings.rag.openvino_cache_dir,
        ):
            try:
                kwargs = {
                    "model_name": model_name,
                    "cache_dir": self.cache_dir,
                    "local_files_only": self.local_files_only,
                }
                if self.providers:
                    kwargs["providers"] = self.providers
                self._model = TextEmbedding(**kwargs)
            except TypeError as error:
                if self.providers:
                    raise RuntimeError(
                        "Current fastembed version does not support custom ONNX providers. "
                        "Please upgrade fastembed to use OpenVINOExecutionProvider."
                    ) from error
                raise
            except ValueError as error:
                raise RuntimeError(
                    "FastEmbed does not support the selected dense model. "
                    f"Model: {model_name}. "
                    "Use a FastEmbed-supported model, or switch backend to sentence-transformers/flagembedding "
                    "with --embedding-provider."
                ) from error

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        with _scoped_model_environment(
            self.proxy,
            self.cache_dir,
            self.local_files_only,
            settings.rag.openvino_cache_dir,
        ):
            vectors = list(self._model.embed(texts))
        return [vector.tolist() if hasattr(vector, "tolist") else [float(x) for x in vector] for vector in vectors]

    def embed_query(self, text: str) -> List[float]:
        vectors = self.embed_documents([text])
        return vectors[0] if vectors else []


class SentenceTransformersDenseEmbedder(BaseEmbedder):
    def __init__(
        self,
        model_name: str,
        proxy: Optional[str] = None,
        cache_dir: Optional[str] = None,
        local_files_only: Optional[bool] = None,
        model_path: Optional[str] = None,
        device: Optional[str] = None,
        batch_size: Optional[int] = None,
        inference_backend: Optional[str] = None,
    ):
        self.model_name = model_name
        self.proxy = proxy if proxy is not None else settings.rag.embedding_proxy
        self.cache_dir = cache_dir if cache_dir is not None else settings.rag.embedding_cache_dir
        self.model_path = model_path if model_path is not None else settings.rag.embedding_model_path
        configured_local_only = settings.rag.embedding_local_files_only if local_files_only is None else bool(local_files_only)
        self.local_files_only = True if self.cache_dir else configured_local_only
        self.device = device if device is not None else settings.rag.embedding_device
        self.batch_size = max(1, int(batch_size if batch_size is not None else settings.rag.embedding_batch_size))
        self.inference_backend = (inference_backend if inference_backend is not None else settings.rag.embedding_inference_backend or "auto").lower()

        try:
            from sentence_transformers import SentenceTransformer
        except Exception as error:
            raise RuntimeError(
                "sentence-transformers backend selected but package is not installed. "
                "Install it with: pip install sentence-transformers"
            ) from error

        model_source = self.model_path or self.model_name
        with _scoped_model_environment(
            self.proxy,
            self.cache_dir,
            self.local_files_only,
            settings.rag.openvino_cache_dir,
        ):
            kwargs = {
                "model_name_or_path": model_source,
                "device": self.device,
                "cache_folder": self.cache_dir,
                "local_files_only": self.local_files_only,
            }
            if self.inference_backend == "openvino":
                kwargs["backend"] = "openvino"
            self._model = SentenceTransformer(**kwargs)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        with _scoped_model_environment(
            self.proxy,
            self.cache_dir,
            self.local_files_only,
            settings.rag.openvino_cache_dir,
        ):
            vectors = self._model.encode(
                texts,
                batch_size=self.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=False,
            )
        if hasattr(vectors, "tolist"):
            return vectors.tolist()
        return [[float(x) for x in row] for row in vectors]

    def embed_query(self, text: str) -> List[float]:
        vectors = self.embed_documents([text])
        return vectors[0] if vectors else []


class FlagEmbeddingDenseEmbedder(BaseEmbedder):
    def __init__(
        self,
        model_name: str,
        proxy: Optional[str] = None,
        cache_dir: Optional[str] = None,
        local_files_only: Optional[bool] = None,
        model_path: Optional[str] = None,
        use_fp16: Optional[bool] = None,
        device: Optional[str] = None,
        batch_size: Optional[int] = None,
    ):
        self.model_name = model_name
        self.proxy = proxy if proxy is not None else settings.rag.embedding_proxy
        self.cache_dir = cache_dir if cache_dir is not None else settings.rag.embedding_cache_dir
        self.model_path = model_path if model_path is not None else settings.rag.embedding_model_path
        configured_local_only = settings.rag.embedding_local_files_only if local_files_only is None else bool(local_files_only)
        self.local_files_only = True if self.cache_dir else configured_local_only
        self.use_fp16 = settings.rag.embedding_use_fp16 if use_fp16 is None else bool(use_fp16)
        self.device = device if device is not None else settings.rag.embedding_device
        self.batch_size = max(1, int(batch_size if batch_size is not None else settings.rag.embedding_batch_size))

        try:
            from FlagEmbedding import BGEM3FlagModel
        except Exception as error:
            raise RuntimeError(
                "FlagEmbedding backend failed to initialize. "
                "Ensure compatible versions are installed, e.g. pip install -U FlagEmbedding transformers. "
                f"Original error: {error}"
            ) from error

        model_source = self.model_path or self.model_name
        with _scoped_model_environment(
            self.proxy,
            self.cache_dir,
            self.local_files_only,
            settings.rag.openvino_cache_dir,
        ):
            self._model = BGEM3FlagModel(
                model_source,
                use_fp16=self.use_fp16,
                device=self.device,
            )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        with _scoped_model_environment(
            self.proxy,
            self.cache_dir,
            self.local_files_only,
            settings.rag.openvino_cache_dir,
        ):
            encoded = self._model.encode(
                texts,
                batch_size=self.batch_size,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
        dense_vecs = encoded.get("dense_vecs") if isinstance(encoded, dict) else []
        if hasattr(dense_vecs, "tolist"):
            return dense_vecs.tolist()
        return [[float(x) for x in row] for row in dense_vecs]

    def embed_query(self, text: str) -> List[float]:
        vectors = self.embed_documents([text])
        return vectors[0] if vectors else []


class FastEmbedSparseEmbedder:
    def __init__(
        self,
        model_name: str,
        proxy: Optional[str] = None,
        cache_dir: Optional[str] = None,
        local_files_only: Optional[bool] = None,
        providers: Optional[List[Any]] = None,
    ):
        self.model_name = model_name
        self.proxy = proxy if proxy is not None else (settings.rag.sparse_embedding_proxy or settings.rag.embedding_proxy)
        self.cache_dir = cache_dir if cache_dir is not None else settings.rag.sparse_embedding_cache_dir
        configured_local_only = settings.rag.sparse_embedding_local_files_only if local_files_only is None else bool(local_files_only)
        self.local_files_only = True if self.cache_dir else configured_local_only
        self.providers: List[Any] = []
        for provider in providers or []:
            if isinstance(provider, str):
                cleaned = provider.strip()
                if cleaned:
                    self.providers.append(cleaned)
            elif provider:
                self.providers.append(provider)
        with _scoped_model_environment(
            self.proxy,
            self.cache_dir,
            self.local_files_only,
            settings.rag.openvino_cache_dir,
        ):
            try:
                kwargs = {
                    "model_name": model_name,
                    "cache_dir": self.cache_dir,
                    "local_files_only": self.local_files_only,
                }
                if self.providers:
                    kwargs["providers"] = self.providers
                self._model = SparseTextEmbedding(**kwargs)
            except TypeError as error:
                if self.providers:
                    raise RuntimeError(
                        "Current fastembed version does not support custom ONNX providers for sparse models. "
                        "Please upgrade fastembed to use OpenVINOExecutionProvider."
                    ) from error
                raise

    def embed_documents(self, texts: List[str]) -> List[dict]:
        if not texts:
            return []
        with _scoped_model_environment(
            self.proxy,
            self.cache_dir,
            self.local_files_only,
            settings.rag.openvino_cache_dir,
        ):
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


class FlagEmbeddingSparseEmbedder:
    def __init__(
        self,
        model_name: str,
        proxy: Optional[str] = None,
        cache_dir: Optional[str] = None,
        local_files_only: Optional[bool] = None,
        model_path: Optional[str] = None,
        use_fp16: Optional[bool] = None,
        device: Optional[str] = None,
        batch_size: Optional[int] = None,
    ):
        self.model_name = model_name
        self.proxy = proxy if proxy is not None else (settings.rag.sparse_embedding_proxy or settings.rag.embedding_proxy)
        self.cache_dir = cache_dir if cache_dir is not None else settings.rag.sparse_embedding_cache_dir
        self.model_path = model_path if model_path is not None else settings.rag.sparse_embedding_model_path
        configured_local_only = settings.rag.sparse_embedding_local_files_only if local_files_only is None else bool(local_files_only)
        self.local_files_only = True if self.cache_dir else configured_local_only
        self.use_fp16 = settings.rag.sparse_embedding_use_fp16 if use_fp16 is None else bool(use_fp16)
        self.device = device if device is not None else settings.rag.sparse_embedding_device
        self.batch_size = max(1, int(batch_size if batch_size is not None else settings.rag.sparse_embedding_batch_size))

        try:
            from FlagEmbedding import BGEM3FlagModel
        except Exception as error:
            raise RuntimeError(
                "FlagEmbedding backend selected but package is not installed. "
                "Install it with: pip install FlagEmbedding"
            ) from error

        model_source = self.model_path or self.model_name
        with _scoped_model_environment(self.proxy, self.cache_dir, self.local_files_only):
            self._model = BGEM3FlagModel(
                model_source,
                use_fp16=self.use_fp16,
                device=self.device,
            )

    def _convert_sparse_weights(self, weights: Dict) -> Dict[str, List[float]]:
        indices: List[int] = []
        values: List[float] = []
        for key, value in (weights or {}).items():
            try:
                token_id = int(key)
                token_weight = float(value)
            except Exception:
                continue
            indices.append(token_id)
            values.append(token_weight)
        return {"indices": indices, "values": values}

    def embed_documents(self, texts: List[str]) -> List[dict]:
        if not texts:
            return []

        with _scoped_model_environment(self.proxy, self.cache_dir, self.local_files_only):
            encoded = self._model.encode(
                texts,
                batch_size=self.batch_size,
                return_dense=False,
                return_sparse=True,
                return_colbert_vecs=False,
            )

        lexical_weights = []
        if isinstance(encoded, dict):
            lexical_weights = encoded.get("lexical_weights") or []

        vectors: List[dict] = []
        for item in lexical_weights:
            if isinstance(item, dict):
                vectors.append(self._convert_sparse_weights(item))
            else:
                vectors.append({"indices": [], "values": []})
        return vectors

    def embed_query(self, text: str) -> dict:
        vectors = self.embed_documents([text])
        return vectors[0] if vectors else {"indices": [], "values": []}


class SentenceTransformersSparseEmbedder:
    def __init__(
        self,
        model_name: str,
        proxy: Optional[str] = None,
        cache_dir: Optional[str] = None,
        local_files_only: Optional[bool] = None,
        model_path: Optional[str] = None,
        device: Optional[str] = None,
        batch_size: Optional[int] = None,
    ):
        self.model_name = model_name
        self.proxy = proxy if proxy is not None else (settings.rag.sparse_embedding_proxy or settings.rag.embedding_proxy)
        self.cache_dir = cache_dir if cache_dir is not None else settings.rag.sparse_embedding_cache_dir
        self.model_path = model_path if model_path is not None else settings.rag.sparse_embedding_model_path
        configured_local_only = settings.rag.sparse_embedding_local_files_only if local_files_only is None else bool(local_files_only)
        self.local_files_only = True if self.cache_dir else configured_local_only
        self.device = device if device is not None else settings.rag.sparse_embedding_device
        self.batch_size = max(1, int(batch_size if batch_size is not None else settings.rag.sparse_embedding_batch_size))

        try:
            import torch
            from transformers import AutoModelForMaskedLM, AutoTokenizer
        except Exception as error:
            raise RuntimeError(
                "sentence-transformers sparse backend requires transformers and torch. "
                "Install with: pip install -U transformers torch"
            ) from error

        self._torch = torch
        model_source = self.model_path or self.model_name
        with _scoped_model_environment(
            self.proxy,
            self.cache_dir,
            self.local_files_only,
            settings.rag.openvino_cache_dir,
        ):
            self._tokenizer = AutoTokenizer.from_pretrained(
                model_source,
                cache_dir=self.cache_dir,
                local_files_only=self.local_files_only,
            )
            try:
                self._model = AutoModelForMaskedLM.from_pretrained(
                    model_source,
                    cache_dir=self.cache_dir,
                    local_files_only=self.local_files_only,
                )
            except Exception as error:
                raise RuntimeError(
                    "Sparse sentence-transformers backend expects a masked-language-model compatible checkpoint "
                    "(for example SPLADE family), but model loading failed. "
                    f"Model source: {model_source}. Original error: {error}"
                ) from error

        target_device = self.device or ("cuda" if self._torch.cuda.is_available() else "cpu")
        self._device = self._torch.device(target_device)
        self._model.to(self._device)
        self._model.eval()

    def _encode_batch(self, texts: List[str]) -> List[dict]:
        with _scoped_model_environment(
            self.proxy,
            self.cache_dir,
            self.local_files_only,
            settings.rag.openvino_cache_dir,
        ):
            tokenized = self._tokenizer(
                texts,
                padding=True,
                truncation=True,
                return_tensors="pt",
            )

        tokenized = {key: value.to(self._device) for key, value in tokenized.items()}

        with self._torch.no_grad():
            logits = self._model(**tokenized).logits
            # SPLADE-style sparse activation: log(1 + relu(logits)), max-pooled over sequence.
            relu_logits = self._torch.relu(logits)
            weighted = self._torch.log1p(relu_logits)
            attention = tokenized["attention_mask"].unsqueeze(-1)
            weighted = weighted * attention
            sparse_vectors = weighted.max(dim=1).values

        vectors: List[dict] = []
        for row in sparse_vectors:
            nonzero = self._torch.nonzero(row > 0, as_tuple=False).squeeze(-1)
            if nonzero.numel() == 0:
                vectors.append({"indices": [], "values": []})
                continue
            values = row[nonzero]
            vectors.append(
                {
                    "indices": [int(item) for item in nonzero.detach().cpu().tolist()],
                    "values": [float(item) for item in values.detach().cpu().tolist()],
                }
            )
        return vectors

    def embed_documents(self, texts: List[str]) -> List[dict]:
        if not texts:
            return []
        vectors: List[dict] = []
        for index in range(0, len(texts), self.batch_size):
            vectors.extend(self._encode_batch(texts[index : index + self.batch_size]))
        return vectors

    def embed_query(self, text: str) -> dict:
        vectors = self.embed_documents([text])
        return vectors[0] if vectors else {"indices": [], "values": []}


class OptimumIntelEmbedder(BaseEmbedder):
    """Dense embedder backed by optimum.intel OVModelForFeatureExtraction.

    Supports both pre-exported OpenVINO IR directories and on-the-fly export
    from a standard HuggingFace feature-extraction model.  Mean-pooling is
    applied over the last hidden state (identical to the approach in qt.py).

    Args:
        model_name: HuggingFace model ID (used as fallback when model_path is
            not set and for logging).
        proxy: Optional HTTP/HTTPS/SOCKS proxy.
        cache_dir: HuggingFace hub cache directory.
        local_files_only: Prevent network access when loading the model.
        model_path: Absolute path to the model directory.  When the directory
            already contains ``openvino_model.xml`` the model is loaded without
            re-exporting (``export=False``).  Otherwise ``export=True`` is used
            to convert from PyTorch/ONNX on first load.
        device: OpenVINO device string, e.g. ``"CPU"`` or ``"GPU"``.
        batch_size: Number of texts to encode per forward pass.
    """

    def __init__(
        self,
        model_name: str,
        proxy: Optional[str] = None,
        cache_dir: Optional[str] = None,
        local_files_only: Optional[bool] = None,
        model_path: Optional[str] = None,
        device: Optional[str] = None,
        batch_size: Optional[int] = None,
    ):
        self.model_name = model_name
        self.proxy = proxy if proxy is not None else settings.rag.embedding_proxy
        self.cache_dir = cache_dir if cache_dir is not None else settings.rag.embedding_cache_dir
        self.model_path = model_path if model_path is not None else settings.rag.embedding_model_path
        configured_local_only = settings.rag.embedding_local_files_only if local_files_only is None else bool(local_files_only)
        self.local_files_only = True if self.cache_dir else configured_local_only
        self.device = (device if device is not None else settings.rag.embedding_device) or "CPU"
        self.batch_size = max(1, int(batch_size if batch_size is not None else settings.rag.embedding_batch_size))

        try:
            import numpy as _np
            from optimum.intel import OVModelForFeatureExtraction as _OVModel
            from transformers import AutoTokenizer as _AutoTokenizer
        except Exception as error:
            raise RuntimeError(
                "optimum-intel backend selected but required packages are not available. "
                "Install with: pip install 'optimum[openvino]' numpy"
            ) from error

        self._np = _np
        model_source = self.model_path or self.model_name

        # If the directory already contains an OpenVINO IR file, skip export.
        export = True
        if self.model_path:
            import pathlib
            model_dir = pathlib.Path(self.model_path)
            if (model_dir / "openvino_model.xml").exists():
                export = False

        with _scoped_model_environment(
            self.proxy,
            self.cache_dir,
            self.local_files_only,
            settings.rag.openvino_cache_dir,
        ):
            self._tokenizer = _AutoTokenizer.from_pretrained(
                model_source,
                cache_dir=self.cache_dir,
                local_files_only=self.local_files_only,
            )
            self._model = _OVModel.from_pretrained(
                model_source,
                export=export,
                device=self.device.upper(),
                cache_dir=self.cache_dir,
            )

        logger.info(
            f"OptimumIntelEmbedder: model={model_source}, device={self.device.upper()}, export={export}"
        )

    def _mean_pool(self, last_hidden_state, attention_mask):
        mask_expanded = self._np.expand_dims(attention_mask, axis=-1)
        sum_embeddings = self._np.sum(last_hidden_state * mask_expanded, axis=1)
        sum_mask = self._np.clip(self._np.sum(mask_expanded, axis=1), a_min=1e-9, a_max=None)
        return sum_embeddings / sum_mask

    def _encode_batch(self, texts: List[str]) -> List[List[float]]:
        inputs = self._tokenizer(texts, padding=True, truncation=True, return_tensors="pt")
        with _scoped_model_environment(
            self.proxy,
            self.cache_dir,
            self.local_files_only,
            settings.rag.openvino_cache_dir,
        ):
            outputs = self._model(**inputs)
        token_embeddings = outputs.last_hidden_state.detach().numpy()
        attention_mask = inputs["attention_mask"].numpy()
        pooled = self._mean_pool(token_embeddings, attention_mask)
        return pooled.tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        vectors: List[List[float]] = []
        for index in range(0, len(texts), self.batch_size):
            vectors.extend(self._encode_batch(texts[index : index + self.batch_size]))
        return vectors

    def embed_query(self, text: str) -> List[float]:
        vectors = self.embed_documents([text])
        return vectors[0] if vectors else []
