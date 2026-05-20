import typer
from typing import Optional
from pathlib import Path
import os

from versline.services.question_generator import QuestionDesigner
from versline.core.constants import (
    DEFAULT_SLIDES_PER_BATCH,
    DEFAULT_PAGES_PER_BATCH,
    DEFAULT_WORDS_PER_BATCH,
)
from versline.core.prompts import resolve_user_note

app = typer.Typer(help="Generate questions from documents.")

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    input_path: Optional[Path] = typer.Argument(None, help="Input file or directory", exists=True),
    output_dir: Path = typer.Option("output", "--output", "-o", help="Output directory"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="AI Provider (openai, avalai, gemini, openrouter, custom)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="AI Model name"),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="API Key"),
    base_url: Optional[str] = typer.Option(None, "--base-url", "-b", help="Base URL for custom/OpenAI provider"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL"),
    question_type: str = typer.Option("mcq", "--type", "-t", help="Question type (mcq, open)"),
    language: str = typer.Option("en", "--lang", "-l", help="Language code"),
    count: Optional[int] = typer.Option(None, "--count", "-c", help="Questions per chunk/slide (default: max possible)"),
    
    # Output control
    formats: str = typer.Option("all", "--formats", help="Output formats (csv, anki, html, all) - comma separated"),
    style: Optional[Path] = typer.Option(None, "--style", help="Path to custom CSS file for Anki/HTML"),
    prompt_file: Optional[Path] = typer.Option(None, "--prompt", help="Path to custom prompt file"),

    # Chunking options
    slides_per_batch: int = typer.Option(DEFAULT_SLIDES_PER_BATCH, "--slides-per-batch", help="Number of slides per batch (PPTX)"),
    pages_per_batch: int = typer.Option(DEFAULT_PAGES_PER_BATCH, "--pages-per-batch", help="Number of pages per batch (PDF/DOCX)"),
    words_per_batch: int = typer.Option(DEFAULT_WORDS_PER_BATCH, "--words-per-batch", help="Number of words per batch (Markdown/Text)"),

    force: bool = typer.Option(False, "--force", "-f", help="Force regeneration (ignore cache)"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug mode"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Disable caching"),
    regenerate: bool = typer.Option(False, "--regenerate", "-r", help="Regenerate outputs from cache only"),
    note: Optional[str] = typer.Option(None, "--note", help="Additional instruction to append to the prompt"),
    note_file: Optional[Path] = typer.Option(None, "--note-file", help="Path to a .md or .txt file with additional instructions"),
):
    """
    Generate questions (Flashcards, MCQs) from documents (PDF, PPTX, DOCX, etc.).
    """
    if ctx.invoked_subcommand is not None:
        return

    # If no input path provided and not showing help
    if input_path is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()

    designer = QuestionDesigner(
        input_path=str(input_path),
        output_dir=str(output_dir),
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        proxy_url=proxy,
        question_type=question_type,
        language=language,
        num_questions=count,
        slides_per_batch=slides_per_batch,
        pages_per_batch=pages_per_batch,
        words_per_batch=words_per_batch,
        output_formats=formats,
        style_path=str(style) if style else None,
        prompt_path=str(prompt_file) if prompt_file else None,
        force=force,
        debug=debug,
        no_cache=no_cache,
        user_note=resolve_user_note(note, str(note_file) if note_file else None),
    )

    if regenerate:
        designer.regenerate_from_cache()
    else:
        designer.process()
