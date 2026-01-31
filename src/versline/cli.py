import typer
from loguru import logger
import sys
from versline.config import settings
from versline.commands import transcribe, translate

app = typer.Typer(
    name="versline",
    help="[bold green]Versline Toolkit[/bold green] for [yellow]media processing, transcription, and translation[/yellow].",
    add_completion=True,
    rich_markup_mode="rich",
)

# Register subcommands
app.add_typer(transcribe.app, name="transcribe", help="[cyan]Convert audio/video to text[/cyan] using advanced LLMs.")
app.add_typer(translate.app, name="translate", help="[cyan]Translate text files[/cyan] to other languages.")

@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
):
    """
    [bold]Versline[/bold] is a powerful toolkit for automated media processing.
    
    [underline]Features:[/underline]
    
    * :microphone: [bold green]Transcribe[/bold green]: Accurate audio-to-text with speaker identification context.
    * :globe_with_meridians: [bold blue]Download[/bold blue]: Integrated file downloader (supports auto-download in transcribe).
    * :gear: [bold yellow]Flexible ConfiTranslate[/bold blue]: Context-aware translation for documents
    
    [dim]Run 'versline COMMAND --help' for more info on specific commands.[/dim]
    """
    configure_logging(verbose)
    # logger.debug(f"Loaded settings: {settings.model_dump()}")

def configure_logging(verbose: bool):
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(sys.stderr, level=level)

if __name__ == "__main__":
    app()
