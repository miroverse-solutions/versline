import json
import typer
from versline.commands._common import EXTRA_BODY_HELP, apply_extra_body_option
from typing import Optional
from pathlib import Path
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from loguru import logger
import os

from versline.services.transcription import AudioTranscriber
from versline.config import settings
from versline.services.network import download_file
from versline.services.pricing import print_cost_report
from versline.core.prompts import load_prompt, resolve_user_note

app = typer.Typer(help="Transcribe audio/video files.")

@app.callback(invoke_without_command=True)
def transcribe_file(
    ctx: typer.Context,
    file_path: Optional[str] = typer.Argument(None, help="Path or URL to the audio/video file"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path"),
    chunk_size: int = typer.Option(900, help="Chunk size in seconds"),
    overlap: int = typer.Option(180, help="Overlap size in seconds"),
    model: Optional[str] = typer.Option(None, help="LLM Model to use (overrides config)"),
    provider: Optional[str] = typer.Option(None, help="LLM Provider (Google, OpenAI, OpenRouter, AvalAI, OpenAICompatible)"),
    api_key: Optional[str] = typer.Option(None, help="API Key for the provider"),
    api_endpoint: Optional[str] = typer.Option(None, help="Custom API Endpoint"),
    proxy: Optional[str] = typer.Option(None, help="Proxy URL"),
    extra_body: Optional[str] = typer.Option(None, "--extra-body", help=EXTRA_BODY_HELP),
    # Advanced options
    prompt_file: Optional[Path] = typer.Option(None, help="Custom system prompt file"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output in JSON format (using predefined schema)"),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-transcription (ignore cache)"),
    note: Optional[str] = typer.Option(None, "--note", help="Additional instruction to append to the prompt"),
    note_file: Optional[Path] = typer.Option(None, "--note-file", help="Path to a .md or .txt file with an additional instruction"),
    # Timestamp options
    timestamped: bool = typer.Option(False, "--timestamped", help="Produce timestamp-aligned segments along with the full text"),
    timestamp_model: Optional[str] = typer.Option(None, "--timestamp-model", help="Model to use for timestamp annotation (e.g. gpt-4o-transcribe)"),
    chunk_minutes: Optional[int] = typer.Option(None, "--chunk-minutes", help="Minutes per chunk for the primary transcription phase"),
    native_timestamps_only: bool = typer.Option(False, "--native-timestamps-only", help="Only use native STT API for timestamps; fail instead of falling back to chunk-based"),
    reuse_transcript: bool = typer.Option(False, "--reuse-transcript", help="Skip the main transcription and reuse the cached transcript (work_dir/<name>/progress.json); only redo timestamping. --force then only resets timestamp caches"),
    # STT options (default to the LLM settings when omitted)
    timestamp_provider: Optional[str] = typer.Option(None, "--timestamp-provider", help="STT provider (OpenAI, AvalAI, OpenRouter, OpenAICompatible). Defaults to LLM settings"),
    timestamp_api_key: Optional[str] = typer.Option(None, "--timestamp-api-key", help="API key for the STT endpoint. Defaults to the LLM API key"),
    timestamp_api_endpoint: Optional[str] = typer.Option(None, "--timestamp-api-endpoint", help="STT base URL (without /audio/transcriptions). Defaults to provider/LLM endpoint"),
    timestamp_proxy: Optional[str] = typer.Option(None, "--timestamp-proxy", help="Proxy URL for STT requests. Defaults to the LLM proxy"),
    timestamp_language: Optional[str] = typer.Option(None, "--timestamp-language", help="Language code for STT (e.g. fa, en). Default: fa"),
    timestamp_timeout: Optional[int] = typer.Option(None, "--timestamp-timeout", help="HTTP timeout in seconds for timestamp (STT) requests"),
):
    """
    Transcribe a single file (or URL).
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
    if extra_body:
        apply_extra_body_option(extra_body)
    if timestamp_provider:
        settings.transcription.timestamp_provider = timestamp_provider
    if timestamp_api_key:
        settings.transcription.timestamp_api_key = timestamp_api_key
    if timestamp_api_endpoint:
        settings.transcription.timestamp_api_endpoint = timestamp_api_endpoint
    if timestamp_proxy:
        settings.transcription.timestamp_proxy = timestamp_proxy
    if timestamp_language:
        settings.transcription.timestamp_language = timestamp_language
    if timestamp_timeout:
        settings.transcription.timestamp_timeout_seconds = timestamp_timeout
        
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
    
    user_note = resolve_user_note(note=note, note_file=str(note_file) if note_file else None)
    transcriber = AudioTranscriber(user_note=user_note)
    if prompt_file:
        if prompt_file.exists():
            transcriber.transcription_prompt = prompt_file.read_text(encoding="utf-8")
            logger.info("Loaded custom prompt from file.")
        else:
            logger.warning(f"Prompt file not found: {prompt_file}. Using default.")
    elif json_output:
        try:
            transcriber.transcription_prompt = load_prompt("transcription_json_prompt.md")
            logger.info("Loaded JSON transcription prompt.")
        except Exception as e:
            logger.error(f"Failed to load JSON prompt: {e}")
            raise typer.Exit(code=1)

    try:
        # Progress bar context
        full_text = ""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            redirect_stdout=True,
            redirect_stderr=True,
        ) as progress:
            main_task = progress.add_task("[green]Transcribing...", total=100)
            
            def progress_handler(current, total, message):
                progress.update(main_task, completed=current, total=total, description=message)
            
            full_text = transcriber.process_file(
                str(resolved_path),
                chunk_length=chunk_size,
                overlap=overlap,
                progress_callback=progress_handler,
                force=force,
                timestamped=timestamped,
                timestamp_model=timestamp_model,
                chunk_minutes=chunk_minutes,
                native_timestamps_only=native_timestamps_only,
                reuse_transcript=reuse_transcript,
            )
        
        if output:
            output_path = output
        else:
            # If URL, resolved_path is temp file, make output in current dir based on original/temp filename
            ext = ".json" if (json_output or (timestamped and isinstance(full_text, dict))) else ".md"
            out_name = Path(resolved_path).with_suffix(ext).name
            output_path = Path("output") / out_name
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
        content = json.dumps(full_text, ensure_ascii=False, indent=2) if isinstance(full_text, dict) else full_text
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        logger.success(f"Transcription saved to: {output_path}")

        if isinstance(full_text, dict) and full_text.get("text"):
            text_path = Path(output_path).with_suffix(".md")
            if text_path == Path(output_path):
                text_path = Path(output_path).with_name(f"{Path(output_path).stem}_full.md")
            text_path.write_text(full_text["text"], encoding="utf-8")
            logger.success(f"Full transcription text saved to: {text_path}")

        print_cost_report(transcriber.tracker, api_key=settings.llm.api_key)
        
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
