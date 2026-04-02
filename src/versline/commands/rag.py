from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from versline.config import settings
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
    embedding_proxy: Optional[str],
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
):
    if embedding_proxy is not None:
        settings.rag.embedding_proxy = embedding_proxy
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
    sparse_model: Optional[str] = typer.Option(None, "--sparse-model", help="Sparse embedding model for native hybrid retrieval"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="Provider API key"),
    api_endpoint: Optional[str] = typer.Option(None, "--api-endpoint", help="Custom API endpoint"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL"),
    embedding_proxy: Optional[str] = typer.Option(None, "--embedding-proxy", help="Proxy used only for embeddings"),
    generation_proxy: Optional[str] = typer.Option(None, "--generation-proxy", help="Proxy used only for generation"),
    qdrant_proxy: Optional[str] = typer.Option(None, "--qdrant-proxy", help="Proxy used only for Qdrant"),
    qdrant_url: Optional[str] = typer.Option(None, "--qdrant-url", help="Qdrant URL"),
    qdrant_api_key: Optional[str] = typer.Option(None, "--qdrant-api-key", help="Qdrant API key"),
    embedding_rpm: Optional[int] = typer.Option(None, "--embedding-rpm", help="Rate limit for embeddings (req/min)"),
    embedding_tpm: Optional[int] = typer.Option(None, "--embedding-tpm", help="Token limit for embeddings (tokens/min)"),
    generation_rpm: Optional[int] = typer.Option(None, "--generation-rpm", help="Rate limit for generation (req/min)"),
    generation_tpm: Optional[int] = typer.Option(None, "--generation-tpm", help="Token limit for generation (tokens/min)"),
    qdrant_rpm: Optional[int] = typer.Option(None, "--qdrant-rpm", help="Rate limit for qdrant (req/min)"),
    retry_max_retries: Optional[int] = typer.Option(None, "--retry-max-retries", help="Max retries for external requests"),
    retry_base_delay_seconds: Optional[float] = typer.Option(None, "--retry-base-delay", help="Base retry delay (seconds)"),
    retry_max_delay_seconds: Optional[float] = typer.Option(None, "--retry-max-delay", help="Max retry delay (seconds)"),
    rerank: Optional[bool] = typer.Option(None, "--rerank/--no-rerank", help="Enable dedicated rerank model"),
    rerank_provider: Optional[str] = typer.Option(None, "--rerank-provider", help="Rerank provider (e.g. cohere)"),
    rerank_model: Optional[str] = typer.Option(None, "--rerank-model", help="Dedicated rerank model"),
    rerank_api_key: Optional[str] = typer.Option(None, "--rerank-api-key", help="Rerank API key"),
    rerank_api_endpoint: Optional[str] = typer.Option(None, "--rerank-api-endpoint", help="Rerank API endpoint"),
    rerank_proxy: Optional[str] = typer.Option(None, "--rerank-proxy", help="Proxy used only for rerank"),
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
):
    from versline.services.rag import RAGPipeline

    _apply_llm_overrides(provider, model, api_key, api_endpoint, proxy)
    _apply_rag_overrides(
        embedding_proxy=embedding_proxy,
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
        hybrid=None,
        sparse_model=sparse_model,
        rerank_enabled=rerank,
        rerank_provider=rerank_provider,
        rerank_model=rerank_model,
        rerank_api_key=rerank_api_key,
        rerank_api_endpoint=rerank_api_endpoint,
        rerank_proxy=rerank_proxy,
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
    sparse_model: Optional[str] = typer.Option(None, "--sparse-model", help="Sparse embedding model for native hybrid retrieval"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="Provider API key"),
    api_endpoint: Optional[str] = typer.Option(None, "--api-endpoint", help="Custom API endpoint"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL"),
    embedding_proxy: Optional[str] = typer.Option(None, "--embedding-proxy", help="Proxy used only for embeddings"),
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
    rerank_provider: Optional[str] = typer.Option(None, "--rerank-provider", help="Rerank provider (e.g. cohere)"),
    rerank_model: Optional[str] = typer.Option(None, "--rerank-model", help="Dedicated rerank model"),
    rerank_api_key: Optional[str] = typer.Option(None, "--rerank-api-key", help="Rerank API key"),
    rerank_api_endpoint: Optional[str] = typer.Option(None, "--rerank-api-endpoint", help="Rerank API endpoint"),
    rerank_proxy: Optional[str] = typer.Option(None, "--rerank-proxy", help="Proxy used only for rerank"),
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
):
    from versline.services.rag import RAGPipeline

    _apply_llm_overrides(provider, model, api_key, api_endpoint, proxy)
    _apply_rag_overrides(
        embedding_proxy=embedding_proxy,
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
