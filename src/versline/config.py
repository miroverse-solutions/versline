from typing import Optional
from pathlib import Path
import os
import warnings
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv


ENV_FILE_ENV_VAR = "VERSLINE_ENV_FILE"

class LLMSettings(BaseSettings):
    provider: str = Field(default="Google", description="LLM Provider (Google, OpenAI, OpenRouter, AvalAI, OpenAICompatible)")
    api_key: Optional[str] = Field(default=None, description="API Key for LLM")
    model: str = Field(default="gemini-2.0-flash", description="LLM Model")
    api_endpoint: Optional[str] = Field(default=None, description="Custom API Endpoint")
    proxy: Optional[str] = Field(default=None, description="Proxy URL")

    model_config = SettingsConfigDict(env_prefix='VERSLINE_LLM_', env_file='.env', extra='ignore')

class FFmpegSettings(BaseSettings):
    ffmpeg_path: Optional[str] = Field(default=None, description="Path to FFmpeg executable")
    ffprobe_path: Optional[str] = Field(default=None, description="Path to FFprobe executable")
    
    model_config = SettingsConfigDict(env_prefix='VERSLINE_FFMPEG_', env_file='.env', extra='ignore')


class RAGSettings(BaseSettings):
    vector_backend: str = Field(default="qdrant", description="Vector backend type")
    collection_name: str = Field(default="versline_docs", description="Default vector collection")
    vector_size: Optional[int] = Field(default=None, description="Optional fixed vector size for collection creation")
    qdrant_url: str = Field(default="http://localhost:6333", description="Qdrant URL")
    qdrant_api_key: Optional[str] = Field(default=None, description="Qdrant API key")
    qdrant_distance: str = Field(default="cosine", description="Vector distance metric")
    qdrant_proxy: Optional[str] = Field(default=None, description="Proxy only for Qdrant requests")
    embedding_model: str = Field(default="text-embedding-3-small", description="Embedding model")
    embedding_provider: str = Field(default="openai", description="Embedding provider (openai/openrouter/avalai/openaicompatible/fastembed/sentence-transformers[sentence|sentence_transformers]/flagembedding/optimum-intel/openvino)")
    embedding_api_key: Optional[str] = Field(default=None, description="Embedding API key override")
    embedding_api_endpoint: Optional[str] = Field(default=None, description="Embedding API endpoint override")
    embedding_timeout_seconds: float = Field(default=60.0, description="Embedding request timeout seconds")
    embedding_proxy: Optional[str] = Field(default=None, description="Proxy only for embedding requests")
    embedding_model_path: Optional[str] = Field(default=None, description="Optional local path for dense embedding model artifacts")
    embedding_cache_dir: Optional[str] = Field(default=None, description="Cache directory for dense embedding model artifacts")
    embedding_local_files_only: bool = Field(default=False, description="Load dense embedding model artifacts from local files only")
    embedding_use_fp16: bool = Field(default=True, description="Use fp16 when supported by dense local embedding backend")
    embedding_device: Optional[str] = Field(default=None, description="Device override for dense embedding model (e.g. cpu, cuda)")
    embedding_batch_size: int = Field(default=16, description="Batch size for dense embedding encoding")
    embedding_inference_backend: str = Field(default="auto", description="Dense embedding inference backend: auto or openvino")
    embedding_onnx_providers: Optional[str] = Field(default=None, description="Optional comma-separated ONNX provider list for dense fastembed")
    sparse_embedding_proxy: Optional[str] = Field(default=None, description="Proxy used for sparse embedding model download/init")
    openvino_cache_dir: Optional[str] = Field(default=None, description="Cache directory for OpenVINO compiled artifacts")
    generation_timeout_seconds: float = Field(default=120.0, description="Generation request timeout seconds")
    generation_proxy: Optional[str] = Field(default=None, description="Proxy only for generation requests")
    qdrant_timeout_seconds: float = Field(default=20.0, description="Qdrant request timeout seconds")
    rerank_timeout_seconds: float = Field(default=60.0, description="Rerank request timeout seconds")
    chunk_size: int = Field(default=1200, description="Chunk size in characters")
    chunk_overlap: int = Field(default=200, description="Chunk overlap in characters")
    parent_child_enabled: bool = Field(default=False, description="Enable hierarchical parent-child chunking and retrieval")
    parent_chunk_size: int = Field(default=2400, description="Parent chunk size in characters")
    parent_chunk_overlap: int = Field(default=200, description="Parent chunk overlap in characters")
    parent_child_paragraph_mode: bool = Field(default=False, description="Prefer paragraph boundaries (double newline) for parent-child chunking")
    parent_chunk_delimiters: Optional[str] = Field(default=None, description="Optional comma-separated delimiters used to align parent chunk boundaries")
    child_chunk_delimiters: Optional[str] = Field(default=None, description="Optional comma-separated delimiters used to align child chunk boundaries")
    parent_child_fetch_k: int = Field(default=48, description="Child candidates fetched for parent-child retrieval expansion")
    log_every_batches: int = Field(default=1, description="Emit ingest logs every N batches")
    ingestion_batch_size: int = Field(default=32, description="Batch size for embedding/upsert during ingestion")
    retrieve_fetch_k: int = Field(default=24, description="Dense candidates fetched before hybrid rerank")
    hybrid_enabled: bool = Field(default=True, description="Enable hybrid retrieval reranking")
    sparse_embedding_model: str = Field(
        default="prithivida/Splade_PP_en_v1",
        description="Sparse embedding model for native Qdrant hybrid search",
    )
    sparse_embedding_provider: str = Field(
        default="fastembed",
        description="Sparse embedding provider. Supports fastembed, flagembedding, or compatibility values (same/auto/openai/openrouter/avalai/openaicompatible/sentence-transformers/openvino) mapped to a supported sparse backend.",
    )
    sparse_embedding_model_path: Optional[str] = Field(
        default=None,
        description="Optional local path for sparse embedding model artifacts",
    )
    sparse_embedding_cache_dir: Optional[str] = Field(
        default=None,
        description="Cache directory for sparse FastEmbed model artifacts",
    )
    sparse_embedding_local_files_only: bool = Field(
        default=False,
        description="Load sparse FastEmbed artifacts from local files only",
    )
    sparse_embedding_use_fp16: bool = Field(
        default=True,
        description="Use fp16 for FlagEmbedding sparse model when supported",
    )
    sparse_embedding_device: Optional[str] = Field(
        default=None,
        description="Device override for sparse embedding model (e.g. cpu, cuda)",
    )
    sparse_embedding_batch_size: int = Field(
        default=16,
        description="Batch size for sparse embedding encoding",
    )
    sparse_embedding_onnx_providers: Optional[str] = Field(
        default=None,
        description="Optional comma-separated ONNX provider list for sparse fastembed",
    )
    hybrid_fusion: str = Field(default="rrf", description="Hybrid fusion mode")
    hybrid_dense_weight: float = Field(default=0.7, description="Weight of dense score in hybrid ranking")
    hybrid_lexical_weight: float = Field(default=0.3, description="Weight of lexical score in hybrid ranking")
    generation_prompt_file: str = Field(default="rag_generate_prompt.md", description="Prompt file used for RAG generation")
    retry_max_retries: int = Field(default=4, description="Maximum retries for external requests")
    retry_base_delay_seconds: float = Field(default=1.0, description="Base retry delay in seconds")
    retry_max_delay_seconds: float = Field(default=12.0, description="Maximum retry delay in seconds")
    rate_limit_embedding_rpm: int = Field(default=0, description="Embedding requests per minute (0 disables)")
    rate_limit_embedding_tpm: int = Field(default=0, description="Embedding tokens per minute (0 disables)")
    rate_limit_generation_rpm: int = Field(default=0, description="Generation requests per minute (0 disables)")
    rate_limit_generation_tpm: int = Field(default=0, description="Generation tokens per minute (0 disables)")
    rate_limit_qdrant_rpm: int = Field(default=0, description="Qdrant requests per minute (0 disables)")
    rerank_enabled: bool = Field(default=False, description="Enable dedicated rerank model after retrieval")
    rerank_provider: str = Field(
        default="cohere",
        description="Rerank provider (cohere/jina/openai/openrouter/avalai/openaicompatible/local/fastembed/sentence-transformers/optimum-intel/openvino/flagembedding/same/auto).",
    )
    rerank_model: str = Field(default="rerank-v3.5", description="Rerank model")
    rerank_api_key: Optional[str] = Field(default=None, description="Rerank API key override")
    rerank_api_endpoint: Optional[str] = Field(default=None, description="Rerank API endpoint override")
    rerank_proxy: Optional[str] = Field(default=None, description="Proxy only for rerank requests")
    rerank_model_path: Optional[str] = Field(default=None, description="Optional local path for rerank model artifacts")
    rerank_cache_dir: Optional[str] = Field(default=None, description="Cache directory for rerank model artifacts")
    rerank_local_files_only: bool = Field(default=False, description="Load rerank model artifacts from local files only")
    rerank_device: Optional[str] = Field(default=None, description="Device override for local rerank model (e.g. cpu, cuda)")
    rerank_batch_size: int = Field(default=16, description="Batch size for local rerank scoring")
    rerank_inference_backend: str = Field(default="auto", description="Rerank inference backend: auto or openvino")
    rerank_onnx_providers: Optional[str] = Field(default=None, description="Optional comma-separated ONNX provider list for fastembed rerank")
    rate_limit_rerank_rpm: int = Field(default=0, description="Rerank requests per minute (0 disables)")
    rate_limit_rerank_tpm: int = Field(default=0, description="Rerank tokens per minute (0 disables)")
    token_limit_mode: str = Field(
        default="estimate_only",
        description="Token limiter mode: estimate_only or estimate_and_adjust",
    )
    mcp_enabled: bool = Field(default=False, description="Enable MCP context augmentation")
    mcp_transport: str = Field(default="http", description="MCP transport: http or stdio")
    mcp_server_url: Optional[str] = Field(default=None, description="MCP gateway/server URL for http transport")
    mcp_server_command: Optional[str] = Field(default=None, description="MCP server command for stdio transport")
    mcp_server_args: Optional[str] = Field(default=None, description="MCP stdio server args string")
    mcp_tool_name: str = Field(default="retrieve_context", description="MCP tool name used for external context")
    mcp_timeout_seconds: int = Field(default=30, description="MCP request timeout in seconds")
    mcp_max_context_chars: int = Field(default=8000, description="Maximum external MCP context chars")
    mcp_proxy: Optional[str] = Field(default=None, description="Proxy used only for MCP HTTP transport")
    web_search_enabled: bool = Field(default=False, description="Enable external web search context augmentation")
    web_search_provider: str = Field(default="duckduckgo", description="Web search provider (duckduckgo, tavily)")
    web_search_api_key: Optional[str] = Field(default=None, description="Web search provider API key override")
    web_search_endpoint: Optional[str] = Field(default=None, description="Custom web search API endpoint")
    web_search_timeout_seconds: int = Field(default=15, description="Web search request timeout in seconds")
    web_search_top_k: int = Field(default=3, description="How many web results are used as external context")
    web_search_proxy: Optional[str] = Field(default=None, description="Proxy used only for web search requests")
    web_search_max_context_chars: int = Field(default=6000, description="Maximum chars imported from web search")
    rate_limit_web_search_rpm: int = Field(default=0, description="Web search requests per minute (0 disables)")
    preflight_enabled: bool = Field(default=True, description="Enable preflight validation before RAG operations")
    preflight_network: bool = Field(default=False, description="Enable network endpoint checks in preflight")
    state_directory: Path = Field(default=Path("work_dir"), description="RAG state directory")

    model_config = SettingsConfigDict(env_prefix='VERSLINE_RAG_', env_file='.env', extra='ignore')


