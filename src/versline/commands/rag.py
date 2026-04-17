from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from versline.config import settings
from versline.services.rag.tuning import tune_ingest_settings
from versline.services.pricing import print_cost_report

app = typer.Typer(help="RAG ingestion, retrieval, and generation.")


def _apply_llm_overrides(
    provider: Optional[str],
    model: Optional[str],
    api_key: Optional[str],
    api_endpoint: Optional[str],
    proxy: Optional[str],
):
    if provider:
        settings.llm.provider = provider
    if model:
        settings.llm.model = model
    if api_key:
        settings.llm.api_key = api_key
    if api_endpoint:
        settings.llm.api_endpoint = api_endpoint
    if proxy:
        settings.llm.proxy = proxy


def _apply_rag_overrides(
    vector_size: Optional[int],
    chunk_size: Optional[int],
    chunk_overlap: Optional[int],
    parent_child_enabled: Optional[bool],
    parent_chunk_size: Optional[int],
    parent_chunk_overlap: Optional[int],
    parent_child_paragraph_mode: Optional[bool],
    parent_chunk_delimiters: Optional[str],
    child_chunk_delimiters: Optional[str],
    parent_child_fetch_k: Optional[int],
    ingestion_batch_size: Optional[int],
    retrieve_fetch_k: Optional[int],
    hybrid_dense_weight: Optional[float],
    hybrid_lexical_weight: Optional[float],
    embedding_provider: Optional[str],
    embedding_api_key: Optional[str],
    embedding_api_endpoint: Optional[str],
    embedding_model_path: Optional[str],
    embedding_cache_dir: Optional[str],
    embedding_local_files_only: Optional[bool],
    embedding_use_fp16: Optional[bool],
    embedding_device: Optional[str],
    embedding_batch_size: Optional[int],
    embedding_inference_backend: Optional[str],
    openvino_cache_dir: Optional[str],
    embedding_timeout_seconds: Optional[float],
    generation_timeout_seconds: Optional[float],
    qdrant_timeout_seconds: Optional[float],
    rerank_timeout_seconds: Optional[float],
    log_every_batches: Optional[int],
    preflight_enabled: Optional[bool],
    preflight_network: Optional[bool],
    embedding_proxy: Optional[str],
    sparse_embedding_proxy: Optional[str],
    sparse_embedding_cache_dir: Optional[str],
    sparse_embedding_local_files_only: Optional[bool],
    sparse_embedding_provider: Optional[str],
    sparse_embedding_model_path: Optional[str],
    sparse_embedding_use_fp16: Optional[bool],
    sparse_embedding_device: Optional[str],
    sparse_embedding_batch_size: Optional[int],
    generation_proxy: Optional[str],
    qdrant_proxy: Optional[str],
    embedding_rpm: Optional[int],
    embedding_tpm: Optional[int],
    generation_rpm: Optional[int],
    generation_tpm: Optional[int],
    qdrant_rpm: Optional[int],
    retry_max_retries: Optional[int],
    retry_base_delay_seconds: Optional[float],
    retry_max_delay_seconds: Optional[float],
    hybrid: Optional[bool],
    sparse_model: Optional[str],
    rerank_enabled: Optional[bool],
    rerank_provider: Optional[str],
    rerank_model: Optional[str],
    rerank_api_key: Optional[str],
    rerank_api_endpoint: Optional[str],
    rerank_proxy: Optional[str],
    rerank_model_path: Optional[str],
    rerank_cache_dir: Optional[str],
    rerank_local_files_only: Optional[bool],
    rerank_device: Optional[str],
    rerank_batch_size: Optional[int],
    rerank_inference_backend: Optional[str],
    rerank_onnx_providers: Optional[str],
    rerank_rpm: Optional[int],
    rerank_tpm: Optional[int],
    token_limit_mode: Optional[str],
    mcp_enabled: Optional[bool],
    mcp_transport: Optional[str],
    mcp_server_url: Optional[str],
    mcp_server_command: Optional[str],
    mcp_server_args: Optional[str],
    mcp_tool_name: Optional[str],
    mcp_timeout_seconds: Optional[int],
    mcp_max_context_chars: Optional[int],
    mcp_proxy: Optional[str],
    web_search_enabled: Optional[bool],
    web_search_provider: Optional[str],
    web_search_api_key: Optional[str],
    web_search_endpoint: Optional[str],
    web_search_timeout_seconds: Optional[int],
    web_search_top_k: Optional[int],
    web_search_proxy: Optional[str],
    web_search_max_context_chars: Optional[int],
    web_search_rpm: Optional[int],
):
    if vector_size is not None:
        settings.rag.vector_size = int(vector_size)
    if chunk_size is not None:
        settings.rag.chunk_size = chunk_size
    if chunk_overlap is not None:
        settings.rag.chunk_overlap = chunk_overlap
    if parent_child_enabled is not None:
        settings.rag.parent_child_enabled = parent_child_enabled
    if parent_chunk_size is not None:
        settings.rag.parent_chunk_size = parent_chunk_size
    if parent_chunk_overlap is not None:
        settings.rag.parent_chunk_overlap = parent_chunk_overlap
    if parent_child_paragraph_mode is not None:
        settings.rag.parent_child_paragraph_mode = parent_child_paragraph_mode
    if parent_chunk_delimiters is not None:
        settings.rag.parent_chunk_delimiters = parent_chunk_delimiters
    if child_chunk_delimiters is not None:
        settings.rag.child_chunk_delimiters = child_chunk_delimiters
    if parent_child_fetch_k is not None:
        settings.rag.parent_child_fetch_k = parent_child_fetch_k
    if ingestion_batch_size is not None:
        settings.rag.ingestion_batch_size = ingestion_batch_size
    if retrieve_fetch_k is not None:
        settings.rag.retrieve_fetch_k = retrieve_fetch_k
    if hybrid_dense_weight is not None:
        settings.rag.hybrid_dense_weight = hybrid_dense_weight
    if hybrid_lexical_weight is not None:
        settings.rag.hybrid_lexical_weight = hybrid_lexical_weight
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
        settings.rag.embedding_local_files_only = embedding_local_files_only
    if embedding_use_fp16 is not None:
        settings.rag.embedding_use_fp16 = embedding_use_fp16
    if embedding_device is not None:
        settings.rag.embedding_device = embedding_device
    if embedding_batch_size is not None:
        settings.rag.embedding_batch_size = embedding_batch_size
    if embedding_inference_backend is not None:
        settings.rag.embedding_inference_backend = embedding_inference_backend
    if openvino_cache_dir is not None:
        settings.rag.openvino_cache_dir = openvino_cache_dir
    if embedding_timeout_seconds is not None:
        settings.rag.embedding_timeout_seconds = embedding_timeout_seconds
    if generation_timeout_seconds is not None:
        settings.rag.generation_timeout_seconds = generation_timeout_seconds
    if qdrant_timeout_seconds is not None:
        settings.rag.qdrant_timeout_seconds = qdrant_timeout_seconds
    if rerank_timeout_seconds is not None:
        settings.rag.rerank_timeout_seconds = rerank_timeout_seconds
    if log_every_batches is not None:
        settings.rag.log_every_batches = max(1, log_every_batches)
    if preflight_enabled is not None:
        settings.rag.preflight_enabled = preflight_enabled
    if preflight_network is not None:
        settings.rag.preflight_network = preflight_network
    if embedding_proxy is not None:
        settings.rag.embedding_proxy = embedding_proxy
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
        settings.rag.sparse_embedding_batch_size = sparse_embedding_batch_size
    if generation_proxy is not None:
        settings.rag.generation_proxy = generation_proxy
    if qdrant_proxy is not None:
        settings.rag.qdrant_proxy = qdrant_proxy
    if embedding_rpm is not None:
        settings.rag.rate_limit_embedding_rpm = embedding_rpm
    if embedding_tpm is not None:
        settings.rag.rate_limit_embedding_tpm = embedding_tpm
    if generation_rpm is not None:
        settings.rag.rate_limit_generation_rpm = generation_rpm
    if generation_tpm is not None:
        settings.rag.rate_limit_generation_tpm = generation_tpm
    if qdrant_rpm is not None:
        settings.rag.rate_limit_qdrant_rpm = qdrant_rpm
    if retry_max_retries is not None:
        settings.rag.retry_max_retries = retry_max_retries
    if retry_base_delay_seconds is not None:
        settings.rag.retry_base_delay_seconds = retry_base_delay_seconds
    if retry_max_delay_seconds is not None:
        settings.rag.retry_max_delay_seconds = retry_max_delay_seconds
    if hybrid is not None:
        settings.rag.hybrid_enabled = hybrid
    if sparse_model is not None:
        settings.rag.sparse_embedding_model = sparse_model
    if rerank_enabled is not None:
        settings.rag.rerank_enabled = rerank_enabled
    if rerank_provider is not None:
        settings.rag.rerank_provider = rerank_provider
    if rerank_model is not None:
        settings.rag.rerank_model = rerank_model
    if rerank_api_key is not None:
        settings.rag.rerank_api_key = rerank_api_key
    if rerank_api_endpoint is not None:
        settings.rag.rerank_api_endpoint = rerank_api_endpoint
    if rerank_proxy is not None:
        settings.rag.rerank_proxy = rerank_proxy
    if rerank_model_path is not None:
        settings.rag.rerank_model_path = rerank_model_path
    if rerank_cache_dir is not None:
        settings.rag.rerank_cache_dir = rerank_cache_dir
    if rerank_local_files_only is not None:
        settings.rag.rerank_local_files_only = rerank_local_files_only
    if rerank_device is not None:
        settings.rag.rerank_device = rerank_device
    if rerank_batch_size is not None:
        settings.rag.rerank_batch_size = rerank_batch_size
    if rerank_inference_backend is not None:
        settings.rag.rerank_inference_backend = rerank_inference_backend
    if rerank_onnx_providers is not None:
        settings.rag.rerank_onnx_providers = rerank_onnx_providers
    if rerank_rpm is not None:
        settings.rag.rate_limit_rerank_rpm = rerank_rpm
    if rerank_tpm is not None:
        settings.rag.rate_limit_rerank_tpm = rerank_tpm
    if token_limit_mode is not None:
        settings.rag.token_limit_mode = token_limit_mode
    if mcp_enabled is not None:
        settings.rag.mcp_enabled = mcp_enabled
    if mcp_transport is not None:
        settings.rag.mcp_transport = mcp_transport
    if mcp_server_url is not None:
        settings.rag.mcp_server_url = mcp_server_url
    if mcp_server_command is not None:
        settings.rag.mcp_server_command = mcp_server_command
    if mcp_server_args is not None:
        settings.rag.mcp_server_args = mcp_server_args
    if mcp_tool_name is not None:
        settings.rag.mcp_tool_name = mcp_tool_name
    if mcp_timeout_seconds is not None:
        settings.rag.mcp_timeout_seconds = mcp_timeout_seconds
    if mcp_max_context_chars is not None:
        settings.rag.mcp_max_context_chars = mcp_max_context_chars
    if mcp_proxy is not None:
        settings.rag.mcp_proxy = mcp_proxy
    if web_search_enabled is not None:
        settings.rag.web_search_enabled = web_search_enabled
    if web_search_provider is not None:
        settings.rag.web_search_provider = web_search_provider
    if web_search_api_key is not None:
        settings.rag.web_search_api_key = web_search_api_key
    if web_search_endpoint is not None:
        settings.rag.web_search_endpoint = web_search_endpoint
    if web_search_timeout_seconds is not None:
        settings.rag.web_search_timeout_seconds = web_search_timeout_seconds
    if web_search_top_k is not None:
        settings.rag.web_search_top_k = web_search_top_k
    if web_search_proxy is not None:
        settings.rag.web_search_proxy = web_search_proxy
    if web_search_max_context_chars is not None:
        settings.rag.web_search_max_context_chars = web_search_max_context_chars
    if web_search_rpm is not None:
        settings.rag.rate_limit_web_search_rpm = web_search_rpm


