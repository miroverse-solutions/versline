from pathlib import Path
from typing import List, Optional
import json

import typer
from versline.commands._common import EXTRA_BODY_HELP, apply_extra_body_option
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from loguru import logger

from versline.config import settings
from versline.services.qualitative_coding import QualitativeCoder
from versline.services.pricing import print_cost_report
from versline.core.prompts import resolve_user_note

app = typer.Typer(help="Qualitative coding for Markdown files with multiple research methods.")


def _extract_codes_from_text(raw_text: str) -> List[str]:
    text = raw_text.replace("\r\n", "\n")
    for separator in [",", ";", "\t"]:
        text = text.replace(separator, "\n")
    return [line.strip() for line in text.split("\n") if line.strip()]


def _load_codebook_codes(codebook_path: Path) -> List[str]:
    content = codebook_path.read_text(encoding="utf-8")
    suffix = codebook_path.suffix.lower()

    if suffix == ".json":
        data = json.loads(content)
        if isinstance(data, list):
            return [str(item).strip() for item in data if str(item).strip()]
        if isinstance(data, dict):
            if isinstance(data.get("codes"), list):
                return [str(item).strip() for item in data["codes"] if str(item).strip()]
        raise ValueError("Unsupported JSON codebook schema. Use array or {\"codes\": [...]}.")

    return _extract_codes_from_text(content)


@app.callback(invoke_without_command=True)
def qualcode_file(
    ctx: typer.Context,
    input_path: Optional[Path] = typer.Argument(None, help="Path to markdown/text file", exists=True),
    output_dir: Path = typer.Option("output", "--output", "-o", help="Output directory"),
    methods: List[str] = typer.Option(["thematic"], "--method", "-m", help="Coding method (repeatable): thematic, grounded, content, framework, colaizzi"),
    formats: List[str] = typer.Option(["json", "markdown"], "--format", help="Output formats (repeatable): json, markdown, csv, segments-csv, detailed-csv"),
    codes: List[str] = typer.Option([], "--code", help="Seed codebook item (repeatable)"),
    codebook: Optional[Path] = typer.Option(None, "--codebook", help="Path to codebook file (.txt, .md, .csv, .json)"),
    central_concepts: Optional[Path] = typer.Option(None, "--central-concepts", help="Path to central concepts file (.md, .markdown, .txt)", exists=True),
    code_mode: str = typer.Option("guided", "--code-mode", help="Codebook policy: guided or strict"),
    analysis_language: str = typer.Option("auto", "--analysis-language", help="Language for analytic fields: auto, fa, en"),
    fail_on_parse_error: bool = typer.Option(False, "--fail-on-parse-error", help="Fail command if any batch JSON parse fails"),
    csv_fill_quotes_from_segments: bool = typer.Option(True, "--csv-fill-quotes-from-segments/--no-csv-fill-quotes-from-segments", help="When CSV quotes are empty, fill from segment text using segment_ids"),
    excel: bool = typer.Option(True, "--excel/--no-excel", help="Export .xlsx alongside every generated CSV output"),
    citation: bool = typer.Option(False, "--citation/--no-citation", help="Include citation evidence (quotes) in coded output"),
    words_per_batch: int = typer.Option(1200, "--words-per-batch", help="Word budget per analysis batch"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM Provider"),
    model: Optional[str] = typer.Option(None, "--model", help="LLM model"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="Provider API key"),
    api_endpoint: Optional[str] = typer.Option(None, "--api-endpoint", help="Custom API endpoint"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL"),
    extra_body: Optional[str] = typer.Option(None, "--extra-body", help=EXTRA_BODY_HELP),
    force: bool = typer.Option(False, "--force", "-f", help="Force rerun and ignore progress cache"),
    note: Optional[str] = typer.Option(None, "--note", help="Additional instruction to append to the prompt"),
    note_file: Optional[Path] = typer.Option(None, "--note-file", help="Path to a .md or .txt file with an additional instruction"),
):
    """Run qualitative coding analysis on a markdown/text file."""
    if ctx.invoked_subcommand is not None:
        return

    if input_path is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()

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

    try:
        codebook_codes = list(codes)
        if codebook:
            if not codebook.exists():
                raise ValueError(f"Codebook file not found: {codebook}")
            codebook_codes.extend(_load_codebook_codes(codebook))

        coder = QualitativeCoder(
            output_dir=str(output_dir),
            methods=methods,
            output_formats=formats,
            codebook_codes=codebook_codes,
            code_mode=code_mode,
            analysis_language=analysis_language,
            fail_on_parse_error=fail_on_parse_error,
            csv_fill_quotes_from_segments=csv_fill_quotes_from_segments,
            export_excel=excel,
            include_citation=citation,
            words_per_batch=words_per_batch,
            force=force,
            central_concepts_path=str(central_concepts) if central_concepts else None,
            user_note=resolve_user_note(note=note, note_file=str(note_file) if note_file else None),
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            transient=False,
        ) as progress:
            task = progress.add_task("Starting qualitative coding...", total=100)

            def progress_handler(current: int, total: int, message: str):
                progress.update(task, completed=current, total=total, description=message)

            outputs = coder.process_file(str(input_path), progress_callback=progress_handler)

        for fmt, path in outputs.items():
            logger.success(f"Saved {fmt} output: {path}")

        if coder.last_parse_failures > 0:
            logger.warning(
                f"Completed with {coder.last_parse_failures} parse failure(s). "
                "Check output quality or rerun with --fail-on-parse-error."
            )

        print_cost_report(coder.tracker, api_key=settings.llm.api_key)

    except Exception as error:
        logger.error(f"Qualitative coding failed: {error}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
