import typer
import re
from typing import Optional
from pathlib import Path
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from loguru import logger
from versline.services.translation import TextTranslator
from versline.config import settings
from versline.services.pricing import print_cost_report

app = typer.Typer(help="Translate files.")


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


def _resolve_output_paths(file_path: Path, output: Optional[Path]) -> tuple[Path, Path]:
    if output:
        base_path = output.with_suffix("") if output.suffix else output
    else:
        base_path = file_path.with_name(f"{file_path.stem}_translated")

    return base_path.with_suffix(".md"), base_path.with_suffix(".txt")

@app.callback(invoke_without_command=True)
def translate_file(
    ctx: typer.Context,
    file_path: Optional[Path] = typer.Argument(None, help="Path to the input file", exists=True),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Base output path (writes both .md and .txt)"),
    target_lang: str = typer.Option("Persian", "--lang", "-l", help="Target language (e.g. Persian, English, French)"),
    model: Optional[str] = typer.Option(None, help="LLM Model to use (overrides config)"),
    provider: Optional[str] = typer.Option(None, help="LLM Provider (Google, OpenAI, OpenRouter, AvalAI, OpenAICompatible)"),
    api_key: Optional[str] = typer.Option(None, help="API Key for the provider"),
    api_endpoint: Optional[str] = typer.Option(None, help="Custom API Endpoint"),
    proxy: Optional[str] = typer.Option(None, help="Proxy URL"),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-translation (ignore cache)"),
):
    """
    [bold blue]Translate a file[/bold blue] to a target language.
    
    Splits long texts into chunks and ensures fluent translation using LLMs.
    """
    if ctx.invoked_subcommand is not None:
        return

    if not file_path:
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

    logger.info(f"Starting translation for: {file_path}")
    
    translator = TextTranslator()
    
    try:
        final_text = ""
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
            
        md_output_path, txt_output_path = _resolve_output_paths(file_path, output)

        with open(md_output_path, "w", encoding="utf-8") as md_file:
            md_file.write(final_text)

        txt_content = _markdown_to_text(final_text)
        with open(txt_output_path, "w", encoding="utf-8") as txt_file:
            txt_file.write(txt_content)

        logger.success(f"Markdown translation saved to: {md_output_path}")
        logger.success(f"Text translation saved to: {txt_output_path}")

        print_cost_report(translator.tracker, api_key=settings.llm.api_key)

    except Exception as e:
        logger.error(f"Translation failed: {e}")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
