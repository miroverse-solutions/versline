from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from loguru import logger

from versline.config import settings
from versline.services.pricing import TokenTracker
from versline.services.rag.base import BaseChunker, BaseEmbedder, BaseGenerator, BaseReranker, BaseWebSearcher, Chunk, RetrievedChunk
from versline.services.rag.chunkers import HierarchicalChunker, SlidingWindowChunker
from versline.services.rag.embedders import (
    FastEmbedDenseEmbedder,
    FastEmbedSparseEmbedder,
    FlagEmbeddingDenseEmbedder,
    FlagEmbeddingSparseEmbedder,
    OpenAICompatibleEmbedder,
    OptimumIntelEmbedder,
    SentenceTransformersSparseEmbedder,
    SentenceTransformersDenseEmbedder,
)
from versline.services.rag.generators import PromptRAGGenerator
from versline.services.rag.mcp_client import MCPClientConfig, MCPContextClient
from versline.services.rag.preprocessors import DEFAULT_EXTENSION_TO_INPUT_TYPE, MarkdownPreprocessor
from versline.services.rag.rerankers import CohereReranker, FastEmbedReranker, JinaReranker, OpenAICompatibleReranker, OptimumIntelReranker, SentenceTransformersReranker
from versline.services.rag.registry import PreprocessorRegistry, VectorStoreRegistry
from versline.services.rag.runtime import ProgressStateStore, RateLimiter, TokenRateLimiter
from versline.services.rag.vectorstores import QdrantVectorStore
from versline.services.rag.websearch import build_default_web_search_registry


