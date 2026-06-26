import typer
from loguru import logger
import sys
from pathlib import Path
from typing import Optional
from versline.config import settings, reload_settings
from versline.commands import transcribe, translate, qude, qualcode, slides, summarize


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

    configure_logging(verbose)

def configure_logging(verbose: bool):
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    # Use a lambda to ensure we write to the current sys.stderr (which might be patched by rich)
    logger.add(lambda msg: sys.stderr.write(msg), level=level, format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>\n", colorize=True)

if __name__ == "__main__":
    app()
