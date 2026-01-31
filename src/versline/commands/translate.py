import typer
from pathlib import Path
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from loguru import logger
from versline.services.translation import TextTranslator
from versline.config import settings

app = typer.Typer(help="Translate text files.")

@app.command("file")
def translate_file(
    file_path: Path = typer.Argument(..., help="Path to the text file", exists=True),
    output: Path = typer.Option(None, "--output", "-o", help="Output file path"),
    target_lang: str = typer.Option("Persian", "--lang", "-l", help="Target language (e.g. Persian, English, French)"),
    model: str = typer.Option(None, help="LLM Model to use (overrides config)"),
    provider: str = typer.Option(None, help="LLM Provider (Google, OpenAI, OpenRouter)"),
    api_key: str = typer.Option(None, help="API Key for the provider"),
):
    """
    [bold blue]Translate a text file[/bold blue] to a target language.
    
    Splits long texts into chunks and ensures fluent translation using LLMs.
    """
    if model:
        settings.llm.model = model
    if provider:
        settings.llm.provider = provider
    if api_key:
        settings.llm.api_key = api_key

    logger.info(f"Starting translation for: {file_path}")
    
    translator = TextTranslator()
    
    try:
        final_text = ""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        ) as progress:
            task_id = progress.add_task("[blue]Translating...", total=100)
            
            def progress_handler(current, total, message):
                progress.update(task_id, completed=current, total=total, description=message)
                
            final_text = translator.process_file(
                str(file_path),
                target_language=target_lang,
                progress_callback=progress_handler
            )
            
        if output:
            output_path = output
        else:
            output_path = file_path.with_stem(file_path.stem + "_translated")
            
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_text)
            
        logger.success(f"Translation saved to: {output_path}")

    except Exception as e:
        logger.error(f"Translation failed: {e}")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
