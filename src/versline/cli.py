import typer
from loguru import logger
import sys
import os
from pathlib import Path
from typing import Optional
from versline.config import settings, reload_settings
from versline.commands import transcribe, translate, qude, qualcode, rag, slides, summarize
from versline.core.resources import apply_resource_limits


_LOCAL_RAG_PROVIDERS = {
    "fastembed",
    "flagembedding",
    "local",
    "openvino",
    "optimum",
    "optimum-intel",
    "optimum_intel",
    "sentence",
    "sentence-transformers",
    "sentence_transformer",
    "sentence_transformers",
    "sentencetransformer",
    "sentencetransformers",
}


def _normalize_provider(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _extract_cli_option_value(argv: list[str], option_name: str) -> Optional[str]:
    option_prefix = f"{option_name}="
    value: Optional[str] = None
    for idx, token in enumerate(argv):
        if token.startswith(option_prefix):
            value = token[len(option_prefix):]
            continue
        if token == option_name and idx + 1 < len(argv):
            candidate = argv[idx + 1]
            if not candidate.startswith("-"):
                value = candidate
    return value


def _is_local_provider(provider: Optional[str]) -> bool:
    return _normalize_provider(provider) in _LOCAL_RAG_PROVIDERS


def _is_rag_local_execution(argv: list[str]) -> bool:
    try:
        rag_index = argv.index("rag")
    except ValueError:
        return False

    subcommand: Optional[str] = None
    if rag_index + 1 < len(argv):
        candidate = argv[rag_index + 1]
        if not candidate.startswith("-"):
            subcommand = candidate

    embedding_provider = _extract_cli_option_value(argv, "--embedding-provider")
    effective_embedding_provider = embedding_provider or settings.rag.embedding_provider
    has_local_embedding = _is_local_provider(effective_embedding_provider)

    if subcommand == "ingest":
        return has_local_embedding

    rerank_provider = _extract_cli_option_value(argv, "--rerank-provider")
    effective_rerank_provider = rerank_provider or settings.rag.rerank_provider

    rerank_enabled = settings.rag.rerank_enabled
    if "--rerank" in argv:
        rerank_enabled = True
    if "--no-rerank" in argv:
        rerank_enabled = False

    has_local_rerank = rerank_enabled and _is_local_provider(effective_rerank_provider)
    return has_local_embedding or has_local_rerank


def _is_rag_ingest(argv: list[str]) -> bool:
    return any(
        argv[i] == "rag" and i + 1 < len(argv) and argv[i + 1] == "ingest"
        for i in range(len(argv))
    )

app = typer.Typer(
    name="versline",
    help="[bold green]Miroverse Toolkit[/bold green] CLI and Library for [yellow]Media Transcription, Document Translation, and Question Generation using LLMs.",
    add_completion=True,
    rich_markup_mode="rich",
)

# Register subcommands
app.add_typer(transcribe.app, name="transcribe", help="[cyan]Convert audio/video to text[/cyan] using advanced LLMs.")
app.add_typer(translate.app, name="translate", help="[cyan]Translate text files[/cyan] to other languages.")
app.add_typer(qude.app, name="qude", help="[cyan]Generate questions[/cyan] from documents (Flashcards, MCQs).")
app.add_typer(qualcode.app, name="qualcode", help="[cyan]Run qualitative coding[/cyan] on markdown files.")
app.add_typer(slides.app, name="slides", help="[cyan]Generate immersive HTML/TS slides[/cyan] from markdown files.")
app.add_typer(summarize.app, name="summarize", help="[cyan]Summarize files[/cyan] (outline, detailed, or slides mode).")
app.add_typer(rag.app, name="rag", help="[cyan]Run RAG pipelines[/cyan] with ingestion and querying.")

@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    env_file: Optional[Path] = typer.Option(
        None,
        "--env-file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
        help="Path to a custom .env file loaded before command execution",
    ),
):
    """
    [bold]Versline[/bold] is a powerful toolkit for automated media processing.
    
    [underline]Features:[/underline]
    
    * :microphone: [bold green]Transcribe[/bold green]: Accurate audio-to-text with speaker identification context.
    * :globe_with_meridians: [bold blue]Download[/bold blue]: Integrated file downloader (supports auto-download in transcribe).
    * :gear: [bold yellow]Flexible ConfiTranslate[/bold blue]: Context-aware translation for documents
    
    [dim]Run 'versline COMMAND --help' for more info on specific commands.[/dim]
    """
    if env_file is not None:
        reload_settings(env_file=env_file)

    _argv = sys.argv[1:]
    should_apply_limits = _is_rag_local_execution(_argv)

    # OpenVINO/HF model init during local rag ingest can trigger short-lived
    # memory spikes. Use a less aggressive soft trigger by default, while still
    # allowing users to override both knobs explicitly via environment.
    if should_apply_limits and _is_rag_ingest(_argv):
        os.environ.setdefault("VERSLINE_RESOURCE_RAM_SOFT_TRIGGER_PCT", "95")

    configure_logging(verbose)
    if should_apply_limits:
        apply_resource_limits(
            max_ram_mb=settings.resource.max_ram_mb,
            max_cpu_cores=settings.resource.max_cpu_cores,
            max_gpu_vram_fraction=settings.resource.max_gpu_vram_fraction,
        )
    # logger.debug(f"Loaded settings: {settings.model_dump()}")

def configure_logging(verbose: bool):
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    # Use a lambda to ensure we write to the current sys.stderr (which might be patched by rich)
    logger.add(lambda msg: sys.stderr.write(msg), level=level, format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>\n", colorize=True)

if __name__ == "__main__":
    app()
