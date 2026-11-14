import typer
from versline.commands._export import export_frontmatter_option, export_option, run_exports
from versline.commands._common import EXTRA_BODY_HELP, INTERSPERSED, apply_extra_body_option
import re
from typing import List, Optional
from pathlib import Path
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from loguru import logger
from versline.services.translation import TextTranslator
from versline.config import settings
from versline.services.pricing import print_cost_report
from versline.core.prompts import resolve_user_note
from versline.commands._batch import (
    DONE, SKIPPED, TEXT_EXTENSIONS, expand_inputs, output_is_complete, resolve_batch_output, run_batch,
)

app = typer.Typer(help="Translate files.", context_settings=INTERSPERSED)


def _markdown_to_text(markdown: str) -> str:
    text = markdown.replace("\r\n", "\n")
    text = re.sub(r"```[^\n]*\n(.*?)```", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+[.)]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.*?)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_(?!_)(.*?)_(?!_)", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _resolve_output_paths(file_path: Path, output: Optional[Path], output_dir: bool = False) -> tuple[Path, Path]:
    if output and output_dir:
        base_path = output / f"{file_path.stem}_translated"
    elif output:
        base_path = output.with_suffix("") if output.suffix else output
    else:
        base_path = file_path.with_name(f"{file_path.stem}_translated")

    return base_path.with_suffix(".md"), base_path.with_suffix(".txt")

@app.callback(invoke_without_command=True)
def translate_file(
    ctx: typer.Context,
    file_paths: Optional[List[Path]] = typer.Argument(None, help="Input file(s), folder(s) or glob(s). Options may follow them."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Base output path (writes both .md and .txt); a directory when several inputs are given"),
    target_lang: str = typer.Option("Persian", "--lang", "-l", help="Target language (e.g. Persian, English, French)"),
    model: Optional[str] = typer.Option(None, help="LLM Model to use (overrides config)"),
    provider: Optional[str] = typer.Option(None, help="LLM Provider (Google, OpenAI, OpenRouter, AvalAI, OpenAICompatible)"),
    api_key: Optional[str] = typer.Option(None, help="API Key for the provider"),
    api_endpoint: Optional[str] = typer.Option(None, help="Custom API Endpoint"),
    proxy: Optional[str] = typer.Option(None, help="Proxy URL"),
    extra_body: Optional[str] = typer.Option(None, "--extra-body", help=EXTRA_BODY_HELP),
    export: Optional[str] = export_option(),
    export_frontmatter: Optional[bool] = export_frontmatter_option(),
    force: bool = typer.Option(False, "--force", "-f", help="Re-translate even if the output already exists (ignore saved progress)"),
    recursive: bool = typer.Option(False, "--recursive", help="Also search sub-folders of folder inputs"),
    note: Optional[str] = typer.Option(None, "--note", help="Additional instruction to append to the prompt"),
    note_file: Optional[Path] = typer.Option(None, "--note-file", help="Path to a .md or .txt file with an additional instruction"),
):
    """
    [bold blue]Translate a file[/bold blue] to a target language.
    
    Splits long texts into chunks and ensures fluent translation using LLMs.
    """
    if ctx.invoked_subcommand is not None:
        return

    if not file_paths:
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

    inputs = expand_inputs(file_paths, TEXT_EXTENSIONS, recursive=recursive)
    if not inputs:
        logger.error("No input files found.")
        raise typer.Exit(code=1)
    output = resolve_batch_output(output, len(inputs))
    output_is_dir = len(inputs) > 1

    user_note = resolve_user_note(note=note, note_file=str(note_file) if note_file else None)
    translator = TextTranslator(user_note=user_note)

    produced: List[Path] = []

    def process_one(file_path: Path):
        md_output_path, txt_output_path = _resolve_output_paths(file_path, output, output_is_dir)
        if not force and output_is_complete(md_output_path, txt_output_path):
            logger.info(f"Skipping {file_path}: {md_output_path} already exists (use --force to redo)")
            produced.append(md_output_path)
            return SKIPPED

        logger.info(f"Starting translation for: {file_path}")
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                redirect_stdout=True,
                redirect_stderr=True,
            ) as progress:
                task_id = progress.add_task("[blue]Translating...", total=100)

                def progress_handler(current, total, message):
                    progress.update(task_id, completed=current, total=total, description=message)

                final_text = translator.process_file(
                    str(file_path),
                    target_language=target_lang,
                    progress_callback=progress_handler,
                    force=force
                )

            md_output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(md_output_path, "w", encoding="utf-8") as md_file:
                md_file.write(final_text)

            txt_content = _markdown_to_text(final_text)
            with open(txt_output_path, "w", encoding="utf-8") as txt_file:
                txt_file.write(txt_content)

            logger.success(f"Markdown translation saved to: {md_output_path}")
            produced.append(md_output_path)
            logger.success(f"Text translation saved to: {txt_output_path}")
        except Exception as e:
            logger.error(f"Translation failed for {file_path}: {e}")
            raise typer.Exit(code=1)
        return DONE

    try:
        run_batch(inputs, process_one)
    finally:
        print_cost_report(translator.tracker, api_key=settings.llm.api_key)

    run_exports(produced, export, export_frontmatter, {
        "type": "translation", "target_language": target_lang, "model": settings.llm.model,
    }, force=force)

if __name__ == "__main__":
    app()
