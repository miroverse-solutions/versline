import typer
from pathlib import Path
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from loguru import logger
import os

from versline.services.transcription import AudioTranscriber
from versline.config import settings
from versline.services.network import download_file

app = typer.Typer(help="Transcribe audio/video files.")

@app.command("file")
def transcribe_file(
    file_path: str = typer.Argument(..., help="Path or URL to the audio/video file"),
    output: Path = typer.Option(None, "--output", "-o", help="Output file path"),
    chunk_size: int = typer.Option(900, help="Chunk size in seconds"),
    overlap: int = typer.Option(180, help="Overlap size in seconds"),
    model: str = typer.Option(None, help="LLM Model to use (overrides config)"),
    provider: str = typer.Option(None, help="LLM Provider (Google, OpenAI, OpenRouter)"),
    api_key: str = typer.Option(None, help="API Key for the provider"),
    # Advanced options
    prompt_file: Path = typer.Option(None, help="Custom system prompt file"),
):
    """
    Transcribe a single file (or URL).
    """
    if model:
        settings.llm.model = model
    if provider:
        settings.llm.provider = provider
    if api_key:
        settings.llm.api_key = api_key
        
    resolved_path = file_path
    temp_download = None
    
    # Check if URL
    if file_path.startswith("http://") or file_path.startswith("https://"):
        logger.info(f"Detected URL. Downloading content from {file_path}...")
        download_dir = settings.temp_directory / "downloads"
        try:
             # Use a spinner for download
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True
            ) as progress:
                task = progress.add_task(description="Downloading file...", total=None)
                resolved_path = download_file(file_path, download_dir)
                temp_download = resolved_path # Mark for cleanup later if needed
                progress.update(task, description="Download complete!")
                
        except Exception as e:
            logger.error(f"Failed to download file: {e}")
            raise typer.Exit(code=1)
    else:
        path_obj = Path(file_path)
        if not path_obj.exists():
             logger.error(f"File not found: {file_path}")
             raise typer.Exit(code=1)
        resolved_path = path_obj

    logger.info(f"Starting transcription for: {resolved_path}")
    
    transcriber = AudioTranscriber()
    if prompt_file:
        if prompt_file.exists():
            transcriber.transcription_prompt = prompt_file.read_text(encoding="utf-8")
            logger.info("Loaded custom prompt.")
        else:
            logger.warning(f"Prompt file not found: {prompt_file}. Using default.")

    try:
        # Progress bar context
        full_text = ""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        ) as progress:
            main_task = progress.add_task("[green]Transcribing...", total=100)
            
            def progress_handler(current, total, message):
                progress.update(main_task, completed=current, total=total, description=message)
            
            full_text = transcriber.process_file(
                str(resolved_path),
                chunk_length=chunk_size,
                overlap=overlap,
                progress_callback=progress_handler
            )
        
        if output:
            output_path = output
        else:
            # If URL, resolved_path is temp file, make output in current dir based on temp filename
            out_name = Path(resolved_path).with_suffix(".md").name
            output_path = Path("output") / out_name
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_text)
            
        logger.success(f"Transcription saved to: {output_path}")
        
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