@app.command("ingest")
def ingest(
    input_path: Path = typer.Argument(..., exists=True, help="Path to source file or directory"),
    collection: Optional[str] = typer.Option(None, "--collection", "-c", help="Target collection name"),
    input_type: Optional[str] = typer.Option(None, "--input-type", help="Input type override, e.g. markdown"),
    reset: bool = typer.Option(False, "--reset", help="Drop and recreate collection before ingest"),
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Resume from saved progress state"),
    force: bool = typer.Option(False, "--force", "-f", help="Ignore previous progress and re-index all chunks"),
    provider: Optional[str] = typer.Option(None, "--provider", help="LLM Provider"),
    model: Optional[str] = typer.Option(None, "--model", help="Generation model override"),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model", help="Embedding model override"),
    embedding_provider: Optional[str] = typer.Option(None, "--embedding-provider", help="Dense embedding provider (openai/openrouter/avalai/openaicompatible/fastembed/sentence-transformers[sentence|sentence_transformers]/flagembedding/openvino)"),
    embedding_api_key: Optional[str] = typer.Option(None, "--embedding-api-key", help="Embedding API key override"),
    embedding_api_endpoint: Optional[str] = typer.Option(None, "--embedding-api-endpoint", help="Embedding API endpoint override"),
    embedding_model_path: Optional[str] = typer.Option(None, "--embedding-model-path", help="Local path for dense embedding model artifacts"),
    embedding_cache_dir: Optional[str] = typer.Option(None, "--embedding-cache-dir", help="Dense embedding cache directory (enables local-only mode)"),
    embedding_local_files_only: Optional[bool] = typer.Option(None, "--embedding-local-files-only/--no-embedding-local-files-only", help="Use local files only for dense embedding model"),
    embedding_use_fp16: Optional[bool] = typer.Option(None, "--embedding-use-fp16/--no-embedding-use-fp16", help="Use fp16 for dense local backends when supported"),
    embedding_device: Optional[str] = typer.Option(None, "--embedding-device", help="Dense embedding device (cpu/cuda)"),
    embedding_batch_size: Optional[int] = typer.Option(None, "--embedding-batch-size", help="Dense embedding batch size"),
    auto_tune: Optional[bool] = typer.Option(None, "--auto-tune/--no-auto-tune", help="Auto-tune ingest resource knobs based on provider and available RAM"),
    low_memory: Optional[bool] = typer.Option(None, "--low-memory/--no-low-memory", help="Conservative ingest profile for low-RAM systems (forces cpu + smaller batches unless explicitly overridden)"),
    embedding_inference_backend: Optional[str] = typer.Option(None, "--embedding-backend", help="Dense embedding inference backend: auto or openvino"),
    openvino_cache_dir: Optional[str] = typer.Option(None, "--openvino-cache-dir", help="Cache directory for OpenVINO compiled artifacts"),
    embedding_timeout_seconds: Optional[float] = typer.Option(None, "--embedding-timeout", help="Embedding timeout seconds"),
    generation_timeout_seconds: Optional[float] = typer.Option(None, "--generation-timeout", help="Generation timeout seconds"),
    qdrant_timeout_seconds: Optional[float] = typer.Option(None, "--qdrant-timeout", help="Qdrant timeout seconds"),
    rerank_timeout_seconds: Optional[float] = typer.Option(None, "--rerank-timeout", help="Rerank timeout seconds"),
    sparse_model: Optional[str] = typer.Option(None, "--sparse-model", help="Sparse embedding model for native hybrid retrieval"),
    vector_size: Optional[int] = typer.Option(None, "--vector-size", min=1, help="Fixed vector size for collection creation (defaults to embedding dimension when omitted)"),
    chunk_size: Optional[int] = typer.Option(None, "--chunk-size", help="Chunk size in characters"),
    chunk_overlap: Optional[int] = typer.Option(None, "--chunk-overlap", help="Chunk overlap in characters"),
    parent_child: Optional[bool] = typer.Option(None, "--parent-child/--no-parent-child", help="Enable hierarchical parent-child retrieval"),
    parent_chunk_size: Optional[int] = typer.Option(None, "--parent-chunk-size", help="Parent chunk size in characters"),
    parent_chunk_overlap: Optional[int] = typer.Option(None, "--parent-chunk-overlap", help="Parent chunk overlap in characters"),
    parent_child_paragraph: Optional[bool] = typer.Option(None, "--parent-child-paragraph/--no-parent-child-paragraph", help="Prefer paragraph boundaries (double newline) for parent-child chunking"),
    parent_chunk_delimiters: Optional[str] = typer.Option(None, "--parent-chunk-delimiters", help="Comma-separated delimiters for parent chunk boundaries (supports escaped values like \\n\\n)"),
    child_chunk_delimiters: Optional[str] = typer.Option(None, "--child-chunk-delimiters", help="Comma-separated delimiters for child chunk boundaries (supports escaped values like \\n\\n)"),
    parent_child_fetch_k: Optional[int] = typer.Option(None, "--parent-child-fetch-k", help="Child candidates fetched before parent expansion"),
    ingestion_batch_size: Optional[int] = typer.Option(None, "--ingestion-batch-size", help="Ingestion batch size"),
    log_every_batches: Optional[int] = typer.Option(None, "--log-every-batches", help="Emit ingest logs every N batches"),
    retrieve_fetch_k: Optional[int] = typer.Option(None, "--retrieve-fetch-k", help="Dense candidates fetched before rerank/hybrid"),
    hybrid_dense_weight: Optional[float] = typer.Option(None, "--hybrid-dense-weight", help="Dense score weight in hybrid ranking"),
    hybrid_lexical_weight: Optional[float] = typer.Option(None, "--hybrid-lexical-weight", help="Lexical score weight in hybrid ranking"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="Provider API key"),
    api_endpoint: Optional[str] = typer.Option(None, "--api-endpoint", help="Custom API endpoint"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL"),
    embedding_proxy: Optional[str] = typer.Option(None, "--embedding-proxy", help="Proxy used only for embeddings"),
    sparse_proxy: Optional[str] = typer.Option(None, "--sparse-proxy", help="Proxy used for sparse embedding model download/init"),
    sparse_cache_dir: Optional[str] = typer.Option(None, "--sparse-cache-dir", help="Sparse FastEmbed cache directory (forces local-files-only mode)"),
    sparse_local_files_only: Optional[bool] = typer.Option(None, "--sparse-local-files-only/--no-sparse-local-files-only", help="Use local sparse model files only"),
    sparse_provider: Optional[str] = typer.Option(None, "--sparse-provider", help="Sparse provider (fastembed/flagembedding) or compatibility values: same/auto/openai/openrouter/avalai/openaicompatible/sentence-transformers/openvino"),
    sparse_model_path: Optional[str] = typer.Option(None, "--sparse-model-path", help="Local path for sparse model artifacts"),
    sparse_use_fp16: Optional[bool] = typer.Option(None, "--sparse-use-fp16/--no-sparse-use-fp16", help="Use fp16 for FlagEmbedding sparse backend"),
    sparse_device: Optional[str] = typer.Option(None, "--sparse-device", help="Sparse backend device (cpu/cuda)"),
    sparse_batch_size: Optional[int] = typer.Option(None, "--sparse-batch-size", help="Sparse backend batch size"),
    generation_proxy: Optional[str] = typer.Option(None, "--generation-proxy", help="Proxy used only for generation"),
    qdrant_proxy: Optional[str] = typer.Option(None, "--qdrant-proxy", help="Proxy used only for Qdrant"),
    qdrant_url: Optional[str] = typer.Option(None, "--qdrant-url", help="Qdrant URL"),
    qdrant_api_key: Optional[str] = typer.Option(None, "--qdrant-api-key", help="Qdrant API key"),
    hybrid: Optional[bool] = typer.Option(None, "--hybrid/--no-hybrid", help="Enable sparse+dense hybrid indexing during ingest"),
    embedding_rpm: Optional[int] = typer.Option(None, "--embedding-rpm", help="Rate limit for embeddings (req/min)"),
    embedding_tpm: Optional[int] = typer.Option(None, "--embedding-tpm", help="Token limit for embeddings (tokens/min)"),
    generation_rpm: Optional[int] = typer.Option(None, "--generation-rpm", help="Rate limit for generation (req/min)"),
    generation_tpm: Optional[int] = typer.Option(None, "--generation-tpm", help="Token limit for generation (tokens/min)"),
    qdrant_rpm: Optional[int] = typer.Option(None, "--qdrant-rpm", help="Rate limit for qdrant (req/min)"),
    retry_max_retries: Optional[int] = typer.Option(None, "--retry-max-retries", help="Max retries for external requests"),
    retry_base_delay_seconds: Optional[float] = typer.Option(None, "--retry-base-delay", help="Base retry delay (seconds)"),
    retry_max_delay_seconds: Optional[float] = typer.Option(None, "--retry-max-delay", help="Max retry delay (seconds)"),
    rerank: Optional[bool] = typer.Option(None, "--rerank/--no-rerank", help="Enable dedicated rerank model"),
    rerank_provider: Optional[str] = typer.Option(None, "--rerank-provider", help="Rerank provider (cohere/jina/openai/openrouter/avalai/openaicompatible/local/fastembed/sentence-transformers/openvino/flagembedding/same/auto)"),
    rerank_model: Optional[str] = typer.Option(None, "--rerank-model", help="Dedicated rerank model"),
    rerank_api_key: Optional[str] = typer.Option(None, "--rerank-api-key", help="Rerank API key"),
    rerank_api_endpoint: Optional[str] = typer.Option(None, "--rerank-api-endpoint", help="Rerank API endpoint"),
    rerank_proxy: Optional[str] = typer.Option(None, "--rerank-proxy", help="Proxy used only for rerank"),
    rerank_model_path: Optional[str] = typer.Option(None, "--rerank-model-path", help="Local path for rerank model artifacts"),
    rerank_cache_dir: Optional[str] = typer.Option(None, "--rerank-cache-dir", help="Rerank model cache directory (enables local-only mode)"),
    rerank_local_files_only: Optional[bool] = typer.Option(None, "--rerank-local-files-only/--no-rerank-local-files-only", help="Use local files only for rerank model"),
    rerank_device: Optional[str] = typer.Option(None, "--rerank-device", help="Local rerank device (cpu/cuda)"),
    rerank_batch_size: Optional[int] = typer.Option(None, "--rerank-batch-size", help="Local rerank batch size"),
    rerank_inference_backend: Optional[str] = typer.Option(None, "--rerank-backend", help="Rerank inference backend: auto or openvino"),
    rerank_onnx_providers: Optional[str] = typer.Option(None, "--rerank-onnx-providers", help="Comma-separated ONNX provider order for fastembed rerank"),
    rerank_rpm: Optional[int] = typer.Option(None, "--rerank-rpm", help="Rate limit for rerank (req/min)"),
    rerank_tpm: Optional[int] = typer.Option(None, "--rerank-tpm", help="Token limit for rerank (tokens/min)"),
    token_limit_mode: Optional[str] = typer.Option(
        None,
        "--token-limit-mode",
        help="TPM mode: estimate_only or estimate_and_adjust",
    ),
    mcp: Optional[bool] = typer.Option(None, "--mcp/--no-mcp", help="Enable MCP external context"),
    mcp_transport: Optional[str] = typer.Option(None, "--mcp-transport", help="MCP transport: http or stdio"),
    mcp_server_url: Optional[str] = typer.Option(None, "--mcp-server-url", help="MCP server URL (http mode)"),
    mcp_server_command: Optional[str] = typer.Option(None, "--mcp-server-command", help="MCP server command (stdio mode)"),
    mcp_server_args: Optional[str] = typer.Option(None, "--mcp-server-args", help="MCP server args string (stdio mode)"),
    mcp_tool_name: Optional[str] = typer.Option(None, "--mcp-tool", help="MCP tool name for context retrieval"),
    mcp_timeout_seconds: Optional[int] = typer.Option(None, "--mcp-timeout", help="MCP timeout seconds"),
    mcp_max_context_chars: Optional[int] = typer.Option(None, "--mcp-max-context-chars", help="Max chars from MCP context"),
    mcp_proxy: Optional[str] = typer.Option(None, "--mcp-proxy", help="Proxy only for MCP http transport"),
    web_search: Optional[bool] = typer.Option(None, "--web-search/--no-web-search", help="Enable external web search context"),
    web_search_provider: Optional[str] = typer.Option(None, "--web-search-provider", help="Web search provider (duckduckgo, tavily)"),
    web_search_api_key: Optional[str] = typer.Option(None, "--web-search-api-key", help="Web search provider API key"),
    web_search_endpoint: Optional[str] = typer.Option(None, "--web-search-endpoint", help="Custom web search endpoint"),
    web_search_timeout_seconds: Optional[int] = typer.Option(None, "--web-search-timeout", help="Web search timeout seconds"),
    web_search_top_k: Optional[int] = typer.Option(None, "--web-search-top-k", help="Web results included as external context"),
    web_search_proxy: Optional[str] = typer.Option(None, "--web-search-proxy", help="Proxy used only for web search"),
    web_search_max_context_chars: Optional[int] = typer.Option(None, "--web-search-max-context-chars", help="Max chars from web search context"),
    web_search_rpm: Optional[int] = typer.Option(None, "--web-search-rpm", help="Rate limit for web search (req/min)"),
    preflight: Optional[bool] = typer.Option(None, "--preflight/--no-preflight", help="Validate RAG settings before execution"),
    preflight_network: Optional[bool] = typer.Option(None, "--preflight-network/--no-preflight-network", help="Check Qdrant/WebSearch endpoints in preflight"),
):
    from versline.services.rag import RAGPipeline

    if rerank:
        logger.warning(
            "--rerank is ignored for ingest because reranking is only used in retrieval/generation paths."
        )

    effective_auto_tune = settings.rag.auto_tune if auto_tune is None else bool(auto_tune)
    effective_low_memory = settings.rag.low_memory if low_memory is None else bool(low_memory)
    effective_preflight = settings.rag.preflight_enabled if preflight is None else bool(preflight)
    effective_preflight_network = settings.rag.preflight_network if preflight_network is None else bool(preflight_network)
    effective_hybrid = settings.rag.hybrid_enabled if hybrid is None else bool(hybrid)
    if effective_low_memory and hybrid is None and effective_hybrid:
        effective_hybrid = False
        logger.info(
            "Low-memory mode auto-disabled hybrid sparse indexing to reduce model memory footprint. "
            "Use --hybrid to force-enable it."
        )

    tuning_provider = embedding_provider or settings.rag.embedding_provider
    tuning_embedding_device = embedding_device if embedding_device is not None else settings.rag.embedding_device
    tuning_embedding_batch_size = (
        embedding_batch_size if embedding_batch_size is not None else settings.rag.embedding_batch_size
    )
    tuning_ingestion_batch_size = (
        ingestion_batch_size if ingestion_batch_size is not None else settings.rag.ingestion_batch_size
    )

    tuning_decision = tune_ingest_settings(
        auto_tune=effective_auto_tune,
        low_memory=effective_low_memory,
        embedding_provider=tuning_provider,
        embedding_device=tuning_embedding_device,
        embedding_device_explicit=embedding_device is not None,
        embedding_batch_size=tuning_embedding_batch_size,
        ingestion_batch_size=tuning_ingestion_batch_size,
        max_ram_mb=settings.resource.max_ram_mb,
    )
    embedding_device = tuning_decision.embedding_device
    embedding_batch_size = tuning_decision.embedding_batch_size
    ingestion_batch_size = tuning_decision.ingestion_batch_size

    if effective_auto_tune or effective_low_memory:
        logger.info(
            "Ingest tuning applied: "
            f"profile={tuning_decision.profile}, "
            f"embedding_device={embedding_device}, "
            f"embedding_batch_size={embedding_batch_size}, "
            f"ingestion_batch_size={ingestion_batch_size}"
        )

    _apply_llm_overrides(provider, model, api_key, api_endpoint, proxy)
    _apply_rag_overrides(
        vector_size=vector_size,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        parent_child_enabled=parent_child,
        parent_chunk_size=parent_chunk_size,
        parent_chunk_overlap=parent_chunk_overlap,
        parent_child_paragraph_mode=parent_child_paragraph,
        parent_chunk_delimiters=parent_chunk_delimiters,
        child_chunk_delimiters=child_chunk_delimiters,
        parent_child_fetch_k=parent_child_fetch_k,
        ingestion_batch_size=ingestion_batch_size,
        retrieve_fetch_k=retrieve_fetch_k,
        hybrid_dense_weight=hybrid_dense_weight,
        hybrid_lexical_weight=hybrid_lexical_weight,
        embedding_provider=embedding_provider,
        embedding_api_key=embedding_api_key,
        embedding_api_endpoint=embedding_api_endpoint,
        embedding_model_path=embedding_model_path,
        embedding_cache_dir=embedding_cache_dir,
        embedding_local_files_only=embedding_local_files_only,
        embedding_use_fp16=embedding_use_fp16,
        embedding_device=embedding_device,
        embedding_batch_size=embedding_batch_size,
        embedding_inference_backend=embedding_inference_backend,
        openvino_cache_dir=openvino_cache_dir,
        embedding_timeout_seconds=embedding_timeout_seconds,
        generation_timeout_seconds=generation_timeout_seconds,
        qdrant_timeout_seconds=qdrant_timeout_seconds,
        rerank_timeout_seconds=rerank_timeout_seconds,
        log_every_batches=log_every_batches,
        preflight_enabled=effective_preflight,
        preflight_network=effective_preflight_network,
        embedding_proxy=embedding_proxy,
        sparse_embedding_proxy=sparse_proxy,
        sparse_embedding_cache_dir=sparse_cache_dir,
        sparse_embedding_local_files_only=sparse_local_files_only,
        sparse_embedding_provider=sparse_provider,
        sparse_embedding_model_path=sparse_model_path,
        sparse_embedding_use_fp16=sparse_use_fp16,
        sparse_embedding_device=sparse_device,
        sparse_embedding_batch_size=sparse_batch_size,
        generation_proxy=generation_proxy,
        qdrant_proxy=qdrant_proxy,
        embedding_rpm=embedding_rpm,
        embedding_tpm=embedding_tpm,
        generation_rpm=generation_rpm,
        generation_tpm=generation_tpm,
        qdrant_rpm=qdrant_rpm,
        retry_max_retries=retry_max_retries,
        retry_base_delay_seconds=retry_base_delay_seconds,
        retry_max_delay_seconds=retry_max_delay_seconds,
        hybrid=effective_hybrid,
        sparse_model=sparse_model,
        rerank_enabled=False,
        rerank_provider=rerank_provider,
        rerank_model=rerank_model,
        rerank_api_key=rerank_api_key,
        rerank_api_endpoint=rerank_api_endpoint,
        rerank_proxy=rerank_proxy,
        rerank_model_path=rerank_model_path,
        rerank_cache_dir=rerank_cache_dir,
        rerank_local_files_only=rerank_local_files_only,
        rerank_device=rerank_device,
        rerank_batch_size=rerank_batch_size,
        rerank_inference_backend=rerank_inference_backend,
        rerank_onnx_providers=rerank_onnx_providers,
        rerank_rpm=rerank_rpm,
        rerank_tpm=rerank_tpm,
        token_limit_mode=token_limit_mode,
        mcp_enabled=mcp,
        mcp_transport=mcp_transport,
        mcp_server_url=mcp_server_url,
        mcp_server_command=mcp_server_command,
        mcp_server_args=mcp_server_args,
        mcp_tool_name=mcp_tool_name,
        mcp_timeout_seconds=mcp_timeout_seconds,
        mcp_max_context_chars=mcp_max_context_chars,
        mcp_proxy=mcp_proxy,
        web_search_enabled=web_search,
        web_search_provider=web_search_provider,
        web_search_api_key=web_search_api_key,
        web_search_endpoint=web_search_endpoint,
        web_search_timeout_seconds=web_search_timeout_seconds,
        web_search_top_k=web_search_top_k,
        web_search_proxy=web_search_proxy,
        web_search_max_context_chars=web_search_max_context_chars,
        web_search_rpm=web_search_rpm,
    )

    pipeline = RAGPipeline(
        collection_name=collection,
        embedding_model=embedding_model,
        generation_model=model,
        qdrant_url=qdrant_url,
        qdrant_api_key=qdrant_api_key,
    )
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        transient=False,
    ) as progress:
        task = progress.add_task("Preparing ingestion...", total=100)

        def progress_handler(current: float, total: float, message: str):
            progress.update(task, completed=current, total=total, description=message)

        result = pipeline.ingest_path(
            input_path=str(input_path),
            input_type=input_type,
            collection_name=collection,
            reset_collection=reset,
            resume=resume,
            force=force,
            progress_callback=progress_handler,
        )

    logger.success(f"Ingestion completed: {result}")
    print_cost_report(pipeline.tracker, api_key=settings.llm.api_key)


