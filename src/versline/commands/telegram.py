from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from versline.commands._common import EXTRA_BODY_HELP, apply_extra_body_option
from versline.commands.setup import _read_env
from versline.config import settings, reload_settings
from versline.core.prompts import resolve_user_note
from versline.userconfig import user_config_dir, user_env_path
from versline.utils.common import format_duration

app = typer.Typer(help="Archive Telegram channel posts (captions + transcripts) as Obsidian notes.")
console = Console()

VALID_TYPES = {"audio", "voice", "video", "video_note", "photo", "document", "text"}


def _save_credentials(api_id: str, api_hash: str) -> None:
    path = user_env_path()
    values = _read_env(path)
    values["VERSLINE_TELEGRAM_API_ID"] = api_id
    values["VERSLINE_TELEGRAM_API_HASH"] = api_hash
    user_config_dir().mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _make_source(proxy: Optional[str] = None, web: bool = False):
    try:
        if web:
            from versline.services.channel_archive.sources.telegram_web import TelegramWebSource

            return TelegramWebSource(proxy=proxy)
        from versline.services.channel_archive.sources.telegram import TelegramSource

        return TelegramSource(proxy=proxy)
    except (RuntimeError, ValueError) as exc:
        logger.error(str(exc))
        raise typer.Exit(code=1)


@app.command("login")
def login(
    proxy: Optional[str] = typer.Option(None, help="Proxy URL (socks5://host:port or http://host:port)"),
):
    """Log in to Telegram once (phone number + code). api_id/api_hash come from https://my.telegram.org."""
    if not (settings.telegram.api_id and settings.telegram.api_hash):
        console.print("Create an app at [bold]https://my.telegram.org[/bold] → API development tools, then paste its values.")
        api_id = typer.prompt("api_id")
        api_hash = typer.prompt("api_hash", hide_input=True)
        if not api_id.strip().isdigit():
            console.print("[red]api_id must be a number.[/red]")
            raise typer.Exit(1)
        _save_credentials(api_id.strip(), api_hash.strip())
        reload_settings()
    source = _make_source(proxy)
    try:
        name = source.login()
    finally:
        source.close()
    console.print(f"[green]Logged in as {name}.[/green]")
    console.print("[yellow]The session file grants access to your Telegram account; keep it private.[/yellow]")


@app.command("logout")
def logout():
    """Log out and delete the saved Telegram session."""
    source = _make_source()
    try:
        source.logout()
    finally:
        source.close()
    console.print("Logged out.")