class ResourceSettings(BaseSettings):
    max_ram_mb: int = Field(default=0, description="Maximum RAM usage in MB (0 = unlimited)")
    max_cpu_cores: int = Field(default=0, description="Maximum CPU cores/threads to use (0 = unlimited)")
    max_gpu_vram_fraction: float = Field(default=0.0, description="Maximum GPU VRAM fraction per device (0.0 = unlimited, e.g. 0.8 = 80%)")

    model_config = SettingsConfigDict(env_prefix='VERSLINE_RESOURCE_', env_file='.env', extra='ignore')


class Settings(BaseSettings):
    llm: LLMSettings = Field(default_factory=LLMSettings)
    ffmpeg: FFmpegSettings = Field(default_factory=FFmpegSettings)
    rag: RAGSettings = Field(default_factory=RAGSettings)
    resource: ResourceSettings = Field(default_factory=ResourceSettings)

    # Common settings
    output_directory: Path = Field(default=Path("output"), description="Default output directory")
    temp_directory: Path = Field(default=Path("temp"), description="Temporary directory")
    
    model_config = SettingsConfigDict(env_prefix='VERSLINE_', env_file='.env', extra='ignore')


def _resolve_env_file_path(env_file: Optional[Path]) -> Optional[Path]:
    if env_file is not None:
        return Path(env_file).expanduser()

    env_file_value = os.getenv(ENV_FILE_ENV_VAR)
    if not env_file_value:
        return None
    return Path(env_file_value).expanduser()


def _load_env_file(env_path: Path, *, override: bool, raise_if_missing: bool) -> None:
    if not env_path.exists() or not env_path.is_file():
        if raise_if_missing:
            raise FileNotFoundError(f"Env file not found: {env_path}")
        warnings.warn(f"Env file from {ENV_FILE_ENV_VAR} not found: {env_path}", stacklevel=2)
        return
    load_dotenv(dotenv_path=env_path, override=override)


_bootstrap_env_path = _resolve_env_file_path(None)
if _bootstrap_env_path is not None:
    _load_env_file(_bootstrap_env_path, override=False, raise_if_missing=False)


# Global settings instance
settings = Settings()


def reload_settings(env_file: Optional[Path] = None, *, override_env: bool = True) -> Settings:
    env_path = _resolve_env_file_path(env_file)
    if env_path is not None:
        effective_override = override_env if env_file is not None else False
        _load_env_file(env_path, override=effective_override, raise_if_missing=True)

    refreshed_settings = Settings()
    settings.llm = refreshed_settings.llm
    settings.ffmpeg = refreshed_settings.ffmpeg
    settings.rag = refreshed_settings.rag
    settings.output_directory = refreshed_settings.output_directory
    settings.temp_directory = refreshed_settings.temp_directory
    return settings