@app.command("ask")
def ask(
    query: str = typer.Argument(..., help="User query"),
    collection: Optional[str] = typer.Option(None, "--collection", "-c", help="Collection name"),
    top_k: int = typer.Option(5, "--top-k", help="Number of retrieved chunks"),
    provider: Optional[str] = typer.Option(None, "--provider", help="LLM Provider"),
    model: Optional[str] = typer.Option(None, "--model", help="Generation model override"),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model", help="Embedding model override"),
    embedding_provider: Optional[str] = typer.Option(None, "--embedding-provider", help="Dense embedding provider (openai/openrouter/avalai/openaicompatible/fastembed/sentence-transformers[sentence|sentence_transformers]/flagembedding/openvino)"),
    embedding_api_key: Optional[str] = typer.Option(None, "--embedding-api-key", help="Embedding API key override"),
    embedding_api_endpoint: Optional[str] = typer.Option(None, "--embedding-api-endpoint", help="Embedding API endpoint override"),
    embedding_model_path: Optional[str] = typer.Option(None, "--embedding-model-path", help="Local path for dense embedding model artifacts"),
    embedding_cache_dir: Optional[str] = typer.Option(None, "--embedding-cache-dir", help="Dense embedding cache directory (enables local-only mode)"),
    embedding_local_files_only: Optional[bool] = typer.Option(None, "--embedding-local-files-only/--no-embedding-local-files-only", help="Use local files only for dense embedding model"),
    embedding_use_fp16: Optional[bool] = typer.Option(None, "--embedding-use-fp16/--no-embedding-use-fp16", help="Use fp16 for dense local backends when supported"),
    embedding_device: Optional[str] = typer.Option(None, "--embedding-device", help="Dense embedding device (cpu/cuda)"),
    embedding_batch_size: Optional[int] = typer.Option(None, "--embedding-batch-size", help="Dense embedding batch size"),
    embedding_inference_backend: Optional[str] = typer.Option(None, "--embedding-backend", help="Dense embedding inference backend: auto or openvino"),
    openvino_cache_dir: Optional[str] = typer.Option(None, "--openvino-cache-dir", help="Cache directory for OpenVINO compiled artifacts"),
    embedding_timeout_seconds: Optional[float] = typer.Option(None, "--embedding-timeout", help="Embedding timeout seconds"),
    generation_timeout_seconds: Optional[float] = typer.Option(None, "--generation-timeout", help="Generation timeout seconds"),
    qdrant_timeout_seconds: Optional[float] = typer.Option(None, "--qdrant-timeout", help="Qdrant timeout seconds"),
    rerank_timeout_seconds: Optional[float] = typer.Option(None, "--rerank-timeout", help="Rerank timeout seconds"),
    sparse_model: Optional[str] = typer.Option(None, "--sparse-model", help="Sparse embedding model for native hybrid retrieval"),
    vector_size: Optional[int] = typer.Option(None, "--vector-size", min=1, help="Fixed vector size for collection creation (defaults to embedding dimension when omitted)"),
    chunk_size: Optional[int] = typer.Option(None, "--chunk-size", help="Chunk size in characters"),
    chunk_overlap: Optional[int] = typer.Option(None, "--chunk-overlap", help="Chunk overlap in characters"),
    parent_child: Optional[bool] = typer.Option(None, "--parent-child/--no-parent-child", help="Enable hierarchical parent-child retrieval"),
    parent_chunk_size: Optional[int] = typer.Option(None, "--parent-chunk-size", help="Parent chunk size in characters"),
    parent_chunk_overlap: Optional[int] = typer.Option(None, "--parent-chunk-overlap", help="Parent chunk overlap in characters"),
    parent_child_paragraph: Optional[bool] = typer.Option(None, "--parent-child-paragraph/--no-parent-child-paragraph", help="Prefer paragraph boundaries (double newline) for parent-child chunking"),
    parent_chunk_delimiters: Optional[str] = typer.Option(None, "--parent-chunk-delimiters", help="Comma-separated delimiters for parent chunk boundaries (supports escaped values like \\n\\n)"),
    child_chunk_delimiters: Optional[str] = typer.Option(None, "--child-chunk-delimiters", help="Comma-separated delimiters for child chunk boundaries (supports escaped values like \\n\\n)"),
    parent_child_fetch_k: Optional[int] = typer.Option(None, "--parent-child-fetch-k", help="Child candidates fetched before parent expansion"),
    ingestion_batch_size: Optional[int] = typer.Option(None, "--ingestion-batch-size", help="Ingestion batch size"),
    log_every_batches: Optional[int] = typer.Option(None, "--log-every-batches", help="Emit ingest logs every N batches"),
    retrieve_fetch_k: Optional[int] = typer.Option(None, "--retrieve-fetch-k", help="Dense candidates fetched before rerank/hybrid"),
    hybrid_dense_weight: Optional[float] = typer.Option(None, "--hybrid-dense-weight", help="Dense score weight in hybrid ranking"),
    hybrid_lexical_weight: Optional[float] = typer.Option(None, "--hybrid-lexical-weight", help="Lexical score weight in hybrid ranking"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="Provider API key"),
    api_endpoint: Optional[str] = typer.Option(None, "--api-endpoint", help="Custom API endpoint"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL"),
    embedding_proxy: Optional[str] = typer.Option(None, "--embedding-proxy", help="Proxy used only for embeddings"),
    sparse_proxy: Optional[str] = typer.Option(None, "--sparse-proxy", help="Proxy used for sparse embedding model download/init"),
    sparse_cache_dir: Optional[str] = typer.Option(None, "--sparse-cache-dir", help="Sparse FastEmbed cache directory (forces local-files-only mode)"),
    sparse_local_files_only: Optional[bool] = typer.Option(None, "--sparse-local-files-only/--no-sparse-local-files-only", help="Use local sparse model files only"),
    sparse_provider: Optional[str] = typer.Option(None, "--sparse-provider", help="Sparse provider (fastembed/flagembedding) or compatibility values: same/auto/openai/openrouter/avalai/openaicompatible/sentence-transformers/openvino"),
    sparse_model_path: Optional[str] = typer.Option(None, "--sparse-model-path", help="Local path for sparse model artifacts"),
    sparse_use_fp16: Optional[bool] = typer.Option(None, "--sparse-use-fp16/--no-sparse-use-fp16", help="Use fp16 for FlagEmbedding sparse backend"),
    sparse_device: Optional[str] = typer.Option(None, "--sparse-device", help="Sparse backend device (cpu/cuda)"),
    sparse_batch_size: Optional[int] = typer.Option(None, "--sparse-batch-size", help="Sparse backend batch size"),
    generation_proxy: Optional[str] = typer.Option(None, "--generation-proxy", help="Proxy used only for generation"),
    qdrant_proxy: Optional[str] = typer.Option(None, "--qdrant-proxy", help="Proxy used only for Qdrant"),
    qdrant_url: Optional[str] = typer.Option(None, "--qdrant-url", help="Qdrant URL"),
    qdrant_api_key: Optional[str] = typer.Option(None, "--qdrant-api-key", help="Qdrant API key"),
    hybrid: Optional[bool] = typer.Option(None, "--hybrid/--no-hybrid", help="Enable or disable hybrid retrieval"),
    embedding_rpm: Optional[int] = typer.Option(None, "--embedding-rpm", help="Rate limit for embeddings (req/min)"),
    embedding_tpm: Optional[int] = typer.Option(None, "--embedding-tpm", help="Token limit for embeddings (tokens/min)"),
    generation_rpm: Optional[int] = typer.Option(None, "--generation-rpm", help="Rate limit for generation (req/min)"),
    generation_tpm: Optional[int] = typer.Option(None, "--generation-tpm", help="Token limit for generation (tokens/min)"),
    qdrant_rpm: Optional[int] = typer.Option(None, "--qdrant-rpm", help="Rate limit for qdrant (req/min)"),
    retry_max_retries: Optional[int] = typer.Option(None, "--retry-max-retries", help="Max retries for external requests"),
    retry_base_delay_seconds: Optional[float] = typer.Option(None, "--retry-base-delay", help="Base retry delay (seconds)"),
    retry_max_delay_seconds: Optional[float] = typer.Option(None, "--retry-max-delay", help="Max retry delay (seconds)"),
    rerank: Optional[bool] = typer.Option(None, "--rerank/--no-rerank", help="Enable dedicated rerank model"),
    rerank_provider: Optional[str] = typer.Option(None, "--rerank-provider", help="Rerank provider (cohere/jina/openai/openrouter/avalai/openaicompatible/local/fastembed/sentence-transformers/openvino/flagembedding/same/auto)"),
    rerank_model: Optional[str] = typer.Option(None, "--rerank-model", help="Dedicated rerank model"),
    rerank_api_key: Optional[str] = typer.Option(None, "--rerank-api-key", help="Rerank API key"),
    rerank_api_endpoint: Optional[str] = typer.Option(None, "--rerank-api-endpoint", help="Rerank API endpoint"),
    rerank_proxy: Optional[str] = typer.Option(None, "--rerank-proxy", help="Proxy used only for rerank"),
    rerank_model_path: Optional[str] = typer.Option(None, "--rerank-model-path", help="Local path for rerank model artifacts"),
    rerank_cache_dir: Optional[str] = typer.Option(None, "--rerank-cache-dir", help="Rerank model cache directory (enables local-only mode)"),
    rerank_local_files_only: Optional[bool] = typer.Option(None, "--rerank-local-files-only/--no-rerank-local-files-only", help="Use local files only for rerank model"),
    rerank_device: Optional[str] = typer.Option(None, "--rerank-device", help="Local rerank device (cpu/cuda)"),
    rerank_batch_size: Optional[int] = typer.Option(None, "--rerank-batch-size", help="Local rerank batch size"),
    rerank_inference_backend: Optional[str] = typer.Option(None, "--rerank-backend", help="Rerank inference backend: auto or openvino"),
    rerank_onnx_providers: Optional[str] = typer.Option(None, "--rerank-onnx-providers", help="Comma-separated ONNX provider order for fastembed rerank"),
    rerank_rpm: Optional[int] = typer.Option(None, "--rerank-rpm", help="Rate limit for rerank (req/min)"),
    rerank_tpm: Optional[int] = typer.Option(None, "--rerank-tpm", help="Token limit for rerank (tokens/min)"),
    token_limit_mode: Optional[str] = typer.Option(
        None,
        "--token-limit-mode",
        help="TPM mode: estimate_only or estimate_and_adjust",
    ),
    mcp: Optional[bool] = typer.Option(None, "--mcp/--no-mcp", help="Enable MCP external context"),
    mcp_transport: Optional[str] = typer.Option(None, "--mcp-transport", help="MCP transport: http or stdio"),
    mcp_server_url: Optional[str] = typer.Option(None, "--mcp-server-url", help="MCP server URL (http mode)"),
    mcp_server_command: Optional[str] = typer.Option(None, "--mcp-server-command", help="MCP server command (stdio mode)"),
    mcp_server_args: Optional[str] = typer.Option(None, "--mcp-server-args", help="MCP server args string (stdio mode)"),
    mcp_tool_name: Optional[str] = typer.Option(None, "--mcp-tool", help="MCP tool name for context retrieval"),
    mcp_timeout_seconds: Optional[int] = typer.Option(None, "--mcp-timeout", help="MCP timeout seconds"),
    mcp_max_context_chars: Optional[int] = typer.Option(None, "--mcp-max-context-chars", help="Max chars from MCP context"),
    mcp_proxy: Optional[str] = typer.Option(None, "--mcp-proxy", help="Proxy only for MCP http transport"),
    web_search: Optional[bool] = typer.Option(None, "--web-search/--no-web-search", help="Enable external web search context"),
    web_search_provider: Optional[str] = typer.Option(None, "--web-search-provider", help="Web search provider (duckduckgo, tavily)"),
    web_search_api_key: Optional[str] = typer.Option(None, "--web-search-api-key", help="Web search provider API key"),
    web_search_endpoint: Optional[str] = typer.Option(None, "--web-search-endpoint", help="Custom web search endpoint"),
    web_search_timeout_seconds: Optional[int] = typer.Option(None, "--web-search-timeout", help="Web search timeout seconds"),
    web_search_top_k: Optional[int] = typer.Option(None, "--web-search-top-k", help="Web results included as external context"),
    web_search_proxy: Optional[str] = typer.Option(None, "--web-search-proxy", help="Proxy used only for web search"),
    web_search_max_context_chars: Optional[int] = typer.Option(None, "--web-search-max-context-chars", help="Max chars from web search context"),
    web_search_rpm: Optional[int] = typer.Option(None, "--web-search-rpm", help="Rate limit for web search (req/min)"),
    preflight: bool = typer.Option(True, "--preflight/--no-preflight", help="Validate RAG settings before execution"),
    preflight_network: bool = typer.Option(True, "--preflight-network/--no-preflight-network", help="Check Qdrant/WebSearch endpoints in preflight"),
):
    from versline.services.rag import RAGPipeline

    _apply_llm_overrides(provider, model, api_key, api_endpoint, proxy)
    _apply_rag_overrides(
        vector_size=vector_size,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        parent_child_enabled=parent_child,
        parent_chunk_size=parent_chunk_size,
        parent_chunk_overlap=parent_chunk_overlap,
        parent_child_paragraph_mode=parent_child_paragraph,
        parent_chunk_delimiters=parent_chunk_delimiters,
        child_chunk_delimiters=child_chunk_delimiters,
        parent_child_fetch_k=parent_child_fetch_k,
        ingestion_batch_size=ingestion_batch_size,
        retrieve_fetch_k=retrieve_fetch_k,
        hybrid_dense_weight=hybrid_dense_weight,
        hybrid_lexical_weight=hybrid_lexical_weight,
        embedding_provider=embedding_provider,
        embedding_api_key=embedding_api_key,
        embedding_api_endpoint=embedding_api_endpoint,
        embedding_model_path=embedding_model_path,
        embedding_cache_dir=embedding_cache_dir,
        embedding_local_files_only=embedding_local_files_only,
        embedding_use_fp16=embedding_use_fp16,
        embedding_device=embedding_device,
        embedding_batch_size=embedding_batch_size,
        embedding_inference_backend=embedding_inference_backend,
        openvino_cache_dir=openvino_cache_dir,
        embedding_timeout_seconds=embedding_timeout_seconds,
        generation_timeout_seconds=generation_timeout_seconds,
        qdrant_timeout_seconds=qdrant_timeout_seconds,
        rerank_timeout_seconds=rerank_timeout_seconds,
        log_every_batches=log_every_batches,
        preflight_enabled=preflight,
        preflight_network=preflight_network,
        embedding_proxy=embedding_proxy,
        sparse_embedding_proxy=sparse_proxy,
        sparse_embedding_cache_dir=sparse_cache_dir,
        sparse_embedding_local_files_only=sparse_local_files_only,
        sparse_embedding_provider=sparse_provider,
        sparse_embedding_model_path=sparse_model_path,
        sparse_embedding_use_fp16=sparse_use_fp16,
        sparse_embedding_device=sparse_device,
        sparse_embedding_batch_size=sparse_batch_size,
        generation_proxy=generation_proxy,
        qdrant_proxy=qdrant_proxy,
        embedding_rpm=embedding_rpm,
        embedding_tpm=embedding_tpm,
        generation_rpm=generation_rpm,
        generation_tpm=generation_tpm,
        qdrant_rpm=qdrant_rpm,
        retry_max_retries=retry_max_retries,
        retry_base_delay_seconds=retry_base_delay_seconds,
        retry_max_delay_seconds=retry_max_delay_seconds,
        hybrid=hybrid,
        sparse_model=sparse_model,
        rerank_enabled=rerank,
        rerank_provider=rerank_provider,
        rerank_model=rerank_model,
        rerank_api_key=rerank_api_key,
        rerank_api_endpoint=rerank_api_endpoint,
        rerank_proxy=rerank_proxy,
        rerank_model_path=rerank_model_path,
        rerank_cache_dir=rerank_cache_dir,
        rerank_local_files_only=rerank_local_files_only,
        rerank_device=rerank_device,
        rerank_batch_size=rerank_batch_size,
        rerank_inference_backend=rerank_inference_backend,
        rerank_onnx_providers=rerank_onnx_providers,
        rerank_rpm=rerank_rpm,
        rerank_tpm=rerank_tpm,
        token_limit_mode=token_limit_mode,
        mcp_enabled=mcp,
        mcp_transport=mcp_transport,
        mcp_server_url=mcp_server_url,
        mcp_server_command=mcp_server_command,
        mcp_server_args=mcp_server_args,
        mcp_tool_name=mcp_tool_name,
        mcp_timeout_seconds=mcp_timeout_seconds,
        mcp_max_context_chars=mcp_max_context_chars,
        mcp_proxy=mcp_proxy,
        web_search_enabled=web_search,
        web_search_provider=web_search_provider,
        web_search_api_key=web_search_api_key,
        web_search_endpoint=web_search_endpoint,
        web_search_timeout_seconds=web_search_timeout_seconds,
        web_search_top_k=web_search_top_k,
        web_search_proxy=web_search_proxy,
        web_search_max_context_chars=web_search_max_context_chars,
        web_search_rpm=web_search_rpm,
    )

    pipeline = RAGPipeline(
        collection_name=collection,
        embedding_model=embedding_model,
        generation_model=model,
        qdrant_url=qdrant_url,
        qdrant_api_key=qdrant_api_key,
    )
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        transient=False,
    ) as progress:
        task = progress.add_task("Retrieving context...", total=2)
        progress.update(task, completed=1, description="Retrieving and reranking chunks...")
        result = pipeline.generate(query=query, top_k=top_k, collection_name=collection)
        progress.update(task, completed=2, description="Generating final answer...")

    typer.echo("\n=== Answer ===\n")
    typer.echo(result["answer"])
    typer.echo("\n=== Sources ===\n")
    for item in result["sources"]:
        source = item["metadata"].get("source", "unknown")
        score = item["score"]
        typer.echo(f"- {source} (score={score:.4f})")

    print_cost_report(pipeline.tracker, api_key=settings.llm.api_key)
