from pathlib import Path
from typing import Optional

import typer
from loguru import logger

from versline.config import settings

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


@app.command("ingest")
def ingest(
    file_path: Path = typer.Argument(..., exists=True, help="Path to source document (currently markdown/text)"),
    collection: Optional[str] = typer.Option(None, "--collection", "-c", help="Target collection name"),
    input_type: Optional[str] = typer.Option(None, "--input-type", help="Input type override, e.g. markdown"),
    reset: bool = typer.Option(False, "--reset", help="Drop and recreate collection before ingest"),
    provider: Optional[str] = typer.Option(None, "--provider", help="LLM Provider"),
    model: Optional[str] = typer.Option(None, "--model", help="Generation model override"),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model", help="Embedding model override"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="Provider API key"),
    api_endpoint: Optional[str] = typer.Option(None, "--api-endpoint", help="Custom API endpoint"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL"),
    qdrant_url: Optional[str] = typer.Option(None, "--qdrant-url", help="Qdrant URL"),
    qdrant_api_key: Optional[str] = typer.Option(None, "--qdrant-api-key", help="Qdrant API key"),
):
    from versline.services.rag import RAGPipeline

    _apply_llm_overrides(provider, model, api_key, api_endpoint, proxy)

    pipeline = RAGPipeline(
        collection_name=collection,
        embedding_model=embedding_model,
        generation_model=model,
        qdrant_url=qdrant_url,
        qdrant_api_key=qdrant_api_key,
    )
    result = pipeline.ingest_file(
        file_path=str(file_path),
        input_type=input_type,
        collection_name=collection,
        reset_collection=reset,
    )
    logger.success(f"Ingestion completed: {result}")


@app.command("ask")
def ask(
    query: str = typer.Argument(..., help="User query"),
    collection: Optional[str] = typer.Option(None, "--collection", "-c", help="Collection name"),
    top_k: int = typer.Option(5, "--top-k", help="Number of retrieved chunks"),
    provider: Optional[str] = typer.Option(None, "--provider", help="LLM Provider"),
    model: Optional[str] = typer.Option(None, "--model", help="Generation model override"),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model", help="Embedding model override"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="Provider API key"),
    api_endpoint: Optional[str] = typer.Option(None, "--api-endpoint", help="Custom API endpoint"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL"),
    qdrant_url: Optional[str] = typer.Option(None, "--qdrant-url", help="Qdrant URL"),
    qdrant_api_key: Optional[str] = typer.Option(None, "--qdrant-api-key", help="Qdrant API key"),
):
    from versline.services.rag import RAGPipeline

    _apply_llm_overrides(provider, model, api_key, api_endpoint, proxy)

    pipeline = RAGPipeline(
        collection_name=collection,
        embedding_model=embedding_model,
        generation_model=model,
        qdrant_url=qdrant_url,
        qdrant_api_key=qdrant_api_key,
    )

    result = pipeline.generate(query=query, top_k=top_k, collection_name=collection)
    typer.echo("\n=== Answer ===\n")
    typer.echo(result["answer"])
    typer.echo("\n=== Sources ===\n")
    for item in result["sources"]:
        source = item["metadata"].get("source", "unknown")
        score = item["score"]
        typer.echo(f"- {source} (score={score:.4f})")