@app.command("archive")
def archive(
    channel: str = typer.Argument(..., help="Channel: @name, name, https://t.me/name, https://t.me/c/<id>, or a joined invite link"),
    since: Optional[str] = typer.Option(None, "--since", help="Only posts from this date (YYYY-MM-DD[ HH:MM], Gregorian or Shamsi e.g. 1404-07-01)"),
    until: Optional[str] = typer.Option(None, "--until", help="Only posts up to and including this date"),
    limit: Optional[int] = typer.Option(None, "--limit", help="Process at most N matching posts"),
    types: Optional[str] = typer.Option(None, "--types", help="Comma-separated media types: audio,voice,video,video_note,photo,document,text (default: all)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output folder (default: output/<channel>); point it at your Obsidian vault"),
    keep_media: bool = typer.Option(False, "--keep-media", help="Save media under attachments/ and embed it in the notes"),
    no_transcribe: bool = typer.Option(False, "--no-transcribe", help="Only save captions/metadata; skip transcription"),
    max_size: Optional[float] = typer.Option(None, "--max-size", help="Skip media larger than this many MB"),
    force: bool = typer.Option(False, "--force", "-f", help="Re-process posts already archived (and ignore the transcription cache)"),
    reuse_transcripts: bool = typer.Option(False, "--reuse-transcripts", help="Re-process already archived posts (captions, tags, --summary, --taqrir...) but keep the transcripts in their existing notes instead of transcribing again"),
    dry_run: bool = typer.Option(False, "--dry-run", help="List matching posts without downloading or writing anything"),
    add_summary: bool = typer.Option(False, "--summary", help="Add an LLM-written summary at the top of each note"),
    add_taqrir: bool = typer.Option(False, "--taqrir", help="Add a taqrir: the talk (or a long text post) rewritten as a structured, formulated exposition, after the transcript/caption"),
    output_lang: Optional[str] = typer.Option(None, "--output-lang", help="Language for --summary/--taqrir (default: same as the content)"),
    web: bool = typer.Option(False, "--web", help="Read the public web preview (t.me/s/<channel>) instead of a logged-in account: no login needed, public channels only; audio files and large videos can't be downloaded"),
    # LLM / transcription overrides (same as `versline transcribe`)
    model: Optional[str] = typer.Option(None, help="LLM Model to use (overrides config)"),
    provider: Optional[str] = typer.Option(None, help="LLM Provider (Google, OpenAI, OpenRouter, AvalAI, OpenAICompatible)"),
    api_key: Optional[str] = typer.Option(None, help="API Key for the provider"),
    api_endpoint: Optional[str] = typer.Option(None, help="Custom API Endpoint"),
    proxy: Optional[str] = typer.Option(None, help="Proxy URL for the LLM provider"),
    telegram_proxy: Optional[str] = typer.Option(None, "--telegram-proxy", help="Proxy URL for Telegram (defaults to VERSLINE_TELEGRAM_PROXY, then --proxy)"),
    extra_body: Optional[str] = typer.Option(None, "--extra-body", help=EXTRA_BODY_HELP),
    note: Optional[str] = typer.Option(None, "--note", help="Additional instruction to append to the transcription prompt"),
    note_file: Optional[Path] = typer.Option(None, "--note-file", help="Path to a .md or .txt file with an additional instruction"),
    chunk_size: int = typer.Option(900, help="Chunk size in seconds"),
    overlap: int = typer.Option(180, help="Overlap size in seconds"),
    skip_blocked: bool = typer.Option(False, "--skip-blocked", help="Skip chunks blocked by the provider instead of failing the post"),
):
    """Download a channel's posts in a date range and save each as an Obsidian note with frontmatter and transcript."""
    from versline.services.channel_archive.obsidian import parse_date_arg
    from versline.services.channel_archive.pipeline import ArchiveOptions, ChannelArchiver
    from versline.services.channel_archive.steps import StepContext

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
        since_dt = parse_date_arg(since) if since else None
        until_dt = parse_date_arg(until, end=True) if until else None
    except ValueError as exc:
        raise typer.BadParameter(str(exc))
    if since_dt and until_dt and since_dt > until_dt:
        raise typer.BadParameter("--since is after --until")

    type_set = None
    if types:
        type_set = {t.strip() for t in types.split(",") if t.strip()}
        bad = type_set - VALID_TYPES
        if bad:
            raise typer.BadParameter(f"Unknown type(s): {', '.join(sorted(bad))}. Choose from: {', '.join(sorted(VALID_TYPES))}")

    source = _make_source(telegram_proxy, web=web)
    try:
        transcriber = None
        if not no_transcribe and not dry_run:
            from versline.services.transcription import AudioTranscriber

            user_note = resolve_user_note(note=note, note_file=str(note_file) if note_file else None)
            transcriber = AudioTranscriber(user_note=user_note)

        tracker = transcriber.tracker if transcriber is not None else None
        text_llm = None
        steps = ["media", "transcribe"]
        if add_summary or add_taqrir:
            from versline.services.channel_archive.llm import TextLLM
            from versline.services.pricing import TokenTracker

            tracker = tracker or TokenTracker()
            text_llm = TextLLM(tracker)
            steps += (["summary"] if add_summary else []) + (["taqrir"] if add_taqrir else [])

        ctx = StepContext(
            source=source,
            channel=None,  # set by the archiver once resolved
            out_dir=output,
            temp_dir=Path(settings.temp_directory) / "telegram",
            keep_media=keep_media,
            transcribe=not no_transcribe,
            max_size_mb=max_size,
            force=force,
            chunk_size=chunk_size,
            overlap=overlap,
            skip_blocked=skip_blocked,
            transcriber=transcriber,
            text_llm=text_llm,
            output_lang=output_lang or "",
        )
        options = ArchiveOptions(
            out_dir=output,
            temp_dir=ctx.temp_dir,
            since=since_dt,
            until=until_dt,
            limit=limit,
            types=type_set,
            dry_run=dry_run,
            force=force,
            reuse_transcripts=reuse_transcripts,
            steps=steps,
        )
        archiver = ChannelArchiver(source, ctx, options)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            redirect_stdout=True,
            redirect_stderr=True,
        ) as progress:
            task = progress.add_task("[green]Reading channel...", total=None)
            ctx.progress = lambda message: progress.update(task, description=f"[green]{message}")
            summary = archiver.run(channel, progress=lambda n, msg: progress.update(task, completed=n))
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted. Finished posts are saved; run the same command again to resume.[/yellow]")
        raise typer.Exit(code=130)
    except Exception as exc:
        logger.error(f"Archive failed: {exc}")
        raise typer.Exit(code=1)
    finally:
        source.close()

    if dry_run:
        table = Table(title=f"{summary.channel.title}: {len(summary.plans)} matching posts")
        for column in ("ID", "Date", "Type", "Duration", "Title"):
            table.add_column(column)
        for plan in summary.plans:
            table.add_row(
                str(plan.id),
                plan.date.astimezone().strftime("%Y-%m-%d %H:%M"),
                plan.media_type,
                format_duration(plan.duration) if plan.duration else "",
                plan.title,
            )
        console.print(table)
        return

    console.print(f"[bold]Done:[/bold] {summary.done}  skipped: {summary.skipped}  failed: {summary.failed}  → {archiver.out_dir}")
    for error in summary.errors:
        console.print(f"[red]  {error}[/red]")
    if tracker is not None and summary.done:
        from versline.services.pricing import print_cost_report

        print_cost_report(tracker, api_key=settings.llm.api_key)
    if summary.failed:
        raise typer.Exit(code=1)