class RAGPipeline:
    EMBEDDING_PROVIDER_SENTENCE_ALIASES = {
        "sentence-transformers",
        "sentence_transformers",
        "sentencetransformers",
        "sentence-transformer",
        "sentence",
    }

    @staticmethod
    def _normalized_proxy(proxy: Optional[str]) -> Optional[str]:
        if proxy is None:
            return None
        cleaned = str(proxy).strip()
        return cleaned or None

    @staticmethod
    def _parse_providers(raw: Optional[str]) -> List[str]:
        if raw is None:
            return []
        return [part.strip() for part in str(raw).split(",") if part.strip()]

    @staticmethod
    def _parse_delimiters(raw: Optional[str]) -> List[str]:
        if raw is None:
            return []
        if str(raw).strip().startswith("#"):
            return []
        delimiters: List[str] = []
        for part in str(raw).split(","):
            cleaned = part.strip()
            if not cleaned:
                continue
            delimiters.append(bytes(cleaned, "utf-8").decode("unicode_escape"))
        return delimiters

    @staticmethod
    def _with_openvino_provider_options(
        providers: List[str],
        *,
        device: Optional[str],
        cache_dir: Optional[str],
    ) -> List[Any]:
        normalized_device: Optional[str] = None
        if device:
            device_value = str(device).strip()
            low = device_value.lower()
            if low.startswith("cuda") or low.startswith("gpu"):
                normalized_device = "GPU"
            elif low.startswith("cpu"):
                normalized_device = "CPU"
            elif device_value:
                normalized_device = device_value

        resolved: List[Any] = []
        for provider in providers:
            if str(provider).strip().lower() != "openvinoexecutionprovider":
                resolved.append(provider)
                continue
            options: Dict[str, Any] = {}
            if normalized_device:
                options["device_type"] = normalized_device
            if cache_dir:
                options["cache_dir"] = str(cache_dir)
            resolved.append(("OpenVINOExecutionProvider", options) if options else "OpenVINOExecutionProvider")
        return resolved

    @classmethod
    def _resolve_sparse_provider(
        cls,
        requested_provider: Optional[str],
        *,
        dense_provider: str,
    ) -> str:
        provider = (requested_provider or "fastembed").strip().lower()
        if provider in {"auto", "same", "default"}:
            provider = dense_provider

        if provider == "flagembedding":
            return "flagembedding"
        if provider == "fastembed":
            return "fastembed"

        if provider in cls.EMBEDDING_PROVIDER_SENTENCE_ALIASES:
            return "sentence-transformers"

        if provider in {"openai", "openrouter", "avalai", "openaicompatible", "openvino", "optimum-intel", "optimum_intel", "optimum"}:
            logger.warning(
                f"Sparse provider '{requested_provider}' is mapped to fastembed because sparse embeddings are local lexical models."
            )
            return "fastembed"

        logger.warning(
            f"Unsupported sparse provider '{requested_provider}'. Falling back to fastembed for compatibility."
        )
        return "fastembed"

    @classmethod
    def _resolve_rerank_provider(
        cls,
        requested_provider: Optional[str],
        *,
        dense_provider: str,
    ) -> str:
        provider = (requested_provider or "cohere").strip().lower()
        if provider in {"auto", "same", "default"}:
            provider = dense_provider

        if provider == "flagembedding":
            logger.warning(
                "rerank_provider=flagembedding is mapped to sentence-transformers reranker for compatibility."
            )
            return "sentence-transformers"

        if provider in cls.EMBEDDING_PROVIDER_SENTENCE_ALIASES:
            return "sentence-transformers"

        return provider

    def __init__(
        self,
        chunker: Optional[BaseChunker] = None,
        embedder: Optional[BaseEmbedder] = None,
        sparse_embedder: Optional[Any] = None,
        reranker: Optional[BaseReranker] = None,
        mcp_client: Optional[Any] = None,
        web_searcher: Optional[BaseWebSearcher] = None,
        generator: Optional[BaseGenerator] = None,
        preprocessor_registry: Optional[PreprocessorRegistry] = None,
        vector_store_registry: Optional[VectorStoreRegistry] = None,
        vector_backend: Optional[str] = None,
        collection_name: Optional[str] = None,
        qdrant_url: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
        qdrant_distance: str = "cosine",
        embedding_model: Optional[str] = None,
        generation_model: Optional[str] = None,
        embedding_provider: Optional[str] = None,
        embedding_api_key: Optional[str] = None,
        embedding_api_endpoint: Optional[str] = None,
        embedding_model_path: Optional[str] = None,
        embedding_cache_dir: Optional[str] = None,
        embedding_local_files_only: Optional[bool] = None,
        embedding_use_fp16: Optional[bool] = None,
        embedding_device: Optional[str] = None,
        embedding_batch_size: Optional[int] = None,
        embedding_inference_backend: Optional[str] = None,
        sparse_embedding_proxy: Optional[str] = None,
        sparse_embedding_cache_dir: Optional[str] = None,
        sparse_embedding_local_files_only: Optional[bool] = None,
        sparse_embedding_provider: Optional[str] = None,
        sparse_embedding_model_path: Optional[str] = None,
        sparse_embedding_use_fp16: Optional[bool] = None,
        sparse_embedding_device: Optional[str] = None,
        sparse_embedding_batch_size: Optional[int] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        parent_child_enabled: Optional[bool] = None,
        parent_chunk_size: Optional[int] = None,
        parent_chunk_overlap: Optional[int] = None,
        parent_child_paragraph_mode: Optional[bool] = None,
        parent_chunk_delimiters: Optional[str] = None,
        child_chunk_delimiters: Optional[str] = None,
        parent_child_fetch_k: Optional[int] = None,
        ingestion_batch_size: Optional[int] = None,
        retrieve_fetch_k: Optional[int] = None,
        hybrid_enabled: Optional[bool] = None,
        hybrid_dense_weight: Optional[float] = None,
        hybrid_lexical_weight: Optional[float] = None,
        embedding_timeout_seconds: Optional[float] = None,
        generation_timeout_seconds: Optional[float] = None,
        qdrant_timeout_seconds: Optional[float] = None,
        rerank_timeout_seconds: Optional[float] = None,
        rerank_model_path: Optional[str] = None,
        rerank_cache_dir: Optional[str] = None,
        rerank_local_files_only: Optional[bool] = None,
        rerank_device: Optional[str] = None,
        rerank_batch_size: Optional[int] = None,
        rerank_inference_backend: Optional[str] = None,
        openvino_cache_dir: Optional[str] = None,
        preflight: Optional[bool] = None,
        preflight_network: Optional[bool] = None,
    ):
        if embedding_provider is not None:
            settings.rag.embedding_provider = embedding_provider
        if embedding_api_key is not None:
            settings.rag.embedding_api_key = embedding_api_key
        if embedding_api_endpoint is not None:
            settings.rag.embedding_api_endpoint = embedding_api_endpoint
        if embedding_model_path is not None:
            settings.rag.embedding_model_path = embedding_model_path
        if embedding_cache_dir is not None:
            settings.rag.embedding_cache_dir = embedding_cache_dir
        if embedding_local_files_only is not None:
            settings.rag.embedding_local_files_only = bool(embedding_local_files_only)
        if embedding_use_fp16 is not None:
            settings.rag.embedding_use_fp16 = bool(embedding_use_fp16)
        if embedding_device is not None:
            settings.rag.embedding_device = embedding_device
        if embedding_batch_size is not None:
            settings.rag.embedding_batch_size = int(embedding_batch_size)
        if embedding_inference_backend is not None:
            settings.rag.embedding_inference_backend = embedding_inference_backend
        if sparse_embedding_proxy is not None:
            settings.rag.sparse_embedding_proxy = sparse_embedding_proxy
        if sparse_embedding_cache_dir is not None:
            settings.rag.sparse_embedding_cache_dir = sparse_embedding_cache_dir
        if sparse_embedding_local_files_only is not None:
            settings.rag.sparse_embedding_local_files_only = sparse_embedding_local_files_only
        if sparse_embedding_provider is not None:
            settings.rag.sparse_embedding_provider = sparse_embedding_provider
        if sparse_embedding_model_path is not None:
            settings.rag.sparse_embedding_model_path = sparse_embedding_model_path
        if sparse_embedding_use_fp16 is not None:
            settings.rag.sparse_embedding_use_fp16 = sparse_embedding_use_fp16
        if sparse_embedding_device is not None:
            settings.rag.sparse_embedding_device = sparse_embedding_device
        if sparse_embedding_batch_size is not None:
            settings.rag.sparse_embedding_batch_size = int(sparse_embedding_batch_size)
        if chunk_size is not None:
            settings.rag.chunk_size = int(chunk_size)
        if chunk_overlap is not None:
            settings.rag.chunk_overlap = int(chunk_overlap)
        if parent_child_enabled is not None:
            settings.rag.parent_child_enabled = bool(parent_child_enabled)
        if parent_chunk_size is not None:
            settings.rag.parent_chunk_size = int(parent_chunk_size)
        if parent_chunk_overlap is not None:
            settings.rag.parent_chunk_overlap = int(parent_chunk_overlap)
        if parent_child_paragraph_mode is not None:
            settings.rag.parent_child_paragraph_mode = bool(parent_child_paragraph_mode)
        if parent_chunk_delimiters is not None:
            settings.rag.parent_chunk_delimiters = parent_chunk_delimiters
        if child_chunk_delimiters is not None:
            settings.rag.child_chunk_delimiters = child_chunk_delimiters
        if parent_child_fetch_k is not None:
            settings.rag.parent_child_fetch_k = int(parent_child_fetch_k)
        if ingestion_batch_size is not None:
            settings.rag.ingestion_batch_size = int(ingestion_batch_size)
        if retrieve_fetch_k is not None:
            settings.rag.retrieve_fetch_k = int(retrieve_fetch_k)
        if hybrid_enabled is not None:
            settings.rag.hybrid_enabled = bool(hybrid_enabled)
        if hybrid_dense_weight is not None:
            settings.rag.hybrid_dense_weight = float(hybrid_dense_weight)
        if hybrid_lexical_weight is not None:
            settings.rag.hybrid_lexical_weight = float(hybrid_lexical_weight)
        if embedding_timeout_seconds is not None:
            settings.rag.embedding_timeout_seconds = float(embedding_timeout_seconds)
        if generation_timeout_seconds is not None:
            settings.rag.generation_timeout_seconds = float(generation_timeout_seconds)
        if qdrant_timeout_seconds is not None:
            settings.rag.qdrant_timeout_seconds = float(qdrant_timeout_seconds)
        if rerank_timeout_seconds is not None:
            settings.rag.rerank_timeout_seconds = float(rerank_timeout_seconds)
        if rerank_model_path is not None:
            settings.rag.rerank_model_path = rerank_model_path
        if rerank_cache_dir is not None:
            settings.rag.rerank_cache_dir = rerank_cache_dir
        if rerank_local_files_only is not None:
            settings.rag.rerank_local_files_only = bool(rerank_local_files_only)
        if rerank_device is not None:
            settings.rag.rerank_device = rerank_device
        if rerank_batch_size is not None:
            settings.rag.rerank_batch_size = int(rerank_batch_size)
        if rerank_inference_backend is not None:
            settings.rag.rerank_inference_backend = rerank_inference_backend
        if openvino_cache_dir is not None:
            settings.rag.openvino_cache_dir = openvino_cache_dir

        resolved_backend_for_preflight = (vector_backend or settings.rag.vector_backend).lower()
        require_llm_api_keys = bool(embedder is None or generator is None or (settings.rag.rerank_enabled and reranker is None))
        require_web_api_keys = bool(settings.rag.web_search_enabled and web_searcher is None)

        should_preflight = settings.rag.preflight_enabled if preflight is None else bool(preflight)
        should_preflight_network = settings.rag.preflight_network if preflight_network is None else bool(preflight_network)
        if should_preflight:
            preflight_result = self._validate_initial_configuration(
                check_network=should_preflight_network,
                vector_backend=resolved_backend_for_preflight,
                require_llm_api_keys=require_llm_api_keys,
                require_web_api_keys=require_web_api_keys,
                timeout_seconds=min(
                    float(settings.rag.qdrant_timeout_seconds or 20.0),
                    float(settings.rag.web_search_timeout_seconds or 15.0),
                ),
            )
            for warning in preflight_result.get("warnings", []):
                logger.warning(warning)

        self.tracker = TokenTracker()
        self.embedding_rate_limiter = RateLimiter(settings.rag.rate_limit_embedding_rpm)
        self.embedding_token_rate_limiter = TokenRateLimiter(settings.rag.rate_limit_embedding_tpm)
        self.generation_rate_limiter = RateLimiter(settings.rag.rate_limit_generation_rpm)
        self.generation_token_rate_limiter = TokenRateLimiter(settings.rag.rate_limit_generation_tpm)
        self.qdrant_rate_limiter = RateLimiter(settings.rag.rate_limit_qdrant_rpm)
        self.rerank_rate_limiter = RateLimiter(settings.rag.rate_limit_rerank_rpm)
        self.rerank_token_rate_limiter = TokenRateLimiter(settings.rag.rate_limit_rerank_tpm)

        self.parent_child_enabled = bool(settings.rag.parent_child_enabled)
        if chunker is not None:
            self.chunker = chunker
        elif self.parent_child_enabled:
            self.chunker = HierarchicalChunker(
                parent_chunk_size=settings.rag.parent_chunk_size,
                parent_overlap=settings.rag.parent_chunk_overlap,
                child_chunk_size=settings.rag.chunk_size,
                child_overlap=settings.rag.chunk_overlap,
                paragraph_mode=bool(settings.rag.parent_child_paragraph_mode),
                parent_delimiters=self._parse_delimiters(settings.rag.parent_chunk_delimiters),
                child_delimiters=self._parse_delimiters(settings.rag.child_chunk_delimiters),
            )
        else:
            self.chunker = SlidingWindowChunker(
                chunk_size=settings.rag.chunk_size,
                overlap=settings.rag.chunk_overlap,
            )
        dense_provider = (settings.rag.embedding_provider or "openai").lower()
        dense_inference_backend = (settings.rag.embedding_inference_backend or "auto").lower()
        if embedder is not None:
            self.embedder = embedder
        else:
            dense_model = embedding_model or settings.rag.embedding_model
            sentence_embedding_aliases = self.EMBEDDING_PROVIDER_SENTENCE_ALIASES
            if dense_provider == "openvino":
                logger.warning(
                    "embedding_provider=openvino is treated as sentence-transformers with OpenVINO backend. "
                    "Prefer embedding_provider=sentence-transformers plus embedding_inference_backend=openvino."
                )
                dense_provider = "sentence-transformers"
                dense_inference_backend = "openvino"

            if dense_inference_backend == "openvino" and dense_provider not in sentence_embedding_aliases:
                logger.warning(
                    f"Embedding backend openvino is not supported for provider '{dense_provider}' and will be ignored. "
                    "Use sentence-transformers provider to enable OpenVINO."
                )

            if dense_provider in {"openai", "openrouter", "avalai", "openaicompatible"}:
                self.embedder = OpenAICompatibleEmbedder(
                    model=dense_model,
                    provider=dense_provider,
                    rate_limiter=self.embedding_rate_limiter,
                    token_rate_limiter=self.embedding_token_rate_limiter,
                    tracker=self.tracker,
                )
            elif dense_provider == "fastembed":
                dense_fastembed_providers = self._parse_providers(settings.rag.embedding_onnx_providers)
                if dense_inference_backend == "openvino" and not dense_fastembed_providers:
                    dense_fastembed_providers = ["OpenVINOExecutionProvider", "CPUExecutionProvider"]
                if dense_inference_backend == "openvino":
                    dense_fastembed_providers = self._with_openvino_provider_options(
                        dense_fastembed_providers,
                        device=settings.rag.embedding_device,
                        cache_dir=settings.rag.openvino_cache_dir,
                    )
                self.embedder = FastEmbedDenseEmbedder(
                    model_name=dense_model,
                    proxy=settings.rag.embedding_proxy,
                    cache_dir=settings.rag.embedding_cache_dir,
                    local_files_only=settings.rag.embedding_local_files_only,
                    providers=dense_fastembed_providers,
                )
            elif dense_provider in sentence_embedding_aliases:
                self.embedder = SentenceTransformersDenseEmbedder(
                    model_name=dense_model,
                    proxy=settings.rag.embedding_proxy,
                    cache_dir=settings.rag.embedding_cache_dir,
                    local_files_only=settings.rag.embedding_local_files_only,
                    model_path=settings.rag.embedding_model_path,
                    device=settings.rag.embedding_device,
                    batch_size=settings.rag.embedding_batch_size,
                    inference_backend=dense_inference_backend,
                )
            elif dense_provider == "flagembedding":
                self.embedder = FlagEmbeddingDenseEmbedder(
                    model_name=dense_model,
                    proxy=settings.rag.embedding_proxy,
                    cache_dir=settings.rag.embedding_cache_dir,
                    local_files_only=settings.rag.embedding_local_files_only,
                    model_path=settings.rag.embedding_model_path,
                    use_fp16=settings.rag.embedding_use_fp16,
                    device=settings.rag.embedding_device,
                    batch_size=settings.rag.embedding_batch_size,
                )
            elif dense_provider in {"optimum-intel", "optimum_intel", "optimum"}:
                self.embedder = OptimumIntelEmbedder(
                    model_name=dense_model,
                    proxy=settings.rag.embedding_proxy,
                    cache_dir=settings.rag.embedding_cache_dir,
                    local_files_only=settings.rag.embedding_local_files_only,
                    model_path=settings.rag.embedding_model_path,
                    device=settings.rag.embedding_device,
                    batch_size=settings.rag.embedding_batch_size,
                )
            else:
                raise ValueError(
                    "Unsupported dense embedding provider: "
                    f"{dense_provider}. Supported providers: openai, openrouter, avalai, openaicompatible, fastembed, sentence-transformers (aliases: sentence, sentence_transformers), flagembedding, optimum-intel, openvino"
                )
        self.sparse_embedder = sparse_embedder
        if self.sparse_embedder is None and settings.rag.hybrid_enabled:
            try:
                sparse_provider = self._resolve_sparse_provider(
                    settings.rag.sparse_embedding_provider,
                    dense_provider=dense_provider,
                )
                if sparse_provider == "flagembedding":
                    self.sparse_embedder = FlagEmbeddingSparseEmbedder(
                        settings.rag.sparse_embedding_model,
                        proxy=settings.rag.sparse_embedding_proxy or settings.rag.embedding_proxy,
                        cache_dir=settings.rag.sparse_embedding_cache_dir,
                        local_files_only=settings.rag.sparse_embedding_local_files_only,
                        model_path=settings.rag.sparse_embedding_model_path,
                        use_fp16=settings.rag.sparse_embedding_use_fp16,
                        device=settings.rag.sparse_embedding_device,
                        batch_size=settings.rag.sparse_embedding_batch_size,
                    )
                elif sparse_provider in self.EMBEDDING_PROVIDER_SENTENCE_ALIASES:
                    self.sparse_embedder = SentenceTransformersSparseEmbedder(
                        settings.rag.sparse_embedding_model,
                        proxy=settings.rag.sparse_embedding_proxy or settings.rag.embedding_proxy,
                        cache_dir=settings.rag.sparse_embedding_cache_dir,
                        local_files_only=settings.rag.sparse_embedding_local_files_only,
                        model_path=settings.rag.sparse_embedding_model_path,
                        device=settings.rag.sparse_embedding_device,
                        batch_size=settings.rag.sparse_embedding_batch_size,
                    )
                else:
                    sparse_fastembed_providers = self._parse_providers(settings.rag.sparse_embedding_onnx_providers)
                    if dense_inference_backend == "openvino" and not sparse_fastembed_providers:
                        sparse_fastembed_providers = ["OpenVINOExecutionProvider", "CPUExecutionProvider"]
                    if dense_inference_backend == "openvino":
                        sparse_fastembed_providers = self._with_openvino_provider_options(
                            sparse_fastembed_providers,
                            device=settings.rag.sparse_embedding_device,
                            cache_dir=settings.rag.openvino_cache_dir,
                        )
                    self.sparse_embedder = FastEmbedSparseEmbedder(
                        settings.rag.sparse_embedding_model,
                        proxy=settings.rag.sparse_embedding_proxy or settings.rag.embedding_proxy,
                        cache_dir=settings.rag.sparse_embedding_cache_dir,
                        local_files_only=settings.rag.sparse_embedding_local_files_only,
                        providers=sparse_fastembed_providers,
                    )
            except Exception as error:
                raise RuntimeError(
                    "Failed to initialize sparse hybrid model. "
                    "In offline environments either disable hybrid retrieval "
                    "(VERSLINE_RAG_HYBRID_ENABLED=false) or pre-download sparse model artifacts. "
                    f"Original error: {error}"
                ) from error
        self.generator = generator or PromptRAGGenerator(
            model=generation_model or settings.llm.model,
            prompt_file=settings.rag.generation_prompt_file,
            rate_limiter=self.generation_rate_limiter,
            token_rate_limiter=self.generation_token_rate_limiter,
            tracker=self.tracker,
        )
        self.reranker = reranker
        if self.reranker is None and settings.rag.rerank_enabled:
            provider = self._resolve_rerank_provider(
                settings.rag.rerank_provider,
                dense_provider=dense_provider,
            )
            rerank_inference_backend = (settings.rag.rerank_inference_backend or "auto").lower()
            sentence_rerank_aliases = self.EMBEDDING_PROVIDER_SENTENCE_ALIASES
            if provider == "openvino":
                logger.warning(
                    "rerank_provider=openvino is treated as sentence-transformers with OpenVINO backend. "
                    "Prefer rerank_provider=sentence-transformers plus rerank_inference_backend=openvino."
                )
                provider = "sentence-transformers"
                rerank_inference_backend = "openvino"

            if rerank_inference_backend == "openvino" and provider not in sentence_rerank_aliases and provider not in {"local", "fastembed"}:
                logger.warning(
                    f"Rerank backend openvino is not supported for provider '{provider}' and will be ignored. "
                    "Use local or sentence-transformers rerank provider to enable OpenVINO."
                )

            if provider == "cohere":
                self.reranker = CohereReranker(
                    model=settings.rag.rerank_model,
                    rate_limiter=self.rerank_rate_limiter,
                    token_rate_limiter=self.rerank_token_rate_limiter,
                )
            elif provider == "jina":
                self.reranker = JinaReranker(
                    model=settings.rag.rerank_model,
                    rate_limiter=self.rerank_rate_limiter,
                    token_rate_limiter=self.rerank_token_rate_limiter,
                )
            elif provider in {"openai", "openrouter", "avalai", "openaicompatible", "local"}:
                use_local_model_files = bool(
                    provider == "local"
                    and (
                        settings.rag.rerank_model_path
                        or settings.rag.rerank_cache_dir
                        or settings.rag.rerank_local_files_only
                    )
                )
                if use_local_model_files:
                    self.reranker = SentenceTransformersReranker(
                        model=settings.rag.rerank_model,
                        proxy=settings.rag.rerank_proxy,
                        cache_dir=settings.rag.rerank_cache_dir,
                        local_files_only=settings.rag.rerank_local_files_only,
                        model_path=settings.rag.rerank_model_path,
                        device=settings.rag.rerank_device,
                        batch_size=settings.rag.rerank_batch_size,
                        inference_backend=rerank_inference_backend,
                        rate_limiter=self.rerank_rate_limiter,
                        token_rate_limiter=self.rerank_token_rate_limiter,
                    )
                else:
                    self.reranker = OpenAICompatibleReranker(
                        model=settings.rag.rerank_model,
                        rate_limiter=self.rerank_rate_limiter,
                        token_rate_limiter=self.rerank_token_rate_limiter,
                        tracker=self.tracker,
                    )
            elif provider == "fastembed":
                rerank_fastembed_providers = self._parse_providers(settings.rag.rerank_onnx_providers)
                if rerank_inference_backend == "openvino" and not rerank_fastembed_providers:
                    rerank_fastembed_providers = ["OpenVINOExecutionProvider", "CPUExecutionProvider"]
                if rerank_inference_backend == "openvino":
                    rerank_fastembed_providers = self._with_openvino_provider_options(
                        rerank_fastembed_providers,
                        device=settings.rag.rerank_device,
                        cache_dir=settings.rag.openvino_cache_dir,
                    )
                self.reranker = FastEmbedReranker(
                    model=settings.rag.rerank_model,
                    proxy=settings.rag.rerank_proxy,
                    cache_dir=settings.rag.rerank_cache_dir,
                    local_files_only=settings.rag.rerank_local_files_only,
                    providers=rerank_fastembed_providers,
                    rate_limiter=self.rerank_rate_limiter,
                    token_rate_limiter=self.rerank_token_rate_limiter,
                )
            elif provider in sentence_rerank_aliases:
                self.reranker = SentenceTransformersReranker(
                    model=settings.rag.rerank_model,
                    proxy=settings.rag.rerank_proxy,
                    cache_dir=settings.rag.rerank_cache_dir,
                    local_files_only=settings.rag.rerank_local_files_only,
                    model_path=settings.rag.rerank_model_path,
                    device=settings.rag.rerank_device,
                    batch_size=settings.rag.rerank_batch_size,
                    inference_backend=rerank_inference_backend,
                    rate_limiter=self.rerank_rate_limiter,
                    token_rate_limiter=self.rerank_token_rate_limiter,
                )
            elif provider in {"optimum-intel", "optimum_intel", "optimum"}:
                self.reranker = OptimumIntelReranker(
                    model=settings.rag.rerank_model,
                    proxy=settings.rag.rerank_proxy,
                    cache_dir=settings.rag.rerank_cache_dir,
                    local_files_only=settings.rag.rerank_local_files_only,
                    model_path=settings.rag.rerank_model_path,
                    device=settings.rag.rerank_device,
                    batch_size=settings.rag.rerank_batch_size,
                    rate_limiter=self.rerank_rate_limiter,
                    token_rate_limiter=self.rerank_token_rate_limiter,
                )
            else:
                logger.warning(f"Unsupported rerank provider: {provider}. Reranking disabled.")

        self.mcp_client = mcp_client
        if self.mcp_client is None and settings.rag.mcp_enabled:
            self.mcp_client = MCPContextClient(
                MCPClientConfig(
                    transport=settings.rag.mcp_transport,
                    tool_name=settings.rag.mcp_tool_name,
                    timeout_seconds=settings.rag.mcp_timeout_seconds,
                    max_context_chars=settings.rag.mcp_max_context_chars,
                    server_url=settings.rag.mcp_server_url,
                    server_command=settings.rag.mcp_server_command,
                    server_args=settings.rag.mcp_server_args,
                    proxy=settings.rag.mcp_proxy,
                )
            )

        self.web_searcher = web_searcher
        if self.web_searcher is None and settings.rag.web_search_enabled:
            provider = (settings.rag.web_search_provider or "duckduckgo").lower()
            registry = build_default_web_search_registry()
            try:
                if provider == "tavily":
                    api_key = settings.rag.web_search_api_key
                    if not api_key:
                        logger.warning("Web search provider 'tavily' selected without API key; web search disabled.")
                    else:
                        self.web_searcher = registry.create(
                            provider,
                            api_key=api_key,
                            endpoint=settings.rag.web_search_endpoint,
                            proxy=settings.rag.web_search_proxy,
                            timeout_seconds=settings.rag.web_search_timeout_seconds,
                        )
                else:
                    self.web_searcher = registry.create(
                        provider,
                        endpoint=settings.rag.web_search_endpoint,
                        proxy=settings.rag.web_search_proxy,
                        timeout_seconds=settings.rag.web_search_timeout_seconds,
                    )
            except Exception as error:
                logger.warning(f"Web search initialization failed: {error}")

        self.preprocessors = preprocessor_registry or PreprocessorRegistry()
        self.preprocessors.register("markdown", MarkdownPreprocessor())

        self.vector_stores = vector_store_registry or VectorStoreRegistry()
        self.vector_backend = (vector_backend or settings.rag.vector_backend).lower()

        if self.vector_backend == "qdrant":
            self.vector_stores.register(
                "qdrant",
                QdrantVectorStore(
                    url=qdrant_url or settings.rag.qdrant_url,
                    api_key=qdrant_api_key or settings.rag.qdrant_api_key,
                    distance=qdrant_distance or settings.rag.qdrant_distance,
                    rate_limiter=self.qdrant_rate_limiter,
                ),
            )

        self.collection_name = collection_name or settings.rag.collection_name
        self._active_store = self.vector_stores.get(self.vector_backend)

    def _validate_initial_configuration(
        self,
        *,
        check_network: bool,
        vector_backend: str,
        require_llm_api_keys: bool,
        require_web_api_keys: bool,
        timeout_seconds: float,
    ) -> Dict[str, Any]:
        errors: List[str] = []
        warnings: List[str] = []

        provider = (settings.llm.provider or "").lower()
        embedding_provider = (settings.rag.embedding_provider or provider or "openai").lower()
        if require_llm_api_keys:
            if provider in {"openai", "openrouter", "avalai", "openaicompatible", "google", "gemini"}:
                if not settings.llm.api_key:
                    errors.append(f"Missing API key for provider '{settings.llm.provider}'.")
            if embedding_provider in {"openai", "openrouter", "avalai", "openaicompatible"}:
                if not (settings.rag.embedding_api_key or settings.llm.api_key):
                    errors.append("Missing embedding API key (VERSLINE_RAG_EMBEDDING_API_KEY or VERSLINE_LLM_API_KEY).")

        if vector_backend == "qdrant" and not settings.rag.qdrant_url:
            errors.append("Missing VERSLINE_RAG_QDRANT_URL while vector backend is qdrant.")

        if require_web_api_keys and settings.rag.web_search_enabled:
            web_provider = (settings.rag.web_search_provider or "duckduckgo").lower()
            if web_provider == "tavily" and not settings.rag.web_search_api_key:
                errors.append("Web search provider tavily requires VERSLINE_RAG_WEB_SEARCH_API_KEY.")

        if settings.rag.token_limit_mode not in {"estimate_only", "estimate_and_adjust"}:
            errors.append("VERSLINE_RAG_TOKEN_LIMIT_MODE must be estimate_only or estimate_and_adjust.")

        if check_network and vector_backend == "qdrant":
            qdrant_ready_url = settings.rag.qdrant_url.rstrip("/") + "/readyz"
            try:
                with httpx.Client(proxy=self._normalized_proxy(settings.rag.qdrant_proxy), timeout=timeout_seconds) as client:
                    response = client.get(qdrant_ready_url)
                if response.status_code >= 400:
                    errors.append(
                        f"Qdrant preflight failed: {qdrant_ready_url} returned status {response.status_code}."
                    )
            except Exception as error:
                errors.append(f"Qdrant preflight failed: cannot reach {qdrant_ready_url} ({error}).")

        if check_network and settings.rag.web_search_enabled and require_web_api_keys:
            web_provider = (settings.rag.web_search_provider or "duckduckgo").lower()
            if web_provider == "duckduckgo":
                endpoint = (settings.rag.web_search_endpoint or "https://api.duckduckgo.com/").strip()
                try:
                    with httpx.Client(proxy=self._normalized_proxy(settings.rag.web_search_proxy), timeout=timeout_seconds) as client:
                        response = client.get(endpoint, params={"q": "test", "format": "json"})
                    if response.status_code >= 400:
                        warnings.append(
                            f"DuckDuckGo preflight warning: endpoint returned status {response.status_code}."
                        )
                except Exception as error:
                    warnings.append(f"DuckDuckGo preflight warning: endpoint is not reachable ({error}).")

        if errors:
            raise ValueError("RAG preflight failed:\n- " + "\n- ".join(errors))
        return {"ok": True, "warnings": warnings}

    def validate_configuration(
        self,
        *,
        check_network: bool = False,
        timeout_seconds: float = 3.0,
    ) -> Dict[str, Any]:
        backend = (self.vector_backend or settings.rag.vector_backend).lower()
        require_llm_api_keys = isinstance(self.embedder, OpenAICompatibleEmbedder) or isinstance(self.generator, PromptRAGGenerator)
        require_web_api_keys = bool(settings.rag.web_search_enabled and self.web_searcher is not None)
        return self._validate_initial_configuration(
            check_network=check_network,
            vector_backend=backend,
            require_llm_api_keys=require_llm_api_keys,
            require_web_api_keys=require_web_api_keys,
            timeout_seconds=timeout_seconds,
        )

    def register_preprocessor(self, input_type: str, preprocessor) -> None:
        self.preprocessors.register(input_type=input_type, preprocessor=preprocessor)

    def register_vector_store(self, backend_type: str, store) -> None:
        self.vector_stores.register(backend_type=backend_type, store=store)

    def _resolve_input_type(self, file_path: str, input_type: Optional[str] = None) -> str:
        if input_type:
            return input_type.lower()
        suffix = Path(file_path).suffix.lower()
        if suffix in DEFAULT_EXTENSION_TO_INPUT_TYPE:
            return DEFAULT_EXTENSION_TO_INPUT_TYPE[suffix]
        raise ValueError(
            f"Unsupported file extension '{suffix}'. Provide explicit input_type and matching preprocessor."
        )

    def _lexical_score(self, query: str, text: str) -> float:
        query_terms = [item for item in query.lower().split() if item]
        if not query_terms:
            return 0.0
        text_terms = text.lower().split()
        if not text_terms:
            return 0.0

        text_len = len(text_terms)
        score = 0.0
        for term in query_terms:
            tf = text_terms.count(term)
            if tf > 0:
                score += (tf / max(1, text_len)) * (1.0 + math.log(1.0 + tf))
        return score

    def _hybrid_rank(self, query: str, items: List[RetrievedChunk], top_k: int) -> List[RetrievedChunk]:
        if not items:
            return []

        dense_max = max((item.score for item in items), default=1.0) or 1.0
        lexical_scores = [self._lexical_score(query, item.text) for item in items]
        lexical_max = max(lexical_scores, default=1.0) or 1.0

        dense_weight = settings.rag.hybrid_dense_weight
        lexical_weight = settings.rag.hybrid_lexical_weight

        ranked: List[Tuple[float, RetrievedChunk]] = []
        for item, lexical in zip(items, lexical_scores):
            dense_component = float(item.score) / dense_max
            lexical_component = float(lexical) / lexical_max if lexical_max > 0 else 0.0
            hybrid_score = (dense_weight * dense_component) + (lexical_weight * lexical_component)
            ranked.append((hybrid_score, item))

        ranked.sort(key=lambda entry: entry[0], reverse=True)
        return [entry[1] for entry in ranked[:top_k]]

    def _iter_input_files(self, input_path: str, input_type: Optional[str]) -> List[Path]:
        path = Path(input_path)
        if path.is_file():
            return [path]

        if not path.is_dir():
            raise ValueError(f"Input path does not exist: {input_path}")

        allowed_ext = set(DEFAULT_EXTENSION_TO_INPUT_TYPE.keys())
        files = [
            child for child in sorted(path.rglob("*"))
            if child.is_file() and (input_type is not None or child.suffix.lower() in allowed_ext)
        ]
        if not files:
            raise ValueError("No supported files found in input directory")
        return files

    def _state_store(self, source_file: Path, collection_name: str) -> ProgressStateStore:
        signature_payload = {
            "source": str(source_file.resolve()),
            "collection": collection_name,
            "chunk_size": settings.rag.chunk_size,
            "chunk_overlap": settings.rag.chunk_overlap,
            "parent_child_enabled": bool(settings.rag.parent_child_enabled),
            "parent_chunk_size": settings.rag.parent_chunk_size,
            "parent_chunk_overlap": settings.rag.parent_chunk_overlap,
            "parent_child_paragraph_mode": bool(settings.rag.parent_child_paragraph_mode),
            "parent_chunk_delimiters": settings.rag.parent_chunk_delimiters,
            "child_chunk_delimiters": settings.rag.child_chunk_delimiters,
            "embedding_model": settings.rag.embedding_model,
        }
        raw = json.dumps(signature_payload, ensure_ascii=False, sort_keys=True)
        signature = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        state_dir = settings.rag.state_directory / source_file.stem
        return ProgressStateStore(state_file=state_dir / f"rag_ingest_{signature}.json")

    def _merge_filters(
        self,
        base_filters: Optional[Dict[str, Any]],
        extra_filters: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not base_filters and not extra_filters:
            return None
        merged = dict(base_filters or {})
        merged.update(extra_filters or {})
        return merged

    def _upsert_chunk_batch(self, collection_name: str, batch_chunks: List[Chunk]) -> None:
        dense_vectors = self.embedder.embed_documents([item.text for item in batch_chunks])
        if (
            settings.rag.hybrid_enabled
            and self.sparse_embedder is not None
            and hasattr(self._active_store, "upsert_hybrid")
        ):
            sparse_vectors = self.sparse_embedder.embed_documents([item.text for item in batch_chunks])
            self._active_store.upsert_hybrid(
                collection_name,
                chunks=batch_chunks,
                dense_vectors=dense_vectors,
                sparse_vectors=sparse_vectors,
            )
        else:
            self._active_store.upsert(collection_name, chunks=batch_chunks, vectors=dense_vectors)

    def _prepare_parent_child_chunks(self, documents: List[Any]) -> Tuple[List[Chunk], List[Chunk]]:
        if hasattr(self.chunker, "chunk_with_parents"):
            parent_chunks, child_chunks = self.chunker.chunk_with_parents(documents)
            return list(parent_chunks), list(child_chunks)

        child_chunks = self.chunker.chunk(documents)
        return [], child_chunks

    def _retrieve_parent_expanded(
        self,
        *,
        query: str,
        active_collection: str,
        query_vector: List[float],
        top_k: int,
        fetch_k: int,
        candidate_top_k: int,
        filters: Optional[Dict[str, Any]],
        rerank_enabled: bool,
    ) -> List[RetrievedChunk]:
        child_filters = self._merge_filters(filters, {"chunk_level": "child"})
        child_fetch_k = max(fetch_k, int(settings.rag.parent_child_fetch_k or fetch_k))
        child_top_k = max(candidate_top_k, child_fetch_k)

        child_hits: List[RetrievedChunk] = []
        if (
            settings.rag.hybrid_enabled
            and self.sparse_embedder is not None
            and hasattr(self._active_store, "search_hybrid")
        ):
            sparse_query = self.sparse_embedder.embed_query(query)
            child_hits = self._active_store.search_hybrid(
                collection_name=active_collection,
                dense_query_vector=query_vector,
                sparse_query_vector=sparse_query,
                top_k=child_top_k,
                filters=child_filters,
                fetch_k=child_fetch_k,
            )

        if not child_hits:
            child_hits = self._active_store.search(
                collection_name=active_collection,
                query_vector=query_vector,
                top_k=child_top_k,
                filters=child_filters,
            )

        if not child_hits:
            return []

        parent_scores: Dict[str, float] = {}
        parent_hits: Dict[str, List[RetrievedChunk]] = {}
        for child in child_hits:
            parent_id = str(child.metadata.get("parent_id", "")).strip()
            if not parent_id:
                continue
            score = float(child.score)
            if parent_id not in parent_scores or score > parent_scores[parent_id]:
                parent_scores[parent_id] = score
            parent_hits.setdefault(parent_id, []).append(child)

        if not parent_scores:
            return child_hits[:top_k]

        ranked_parent_ids = [
            item[0]
            for item in sorted(parent_scores.items(), key=lambda item: item[1], reverse=True)[:child_top_k]
        ]

        parent_chunks: List[RetrievedChunk] = []
        if hasattr(self._active_store, "get_by_ids"):
            try:
                parent_chunks = self._active_store.get_by_ids(active_collection, ranked_parent_ids)
            except Exception as error:
                logger.warning(f"Parent expansion by ids failed. Falling back to child chunks: {error}")

        if not parent_chunks:
            return child_hits[:top_k]

        expanded: List[RetrievedChunk] = []
        for item in parent_chunks:
            parent_id = str(item.id)
            score = parent_scores.get(parent_id, 0.0)
            supporting_children = sorted(
                parent_hits.get(parent_id, []),
                key=lambda hit: float(hit.score),
                reverse=True,
            )[:3]
            merged_metadata = dict(item.metadata)
            merged_metadata["matched_children"] = [
                {
                    "id": child.id,
                    "score": float(child.score),
                    "char_start": child.metadata.get("char_start"),
                    "char_end": child.metadata.get("char_end"),
                }
                for child in supporting_children
            ]
            expanded.append(
                RetrievedChunk(
                    id=item.id,
                    text=item.text,
                    score=score,
                    metadata=merged_metadata,
                )
            )

        expanded.sort(key=lambda item: float(item.score), reverse=True)
        if rerank_enabled:
            return self.reranker.rerank(query=query, items=expanded, top_k=top_k)
        return expanded[:top_k]

    def ingest_path(
        self,
        input_path: str,
        input_type: Optional[str] = None,
        collection_name: Optional[str] = None,
        reset_collection: bool = False,
        resume: bool = True,
        force: bool = False,
        progress_callback=None,
    ) -> Dict[str, Any]:
        active_collection = collection_name or self.collection_name
        files = self._iter_input_files(input_path, input_type)
        logger.info(f"RAG ingest started: files={len(files)}, collection={active_collection}")

        total_chunks = 0
        total_parent_chunks = 0
        total_child_chunks = 0
        total_docs = 0
        indexed_files = 0
        collection_reset_done = False

        for file_index, file_path in enumerate(files, start=1):
            logger.info(f"Preparing file {file_index}/{len(files)}: {file_path}")
            if progress_callback:
                progress_callback(file_index - 1, len(files), f"Preparing {file_path.name}...")
            resolved_input_type = self._resolve_input_type(str(file_path), input_type)
            preprocessor = self.preprocessors.get(resolved_input_type)

            documents = preprocessor.preprocess(str(file_path))
            parent_chunks, chunks = ([], self.chunker.chunk(documents))
            if self.parent_child_enabled:
                parent_chunks, chunks = self._prepare_parent_child_chunks(documents)
            total_docs += len(documents)

            if progress_callback and chunks:
                progress_callback(
                    file_index - 1,
                    len(files),
                    (
                        f"Prepared {file_path.name}: {len(chunks)} chunks"
                        if not self.parent_child_enabled
                        else f"Prepared {file_path.name}: {len(parent_chunks)} parent + {len(chunks)} child chunks"
                    ),
                )

            if not chunks:
                if progress_callback:
                    progress_callback(file_index, len(files), f"Skipping empty file: {file_path.name}")
                continue

            vectors_probe = self.embedder.embed_documents([chunks[0].text])
            if not vectors_probe:
                raise RuntimeError("Embedding model returned empty vectors")
            inferred_vector_size = len(vectors_probe[0])
            configured_vector_size = settings.rag.vector_size
            if configured_vector_size is not None:
                vector_size = int(configured_vector_size)
                if vector_size != inferred_vector_size:
                    raise ValueError(
                        "Configured vector_size does not match embedding output dimension: "
                        f"configured={vector_size}, inferred={inferred_vector_size}. "
                        "Update VERSLINE_RAG_VECTOR_SIZE / --vector-size or switch embedding model."
                    )
            else:
                vector_size = inferred_vector_size

            if reset_collection and not collection_reset_done:
                self._active_store.reset_collection(active_collection)
                collection_reset_done = True

            self._active_store.ensure_collection(active_collection, vector_size=vector_size)

            store = self._state_store(file_path, active_collection)
            state = store.load() if resume else {}
            if force:
                state = {}

            batch_size = max(1, settings.rag.ingestion_batch_size)
            if self.parent_child_enabled:
                if state.get("mode") != "parent_child":
                    state = {}

                completed_parent = int(state.get("completed_parent_chunks", 0)) if resume else 0
                completed_child = int(state.get("completed_child_chunks", 0)) if resume else 0
                total_units = max(1, len(parent_chunks) + len(chunks))

                if progress_callback and (completed_parent > 0 or completed_child > 0):
                    resumed = completed_parent + completed_child
                    progress_callback(
                        file_index - 1 + (resumed / total_units),
                        len(files),
                        (
                            f"Resuming {file_path.name}: "
                            f"parents {completed_parent}/{len(parent_chunks)}, children {completed_child}/{len(chunks)}"
                        ),
                    )

                for start in range(completed_parent, len(parent_chunks), batch_size):
                    end = min(start + batch_size, len(parent_chunks))
                    batch_chunks = parent_chunks[start:end]
                    batch_number = (start // batch_size) + 1
                    total_batches = (len(parent_chunks) + batch_size - 1) // batch_size
                    log_every = max(1, int(settings.rag.log_every_batches or 1))
                    if progress_callback:
                        progress_callback(
                            file_index - 1 + (start / total_units),
                            len(files),
                            (
                                f"Embedding parent chunks {file_path.name}: "
                                f"batch {batch_number}/{max(1, total_batches)} (chunks {start + 1}-{end})"
                            ),
                        )
                    if batch_number == 1 or batch_number % log_every == 0 or end == len(parent_chunks):
                        logger.info(
                            "Sending parent ingest batch "
                            f"{batch_number}/{max(1, total_batches)} for {file_path.name} "
                            f"(chunks {start + 1}-{end} of {len(parent_chunks)})"
                        )

                    self._upsert_chunk_batch(active_collection, batch_chunks)

                    state["mode"] = "parent_child"
                    state["completed_parent_chunks"] = end
                    state["total_parent_chunks"] = len(parent_chunks)
                    state["completed_child_chunks"] = completed_child
                    state["total_child_chunks"] = len(chunks)
                    state["source"] = str(file_path)
                    state["collection"] = active_collection
                    store.save(state)

                for start in range(completed_child, len(chunks), batch_size):
                    end = min(start + batch_size, len(chunks))
                    batch_chunks = chunks[start:end]
                    batch_number = (start // batch_size) + 1
                    total_batches = (len(chunks) + batch_size - 1) // batch_size
                    log_every = max(1, int(settings.rag.log_every_batches or 1))
                    overall_start = len(parent_chunks) + start
                    overall_end = len(parent_chunks) + end
                    if progress_callback:
                        progress_callback(
                            file_index - 1 + (overall_start / total_units),
                            len(files),
                            (
                                f"Embedding child chunks {file_path.name}: "
                                f"batch {batch_number}/{max(1, total_batches)} (chunks {start + 1}-{end})"
                            ),
                        )
                    if batch_number == 1 or batch_number % log_every == 0 or end == len(chunks):
                        logger.info(
                            "Sending child ingest batch "
                            f"{batch_number}/{max(1, total_batches)} for {file_path.name} "
                            f"(chunks {start + 1}-{end} of {len(chunks)})"
                        )

                    self._upsert_chunk_batch(active_collection, batch_chunks)

                    state["mode"] = "parent_child"
                    state["completed_parent_chunks"] = len(parent_chunks)
                    state["total_parent_chunks"] = len(parent_chunks)
                    state["completed_child_chunks"] = end
                    state["total_child_chunks"] = len(chunks)
                    state["source"] = str(file_path)
                    state["collection"] = active_collection
                    store.save(state)

                    if progress_callback:
                        progress_callback(
                            file_index - 1 + (overall_end / total_units),
                            len(files),
                            f"Indexing {file_path.name}: child {end}/{len(chunks)}",
                        )
            else:
                completed = int(state.get("completed_chunks", 0))
                start_index = completed if resume else 0

                if progress_callback and start_index > 0:
                    progress_callback(
                        file_index - 1 + (start_index / max(1, len(chunks))),
                        len(files),
                        f"Resuming {file_path.name}: {start_index}/{len(chunks)} chunks",
                    )

                for start in range(start_index, len(chunks), batch_size):
                    end = min(start + batch_size, len(chunks))
                    batch_chunks = chunks[start:end]
                    batch_number = (start // batch_size) + 1
                    total_batches = (len(chunks) + batch_size - 1) // batch_size
                    log_every = max(1, int(settings.rag.log_every_batches or 1))
                    if progress_callback:
                        progress_callback(
                            file_index - 1 + (start / max(1, len(chunks))),
                            len(files),
                            (
                                f"Embedding {file_path.name}: batch {batch_number}/{total_batches} "
                                f"(chunks {start + 1}-{end})"
                            ),
                        )
                    if batch_number == 1 or batch_number % log_every == 0 or end == len(chunks):
                        logger.info(
                            "Sending ingest batch "
                            f"{batch_number}/{total_batches} for {file_path.name} "
                            f"(chunks {start + 1}-{end} of {len(chunks)})"
                        )

                    self._upsert_chunk_batch(active_collection, batch_chunks)

                    state["completed_chunks"] = end
                    state["total_chunks"] = len(chunks)
                    state["source"] = str(file_path)
                    state["collection"] = active_collection
                    store.save(state)

                    if progress_callback:
                        progress_callback(
                            file_index - 1 + (end / max(1, len(chunks))),
                            len(files),
                            f"Indexing {file_path.name}: {end}/{len(chunks)} chunks",
                        )

            total_chunks += len(chunks)
            total_parent_chunks += len(parent_chunks)
            total_child_chunks += len(chunks)
            indexed_files += 1
            if self.parent_child_enabled:
                logger.info(
                    f"Completed file {file_path.name}: parent_chunks={len(parent_chunks)}, child_chunks={len(chunks)}"
                )
            else:
                logger.info(f"Completed file {file_path.name}: chunks={len(chunks)}")

        logger.info(
            "RAG ingest completed: "
            f"files={indexed_files}, documents={total_docs}, chunks={total_chunks}, collection={active_collection}"
        )

        return {
            "collection": active_collection,
            "files": indexed_files,
            "documents": total_docs,
            "chunks": total_chunks,
            "parent_chunks": total_parent_chunks,
            "child_chunks": total_child_chunks,
        }

    def ingest_file(
        self,
        file_path: str,
        input_type: Optional[str] = None,
        collection_name: Optional[str] = None,
        reset_collection: bool = False,
        resume: bool = True,
        force: bool = False,
        progress_callback=None,
    ) -> Dict[str, Any]:
        return self.ingest_path(
            input_path=file_path,
            input_type=input_type,
            collection_name=collection_name,
            reset_collection=reset_collection,
            resume=resume,
            force=force,
            progress_callback=progress_callback,
        )

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        collection_name: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievedChunk]:
        active_collection = collection_name or self.collection_name
        query_vector = self.embedder.embed_query(query)
        fetch_k = max(top_k, int(settings.rag.retrieve_fetch_k or top_k))
        rerank_enabled = bool(settings.rag.rerank_enabled and self.reranker is not None)
        candidate_top_k = fetch_k if rerank_enabled else top_k

        if self.parent_child_enabled:
            return self._retrieve_parent_expanded(
                query=query,
                active_collection=active_collection,
                query_vector=query_vector,
                top_k=top_k,
                fetch_k=fetch_k,
                candidate_top_k=candidate_top_k,
                filters=filters,
                rerank_enabled=rerank_enabled,
            )

        if (
            settings.rag.hybrid_enabled
            and self.sparse_embedder is not None
            and hasattr(self._active_store, "search_hybrid")
        ):
            sparse_query = self.sparse_embedder.embed_query(query)
            hybrid_hits = self._active_store.search_hybrid(
                collection_name=active_collection,
                dense_query_vector=query_vector,
                sparse_query_vector=sparse_query,
                top_k=candidate_top_k,
                filters=filters,
                fetch_k=fetch_k,
            )
            if hybrid_hits:
                if rerank_enabled:
                    return self.reranker.rerank(query=query, items=hybrid_hits, top_k=top_k)
                return hybrid_hits[:top_k]

        dense_hits = self._active_store.search(
            collection_name=active_collection,
            query_vector=query_vector,
            top_k=fetch_k,
            filters=filters,
        )

        if rerank_enabled:
            return self.reranker.rerank(query=query, items=dense_hits, top_k=top_k)

        if not settings.rag.hybrid_enabled:
            return dense_hits[:top_k]

        return self._hybrid_rank(query=query, items=dense_hits, top_k=top_k)

    def generate(
        self,
        query: str,
        top_k: int = 5,
        collection_name: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        logger.info(f"RAG generate started: query_length={len(query)}, top_k={top_k}")
        context_chunks = self.retrieve(
            query=query,
            top_k=top_k,
            collection_name=collection_name,
            filters=filters,
        )
        logger.info(f"Retrieved context chunks: count={len(context_chunks)}")

        external_context_sections: List[str] = []
        mcp_context = ""
        if settings.rag.mcp_enabled and self.mcp_client is not None:
            logger.info("Fetching MCP external context...")
            try:
                mcp_context = self.mcp_client.fetch_context(
                    query=query,
                    top_k=top_k,
                    metadata={
                        "collection_name": collection_name or self.collection_name,
                    },
                )
                if mcp_context.strip():
                    external_context_sections.append(
                        "[MCP External Context]\n"
                        f"{mcp_context.strip()}"
                    )
            except Exception as error:
                logger.warning(f"MCP context fetch failed: {error}")

        web_context_used = False
        web_results_payload: List[Dict[str, Any]] = []
        if settings.rag.web_search_enabled and self.web_searcher is not None:
            logger.info("Fetching web search external context...")
            try:
                web_results = self.web_searcher.search(
                    query=query,
                    top_k=settings.rag.web_search_top_k,
                )
                if web_results:
                    web_context_used = True
                    web_lines: List[str] = []
                    for idx, item in enumerate(web_results, start=1):
                        snippet = (item.snippet or "").strip()
                        if snippet:
                            web_lines.append(
                                f"[{idx}] title={item.title or 'untitled'}\n"
                                f"url={item.url}\n"
                                f"snippet={snippet}"
                            )
                        web_results_payload.append(
                            {
                                "title": item.title,
                                "url": item.url,
                                "snippet": item.snippet,
                                "score": item.score,
                                "metadata": item.metadata,
                            }
                        )
                    if web_lines:
                        web_context = "\n\n".join(web_lines)
                        max_chars = int(settings.rag.web_search_max_context_chars or 0)
                        if max_chars > 0:
                            web_context = web_context[:max_chars]
                        external_context_sections.append(
                            "[Web Search Context]\n"
                            f"{web_context}"
                        )
            except Exception as error:
                logger.warning(f"Web search context fetch failed: {error}")

        merged_external_context = "\n\n".join(external_context_sections).strip()

        answer = self.generator.generate(
            query=query,
            context_chunks=context_chunks,
            external_context=merged_external_context,
        )
        logger.info("Generation completed successfully")
        return {
            "query": query,
            "answer": answer,
            "external_context_used": bool(merged_external_context),
            "mcp_context_used": bool(mcp_context),
            "web_context_used": web_context_used,
            "web_sources": web_results_payload,
            "sources": [
                {
                    "id": item.id,
                    "score": item.score,
                    "metadata": item.metadata,
                    "text": item.text,
                }
                for item in context_chunks
            ],
        }
