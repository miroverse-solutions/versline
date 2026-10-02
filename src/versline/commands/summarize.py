import typer
from versline.commands._common import EXTRA_BODY_HELP, apply_extra_body_option
from typing import Optional
from pathlib import Path
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from loguru import logger

from versline.services.summarizer import TextSummarizer, MODES, _AUTO_LANG
from versline.config import settings
from versline.services.pricing import print_cost_report
from versline.core.prompts import resolve_user_note
from typing import Optional

app = typer.Typer(help="Summarize files in multiple modes.")


def _resolve_output_path(file_path: Path, output: Optional[Path], mode: str) -> Path:
    if output:
        base = output.with_suffix("") if output.suffix else output
    else:
        base = file_path.with_name(f"{file_path.stem}_summary_{mode}")
    return base.with_suffix(".md")


@app.callback(invoke_without_command=True)
def summarize_file(
    ctx: typer.Context,
    file_path: Optional[Path] = typer.Argument(
        None, help="Path to the input file", exists=True
    ),
    mode: str = typer.Option(
        "detailed",
        "--mode",
        "-m",
        help=f"Summarization mode: {', '.join(MODES)}",
    ),
    output_lang: str = typer.Option(
        _AUTO_LANG,
        "--output-lang",
        "-l",
        help=(
            "Language to write the summary in. "
            "Default 'auto' keeps the same language as the source. "
            "Example: 'Persian', 'English', 'French'."
        ),
    ),
    preserve_terms: bool = typer.Option(
        True,
        "--preserve-terms/--no-preserve-terms",
        help=(
            "When outputting in a different language, include the original-language "
            "term in parentheses after each specialised technical term."
        ),
    ),
    didactic: bool = typer.Option(
        False,
        "--didactic/--no-didactic",
        "-d",
        help=(
            "Enable pedagogical restructuring mode. "
            "The LLM first analyses the full document to build a teaching blueprint "
            "(concept dependencies, optimal order, sections to expand), then generates "
            "the output using that blueprint — reordering content where needed for "
            "maximum comprehension. Uses prompt caching to avoid re-billing the "
            "document tokens in the second phase."
        ),
    ),    compression: Optional[int] = typer.Option(
        None,
        "--compression",
        "-c",
        min=1,
        max=100,
        help=(
            "Target output length as a percentage of the original text (1\u2013100). "
            "10 = very brief (only essentials); 50 = moderate; 90 = near-complete. "
            "Omit to let the LLM decide based on the selected mode."
        ),
    ),    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output .md file path"
    ),
    model: Optional[str] = typer.Option(None, help="LLM model to use (overrides config)"),
    provider: Optional[str] = typer.Option(
        None, help="LLM provider (Google, OpenAI, OpenRouter, AvalAI, OpenAICompatible)"
    ),
    api_key: Optional[str] = typer.Option(None, help="API key for the provider"),
    api_endpoint: Optional[str] = typer.Option(None, help="Custom API endpoint"),
    proxy: Optional[str] = typer.Option(None, help="Proxy URL"),
    extra_body: Optional[str] = typer.Option(None, "--extra-body", help=EXTRA_BODY_HELP),
    note: Optional[str] = typer.Option(None, "--note", help="Additional instruction to append to the prompt"),
    note_file: Optional[Path] = typer.Option(None, "--note-file", help="Path to a .md or .txt file with an additional instruction"),
):
    """
    [bold blue]Summarize a file[/bold blue] using one of three modes:

    \b
    [cyan]outline[/cyan]   — Hierarchical detailed outline (فهرست تفصیلی)
    [cyan]detailed[/cyan]  — Detailed summary for study (خلاصه تفصیلی)
    [cyan]slides[/cyan]    — Full slide outline for presentation (اوت‌لاین اسلاید)

    Use [bold]--output-lang[/bold] to generate the summary directly in another language
    (the LLM writes in that language natively, no post-translation step).
    Use [bold]--preserve-terms[/bold] to keep technical terms from the source language
    alongside their equivalents, e.g.: شبکه عصبی (neural network).
    Use [bold]--didactic[/bold] for a two-phase pedagogical pipeline that reorders and
    expands content for maximum comprehension, backed by prompt caching.
    """
    if ctx.invoked_subcommand is not None:
        return

    if not file_path:
        typer.echo(ctx.get_help())
        raise typer.Exit()

    if mode not in MODES:
        typer.echo(
            f"[red]Invalid mode '{mode}'. Choose from: {', '.join(MODES)}[/red]",
            err=True,
        )
        raise typer.Exit(code=1)

    if model:
        settings.llm.model = model
    if provider:
        settings.llm.provider = provider
    if api_key:
        settings.llm.api_key = api_key
    if api_endpoint:
        settings.llm.api_endpoint = api_endpoint
    if proxy:
        settings.llm.proxy = proxy
    if extra_body:
        apply_extra_body_option(extra_body)

    logger.info(f"Starting summarization [{mode}{'|didactic' if didactic else ''}{'|' + str(compression) + '%' if compression else ''}] for: {file_path}")

    summarizer = TextSummarizer(
        mode=mode,
        output_lang=output_lang,
        preserve_terms=preserve_terms,
        didactic=didactic,
        compression=compression,
        user_note=resolve_user_note(note=note, note_file=str(note_file) if note_file else None),
    )

    try:
        result = ""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            redirect_stdout=True,
            redirect_stderr=True,
        ) as progress:
            task_id = progress.add_task("[blue]Summarizing…", total=100)

            def progress_handler(current, total, message):
                progress.update(
                    task_id, completed=current, total=total, description=message
                )

            result = summarizer.process_file(
                str(file_path),
                progress_callback=progress_handler,
            )

        out_path = _resolve_output_path(file_path, output, mode)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result, encoding="utf-8")

        logger.success(f"Summary saved to: {out_path}")
        print_cost_report(summarizer.tracker, api_key=settings.llm.api_key)

    except Exception as exc:
        logger.error(f"Summarization failed: {exc}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
