import os
from datetime import timedelta
from pathlib import Path
from typing import List, Optional

import typer
from loguru import logger
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from versline.commands._common import EXTRA_BODY_HELP, INTERSPERSED, apply_extra_body_option
from versline.commands._export import export_frontmatter_option, export_option, run_exports
from versline.config import settings, reload_settings
from versline.core.prompts import resolve_text_input, resolve_user_note
from versline.utils.common import format_duration

app = typer.Typer(help="Archive Telegram channel posts (captions + transcripts) as Obsidian notes, or write a taqrir of a chat's discussions.")
console = Console()

VALID_TYPES = {"audio", "voice", "video", "video_note", "photo", "document", "text"}


def _save_credentials(api_id: str, api_hash: str) -> None:
    from versline.userenv import update_env

    update_env({"VERSLINE_TELEGRAM_API_ID": api_id, "VERSLINE_TELEGRAM_API_HASH": api_hash})


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


def _apply_llm_overrides(model, provider, api_key, api_endpoint, proxy, extra_body) -> None:
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


def _date_range(since: Optional[str], until: Optional[str]):
    from versline.services.channel_archive.obsidian import parse_date_arg

    try:
        since_dt = parse_date_arg(since) if since else None
        until_dt = parse_date_arg(until, end=True) if until else None
    except ValueError as exc:
        raise typer.BadParameter(str(exc))
    if since_dt and until_dt and since_dt > until_dt:
        raise typer.BadParameter("--since is after --until")
    return since_dt, until_dt


def _type_set(types: Optional[str]):
    if not types:
        return None
    type_set = {t.strip() for t in types.split(",") if t.strip()}
    bad = type_set - VALID_TYPES
    if bad:
        raise typer.BadParameter(f"Unknown type(s): {', '.join(sorted(bad))}. Choose from: {', '.join(sorted(VALID_TYPES))}")
    return type_set


def _require_llm() -> None:
    from versline.services.ai import MissingAPIKeyError, require_api_key

    try:
        require_api_key(settings.llm)
    except MissingAPIKeyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)


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
        # config.env is only read at import; an empty value from another env file would also shadow it
        os.environ["VERSLINE_TELEGRAM_API_ID"] = api_id.strip()
        os.environ["VERSLINE_TELEGRAM_API_HASH"] = api_hash.strip()
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
    channel: str = typer.Argument(..., help="Channel or chat: @name, name, https://t.me/name, https://t.me/c/<id>, a joined invite link, or a numeric id (e.g. -1001234567890 or 1234567890; see `telegram chats`)"),
    since: Optional[str] = typer.Option(None, "--since", help="Only posts from this date (YYYY-MM-DD[ HH:MM], Gregorian or Shamsi e.g. 1404-07-01)"),
    until: Optional[str] = typer.Option(None, "--until", help="Only posts up to and including this date"),
    limit: Optional[int] = typer.Option(None, "--limit", help="Process at most N matching posts"),
    types: Optional[str] = typer.Option(None, "--types", help="Comma-separated media types: audio,voice,video,video_note,photo,document,text (default: all)"),
    ext: Optional[str] = typer.Option(None, "--ext", help="Only files with these extensions, comma-separated (e.g. pdf,docx; 'word' = doc,docx). Taken from the file name, else the mime type"),
    match: Optional[List[str]] = typer.Option(None, "--match", help="Regex; keep files matching at least one (repeatable). Case-insensitive, Persian-normalized (ي/ك, ZWNJ and _ count as plain letters/spaces)"),
    exclude: Optional[List[str]] = typer.Option(None, "--exclude", help="Regex; drop files matching any (repeatable). Wins over --match"),
    match_in: str = typer.Option("name", "--match-in", help="What --match/--exclude test: name (file name), caption (post text) or any (either)"),
    files_only: bool = typer.Option(False, "--files-only", help="Just save the matching files under their original names: no notes, no transcription, no LLM"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output folder (default: output/<channel>); point it at your Obsidian vault"),
    keep_media: bool = typer.Option(False, "--keep-media", help="Save media under attachments/ and embed it in the notes"),
    no_transcribe: bool = typer.Option(False, "--no-transcribe", help="Only save captions/metadata; skip transcription"),
    max_size: Optional[float] = typer.Option(None, "--max-size", help="Skip media larger than this many MB"),
    force: bool = typer.Option(False, "--force", "-f", help="Re-process posts already archived (and ignore the transcription cache)"),
    reuse_transcripts: bool = typer.Option(False, "--reuse-transcripts", help="Re-process already archived posts (captions, tags, --summary, --taqrir...) but keep the transcripts in their existing notes instead of transcribing again"),
    merge_parts: bool = typer.Option(False, "--merge-parts", help="Merge posts split across several messages (⬇️ … ⬆️, «ادامه دارد») into one note; already archived parts are merged too"),
    merge_gap: float = typer.Option(15, "--merge-gap", help="With --merge-parts: max minutes between the parts of one item"),
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
    export: Optional[str] = typer.Option(None, "--export", "-X", help="Also export each post to Word/PDF under <output>/exports/: docx, pdf, 'docx,pdf' or all (needs versline[export])"),
    export_frontmatter: Optional[bool] = typer.Option(None, "--export-frontmatter/--no-export-frontmatter", help="Show each post's metadata as a table under its title in exported files (default: on)"),
    make_pack: bool = typer.Option(False, "--pack", help="After archiving, build the complete pack (book, per-post files, catalog, notes, README, ZIP); same as running `telegram pack` on the output"),
):
    """Download a channel's posts in a date range and save each as an Obsidian note with frontmatter and transcript."""
    from versline.services.channel_archive.pipeline import ArchiveOptions, ChannelArchiver
    from versline.services.channel_archive.steps import StepContext

    _apply_llm_overrides(model, provider, api_key, api_endpoint, proxy, extra_body)
    since_dt, until_dt = _date_range(since, until)
    type_set = _type_set(types)

    from versline.services.channel_archive.filters import FileFilter

    try:
        file_filter = FileFilter.build(ext, match or [], exclude or [], match_in)
    except ValueError as exc:
        raise typer.BadParameter(str(exc))
    if files_only and (add_summary or add_taqrir or reuse_transcripts):
        raise typer.BadParameter("--files-only can't be combined with --summary, --taqrir or --reuse-transcripts")
    if merge_parts and files_only:
        console.print("[yellow]--merge-parts is ignored with --files-only.[/yellow]")
    if (web and (files_only or file_filter)) and not dry_run:
        console.print("[yellow]--web can't download documents (only voice and small videos); matching files will be reported as skipped.[/yellow]")

    needs_llm = not dry_run and not files_only and (not no_transcribe or add_summary or add_taqrir)
    if needs_llm:
        _require_llm()

    source = _make_source(telegram_proxy, web=web)
    try:
        transcriber = None
        if not no_transcribe and not dry_run and not files_only:
            from versline.services.transcription import AudioTranscriber

            user_note = resolve_user_note(note=note, note_file=str(note_file) if note_file else None)
            transcriber = AudioTranscriber(user_note=user_note)

        tracker = transcriber.tracker if transcriber is not None else None
        text_llm = None
        steps = ["media", "transcribe"]
        if (add_summary or add_taqrir) and not files_only:
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
            file_filter=file_filter,
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
            file_filter=file_filter,
            files_only=files_only,
            merge_parts=merge_parts,
            merge_gap=timedelta(minutes=merge_gap),
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
        show_files = files_only or file_filter is not None
        for column in ("ID", "Date", "Type", "Duration", "Title") + (("Files",) if show_files else ()):
            table.add_column(column)
        for plan in summary.plans:
            row = [
                "+".join(str(i) for i in plan.parts) if plan.parts else str(plan.id),
                plan.date.astimezone().strftime("%Y-%m-%d %H:%M"),
                plan.media_type,
                format_duration(plan.duration) if plan.duration else "",
                plan.title,
            ]
            if show_files:
                row.append("\n".join(plan.files))
            table.add_row(*row)
        console.print(table)
        return

    if files_only:
        console.print(
            f"[bold]Saved:[/bold] {summary.files_saved} files from {summary.done} posts  duplicates: {summary.duplicates}  "
            f"skipped posts: {summary.skipped}  failed: {summary.failed}  → {archiver.out_dir}"
        )
    else:
        console.print(f"[bold]Done:[/bold] {summary.done}  skipped: {summary.skipped}  failed: {summary.failed}  → {archiver.out_dir}")
    for error in summary.errors:
        console.print(f"[red]  {error}[/red]")
    if tracker is not None and summary.done:
        from versline.services.pricing import print_cost_report

        print_cost_report(tracker, api_key=settings.llm.api_key)
    if (export or make_pack) and not dry_run and not files_only:
        _post_archive(archiver.out_dir, export, export_frontmatter, make_pack)
    if summary.failed:
        raise typer.Exit(code=1)


def _post_archive(out_dir: Path, export: Optional[str], front_matter: Optional[bool], make_pack: bool) -> None:
    from versline.services import docexport
    from versline.services.channel_archive import pack as pack_service

    try:
        if make_pack:
            opts = _pack_options(export, front_matter, None, None, True, True, True, False, None, True)
            _run_pack(out_dir, opts)
        else:
            exp = docexport.ExportOptions.from_settings(formats=export, front_matter=front_matter)
            opts = pack_service.PackOptions(formats=exp.formats, front_matter=exp.front_matter)
            _, posts = pack_service.collect_posts(out_dir)
            results = pack_service.export_posts(out_dir, posts, out_dir / "exports", opts)
            done = sum(1 for r in results if r.ok and not r.skipped)
            console.print(f"[bold]Exported:[/bold] {done} files → {out_dir / 'exports'}")
            for r in results:
                if not r.ok:
                    console.print(f"[red]  {r.output.name}: {r.error}[/red]")
    except (docexport.ExportError, ValueError, FileNotFoundError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)


def _pack_options(to, front_matter, since, until, per_post, media, make_zip, force, out_dir, toc=True):
    from versline.services import docexport
    from versline.services.channel_archive import pack as pack_service
    from versline.services.channel_archive.obsidian import parse_date_arg

    exp = docexport.ExportOptions.from_settings(formats=to if to is not None else "docx,pdf", front_matter=front_matter)
    return pack_service.PackOptions(
        formats=exp.formats, front_matter=exp.front_matter, per_post=per_post, media=media, make_zip=make_zip,
        since=parse_date_arg(since) if since else None, until=parse_date_arg(until, end=True) if until else None,
        force=force, out_dir=out_dir, toc=toc, page_format=exp.page_format, margin=exp.margin, font_size=exp.font_size,
    )


def _run_pack(archive_dir: Path, opts) -> None:
    from versline.services.channel_archive import pack as pack_service

    result = pack_service.build_pack(archive_dir, opts, log=lambda m: console.print(f"[dim]{m}[/dim]"))
    console.print(f"[bold]Pack:[/bold] {result.posts} posts → {result.root}")
    if result.zip_path:
        console.print(f"[bold]ZIP:[/bold] {result.zip_path}")
    for failure in result.failures:
        console.print(f"[red]  {failure}[/red]")
    if result.failures:
        raise typer.Exit(1)


@app.command("pack")
def pack(
    archive_dir: Path = typer.Argument(..., exists=True, file_okay=False, help="An archive folder made by `telegram archive` (contains .versline-channel.json)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Folder to create the pack in (default: output/<channel>_pack)"),
    to: str = typer.Option("docx,pdf", "--to", "-t", help="Formats for the book and per-post files: docx, pdf, 'docx,pdf' or all"),
    front_matter: Optional[bool] = typer.Option(None, "--front-matter/--no-front-matter", help="Show post metadata as a table under each title (default: on)"),
    per_post: bool = typer.Option(True, "--per-post/--no-per-post", help="Also write one Word/PDF file per post"),
    media: bool = typer.Option(True, "--media/--no-media", help="Include saved attachments (audio, images...) in the notes folder"),
    make_zip: bool = typer.Option(True, "--zip/--no-zip", help="Pack everything into one ZIP file"),
    toc: bool = typer.Option(True, "--toc/--no-toc", help="Table of contents (clickable links, grouped by Shamsi month) in the Word/PDF book"),
    since: Optional[str] = typer.Option(None, "--since", help="Only posts from this date (Gregorian or Shamsi)"),
    until: Optional[str] = typer.Option(None, "--until", help="Only posts up to and including this date"),
    force: bool = typer.Option(False, "--force", "-f", help="Re-export per-post files that are already up to date"),
):
    """Build a tidy, complete pack from a finished archive: one book (Word/PDF), per-post files, catalog, notes and README, as a folder and a ZIP."""
    from versline.services import docexport

    try:
        opts = _pack_options(to, front_matter, since, until, per_post, media, make_zip, force, output, toc)
        _run_pack(archive_dir, opts)
    except (docexport.ExportError, ValueError, FileNotFoundError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)


LIST_COLUMNS = ["id", "name", "username", "phone", "type"]
CHAT_KINDS = {"user", "bot", "group", "supergroup", "channel"}


def _show_people(rows: List[dict], title: str, output: Optional[Path], columns: Optional[List[str]] = None) -> None:
    """Print a people/chat list as a table, or write it to a .csv/.md/.json file."""
    from versline.services.telegram_people import write_rows

    if output:
        try:
            write_rows(rows, output, columns or LIST_COLUMNS)
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--output")
        console.print(f"[bold]{len(rows)}[/bold] {title} → {output}", soft_wrap=True)
        return
    table = Table(title=f"{len(rows)} {title}")
    dated = any(r.get("last_message") for r in rows)
    for column in ("ID", "Type", "Name", "Username", "Phone") + (("Last message",) if dated else ()):
        table.add_column(column)
    for row in rows:
        table.add_row(str(row["id"]), row.get("type") or "", row.get("name") or "", f"@{row['username']}" if row.get("username") else "",
                      row.get("phone") or "", *([row.get("last_message") or ""] if dated else []))
    console.print(table)


def _kind_set(value: Optional[str]):
    if not value:
        return None
    kinds = {k.strip().lower() for k in value.split(",") if k.strip()}
    bad = kinds - CHAT_KINDS
    if bad:
        raise typer.BadParameter(f"Unknown type(s): {', '.join(sorted(bad))}. Choose from: {', '.join(sorted(CHAT_KINDS))}", param_hint="--type")
    return kinds


DEFAULT_CHAT_LIMIT = 50


def effective_chat_limit(limit, since, until, output) -> Optional[int]:
    """An explicit limit always wins; otherwise a date range or a saved file means 'all matching chats'."""
    if limit is not None:
        return limit or None
    return None if (since or until or output) else DEFAULT_CHAT_LIMIT


@app.command("chats")
def chats(
    search: Optional[str] = typer.Option(None, "--search", "-s", help="Only chats whose title, username or phone contains this text"),
    limit: Optional[int] = typer.Option(None, "--limit", help="At most N chats, newest first (default: 50 when printing; no limit with --since/--until or --output)"),
    kinds: Optional[str] = typer.Option(None, "--type", help="Only these kinds, comma-separated: user,bot,group,supergroup,channel (e.g. --type user for private chats)"),
    unread: bool = typer.Option(False, "--unread", help="Only chats with unread messages"),
    archived: Optional[bool] = typer.Option(None, "--archived/--no-archived", help="Only archived chats, or only non-archived ones (default: both)"),
    since: Optional[str] = typer.Option(None, "--since", help="Only chats whose last message is from this date on (YYYY-MM-DD[ HH:MM], Gregorian or Shamsi)"),
    until: Optional[str] = typer.Option(None, "--until", help="Only chats whose last message is up to and including this date"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write the list to a .csv, .md or .json file instead of printing it (a .csv/.md list can be given to `telegram send`)"),
    telegram_proxy: Optional[str] = typer.Option(None, "--telegram-proxy", help="Proxy URL for Telegram"),
):
    """List your chats (private chats, groups, channels) with the id to pass to `telegram taqrir` or `archive`."""
    kind_set = _kind_set(kinds)
    since_dt, until_dt = _date_range(since, until)
    limit = effective_chat_limit(limit, since_dt, until_dt, output)
    source = _make_source(telegram_proxy)
    try:
        rows = source.iter_dialogs(search=search, limit=limit, kinds=kind_set, unread_only=unread, archived=archived,
                                   since=since_dt, until=until_dt)
    except Exception as exc:
        logger.error(f"Listing chats failed: {exc}")
        raise typer.Exit(1)
    finally:
        source.close()
    _show_people(rows, "chats", output, LIST_COLUMNS + ["last_message", "unread", "archived"])
    if limit and len(rows) >= limit:
        console.print(f"[yellow]Stopped at {limit} chats. Use --limit N for more (or give --since/--until, or --output, to list them all).[/yellow]")


@app.command("contacts")
def contacts(
    search: Optional[str] = typer.Option(None, "--search", "-s", help="Only contacts whose name, username or phone contains this text"),
    mutual: bool = typer.Option(False, "--mutual", help="Only mutual contacts (you have each other's number)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write the list to a .csv, .md or .json file (name, phone, username, id); a .csv/.md list can be given to `telegram send`"),
    telegram_proxy: Optional[str] = typer.Option(None, "--telegram-proxy", help="Proxy URL for Telegram"),
):
    """List your Telegram contacts with name, phone number, username and id."""
    source = _make_source(telegram_proxy)
    try:
        rows = source.list_contacts(search=search, mutual_only=mutual)
    except Exception as exc:
        logger.error(f"Listing contacts failed: {exc}")
        raise typer.Exit(1)
    finally:
        source.close()
    _show_people(rows, "contacts", output, LIST_COLUMNS + ["mutual"])


@app.command("members", context_settings=INTERSPERSED)
def members(
    chat: str = typer.Argument(..., help="Group or supergroup: @name, title, t.me link or numeric id (see `telegram chats`)"),
    search: Optional[str] = typer.Option(None, "--search", "-s", help="Only members whose name or username contains this text"),
    limit: Optional[int] = typer.Option(None, "--limit", help="At most N members"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write the list to a .csv, .md or .json file"),
    telegram_proxy: Optional[str] = typer.Option(None, "--telegram-proxy", help="Proxy URL for Telegram"),
):
    """List the members of a group you belong to (phone numbers only show for people who share them with you)."""
    source = _make_source(telegram_proxy)
    try:
        rows = source.list_members(chat, search=search, limit=limit)
    except Exception as exc:
        logger.error(f"Listing members failed: {exc}")
        raise typer.Exit(1)
    finally:
        source.close()
    _show_people(rows, "members", output)


def _parse_delay(value: str):
    try:
        low, _, high = value.replace(" ", "").partition("-")
        low_f = float(low)
        return (low_f, float(high) if high else low_f)
    except ValueError:
        raise typer.BadParameter("Use MIN-MAX seconds, e.g. 20-45 (or one number)", param_hint="--delay")


def _fmt_seconds(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600}h {seconds % 3600 // 60}m" if seconds >= 3600 else f"{seconds // 60}m {seconds % 60}s"


@app.command("send")
def send(
    recipients: Path = typer.Argument(..., help="List of recipients: .csv, .md (table or one per line) or .txt. Columns/values: username (@name), phone, id or name; other columns become {placeholders}"),
    message: Optional[str] = typer.Option(None, "--message", "-m", help="Message text (Markdown). With --forward: an optional note sent before the forwarded message. {name}, {first_name}, {username}, {phone} and any CSV column are filled per person"),
    message_file: Optional[Path] = typer.Option(None, "--message-file", help="Read the message from a .md or .txt file"),
    attach: Optional[Path] = typer.Option(None, "--attach", help="Send this file (photo, video, document, voice...) with the message as its caption"),
    forward: Optional[List[str]] = typer.Option(None, "--forward", help="Forward an existing message instead: https://t.me/<channel>/<id>, https://t.me/c/<id>/<id>, <chat>:<id> or me:last (repeatable; add ?single to skip the rest of an album)"),
    hide_source: bool = typer.Option(False, "--hide-source", help="With --forward: send as your own message, without «Forwarded from»"),
    hide_caption: bool = typer.Option(False, "--hide-caption", help="With --forward: drop the captions of forwarded media"),
    fmt: str = typer.Option("markdown", "--format", help="markdown (bold, italic, links, quotes, code, spoilers, custom emoji, tables), html (Telegram HTML) or plain"),
    tables: str = typer.Option("pre", "--tables", help="Markdown tables: pre (aligned monospace block) or list (`Header: value` lines)"),
    no_preview: bool = typer.Option(False, "--no-preview", help="Don't show link previews"),
    column: Optional[str] = typer.Option(None, "--column", help="CSV column that holds the recipient (default: id, username, phone or name column, found by header)"),
    delay: str = typer.Option("20-45", "--delay", help="Seconds to wait between messages, random between MIN-MAX"),
    batch_size: int = typer.Option(10, "--batch-size", help="After this many messages take a longer pause (0 = never)"),
    batch_pause: float = typer.Option(300, "--batch-pause", help="Seconds of the longer pause (randomised ±20%)"),
    daily_limit: int = typer.Option(100, "--daily-limit", help="Never send more than this many messages in 24 hours (counted across runs; 0 = no limit)"),
    max_flood_wait: float = typer.Option(3600, "--max-flood-wait", help="If Telegram asks to wait longer than this many seconds, stop and resume later"),
    test: bool = typer.Option(False, "--test", help="Send the message once to your Saved Messages (as the first recipient would get it) and stop"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Match recipients and show the message and timing; send nothing"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Don't ask for confirmation"),
    restart: bool = typer.Option(False, "--restart", help="Ignore the saved progress and send to everyone again"),
    telegram_proxy: Optional[str] = typer.Option(None, "--telegram-proxy", help="Proxy URL for Telegram"),
):
    """Send one message (or forward one) to everyone in a list, paced so the account is not limited.

    Progress is saved next to the list (<list>.send-state.json): run the same command again to resume.
    """
    from versline.services import telegram_format, telegram_people, telegram_send
    from versline.userconfig import user_config_dir

    from versline.services.channel_archive.sources.telegram import SendError

    if fmt not in telegram_format.FORMATS:
        raise typer.BadParameter(f"Choose from: {', '.join(telegram_format.FORMATS)}", param_hint="--format")
    if tables not in telegram_format.TABLES:
        raise typer.BadParameter(f"Choose from: {', '.join(telegram_format.TABLES)}", param_hint="--tables")
    if batch_size < 0 or batch_pause < 0 or daily_limit < 0:
        raise typer.BadParameter("--batch-size, --batch-pause and --daily-limit must be ≥ 0")
    try:
        text = resolve_text_input(message, str(message_file) if message_file else None, label="Message")
        forward_refs = [telegram_send.parse_forward_ref(f) for f in forward or []]
        people = telegram_people.read_recipients(recipients, column)
    except (ValueError, FileNotFoundError) as exc:
        raise typer.BadParameter(str(exc))
    if not text and not forward_refs:
        raise typer.BadParameter("Give a message (--message / --message-file) or something to --forward")
    if attach and forward_refs:
        raise typer.BadParameter("--attach can't be combined with --forward")
    if attach and not attach.is_file():
        raise typer.BadParameter(f"Attachment not found: {attach}", param_hint="--attach")
    if text and fmt != "plain":
        try:
            telegram_format.parse(telegram_send.render(text, {}, fmt), fmt, tables)
        except Exception as exc:
            raise typer.BadParameter(f"The message can't be formatted: {exc}")
    pacer = telegram_send.Pacer(_parse_delay(delay), batch_size, batch_pause, daily_limit)
    history = telegram_send.SendHistory(user_config_dir() / "telegram-send-history.json")

    source = _make_source(telegram_proxy)
    try:
        payload = telegram_send.Payload(text=text, file=attach, fmt=fmt, tables=tables, link_preview=not no_preview,
                                        hide_source=hide_source, hide_caption=hide_caption)
        with console.status("Reading the forwarded messages..." if forward_refs else "Matching recipients..."):
            payload.forwards = telegram_send.prepare_forwards(source, forward_refs)
            resolved, skipped = telegram_send.resolve_recipients(source, people)
        if not resolved:
            console.print("[red]None of the recipients could be matched.[/red]")
            for r, reason in skipped[:20]:
                console.print(f"[red]  {r.ref}: {reason}[/red]")
            raise typer.Exit(1)

        table = Table(title=f"{len(resolved)} recipients" + (f", {len(skipped)} skipped" if skipped else ""))
        for column_name in ("Name", "Username", "Phone", "ID"):
            table.add_column(column_name)
        for item in resolved[:15]:
            row = item.row
            table.add_row(item.label, f"@{row['username']}" if row.get("username") else "", row.get("phone") or "", str(item.entity_id))
        if len(resolved) > 15:
            table.add_row(f"… and {len(resolved) - 15} more", "", "", "")
        console.print(table)
        for r, reason in skipped[:20]:
            console.print(f"[yellow]  skipped {r.ref}: {reason}[/yellow]")
        if len(skipped) > 20:
            console.print(f"[yellow]  … and {len(skipped) - 20} more skipped (see the report)[/yellow]")

        first_values = telegram_send.placeholders(resolved[0])
        if text:
            console.print(f"\n[bold]Message for {resolved[0].label}:[/bold]")
            console.print(payload.preview(first_values), markup=False, highlight=False)
        if attach:
            console.print(f"[bold]Attachment:[/bold] {attach}", soft_wrap=True)
        if forward_refs:
            console.print(f"[bold]Forwarding:[/bold] {sum(len(ids) for _, ids in payload.forwards)} message(s)" + (" without the source" if hide_source else ""))

        state_path = recipients.with_name(recipients.name + ".send-state.json")
        report_path = recipients.with_name(recipients.name + ".send-report.csv")
        state = telegram_send.SendState(state_path, telegram_send.payload_key(payload, forward_refs), restart)
        if state.reset_reason:
            console.print(f"[yellow]{state.reset_reason}[/yellow]")
        remaining = [i for i in resolved if not state.is_sent(i.key)]
        if len(remaining) != len(resolved):
            console.print(f"[green]{len(resolved) - len(remaining)} already sent in an earlier run; {len(remaining)} left.[/green]")
        console.print(f"Pacing: {delay} s between messages, {batch_pause:.0f} s pause every {batch_size}, at most {daily_limit or '∞'} per 24 h. "
                      f"Estimated time: {_fmt_seconds(pacer.estimate(len(remaining)))}")

        if dry_run:
            console.print("[dim]Dry run: nothing was sent.[/dim]")
            return
        sender = telegram_send.BulkSender(source, payload, pacer, state, history, max_flood_wait=max_flood_wait)
        if test:
            try:
                sender.deliver(source.entity_of("me"), first_values)
            except (SendError, telegram_send.StopSending) as exc:
                console.print(f"[red]Test failed: {exc}[/red]")
                raise typer.Exit(1)
            console.print("[green]Sent to your Saved Messages. Check how it looks, then run again without --test.[/green]")
            return
        if not remaining:
            console.print("Nothing left to send. Use --restart to send to everyone again.")
            return
        if not yes and not typer.confirm(f"Send to {len(remaining)} recipients?", default=False):
            raise typer.Exit(1)

        source.set_flood_sleep_threshold(0)
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(),
                      redirect_stdout=True, redirect_stderr=True) as progress:
            task = progress.add_task("Sending...", total=len(resolved))
            sender.on_progress = lambda done, total, label: progress.update(task, completed=done, description=f"[green]Sending {label}" if label else "Sending")
            sender.on_wait = lambda left, reason: progress.update(task, description=f"[yellow]{reason}: {_fmt_seconds(left)} left")
            try:
                summary = sender.run(resolved)
            except KeyboardInterrupt:
                state.save()
                console.print("[yellow]Interrupted. Progress is saved; run the same command again to continue.[/yellow]")
                raise typer.Exit(code=130)
    except typer.Exit:
        raise
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted.[/yellow]")
        raise typer.Exit(code=130)
    except Exception as exc:
        logger.error(f"Send failed: {exc}")
        raise typer.Exit(1)
    finally:
        source.close()

    telegram_send.write_report(report_path, skipped, state)
    console.print(f"[bold]Sent:[/bold] {summary.sent}  failed: {summary.failed}  skipped: {len(skipped)}  → report: {report_path}", soft_wrap=True)
    for entry in summary.results:
        if entry["status"] == "failed":
            console.print(f"[red]  {entry['name']}: {entry['reason']}[/red]")
    if summary.stopped:
        console.print(f"[yellow]Stopped: {summary.stopped}. Run the same command again to continue.[/yellow]")
        raise typer.Exit(2)
    if summary.failed:
        raise typer.Exit(1)


@app.command("taqrir", context_settings=INTERSPERSED)
def taqrir(
    chat: str = typer.Argument(..., help="Chat: @user, @group, @channel, its exact title, a t.me link, a joined invite link, a numeric id (e.g. -1001234567890 or 1234567890; see `telegram chats`), or 'me'"),
    since: Optional[str] = typer.Option(None, "--since", help="Messages from this date (YYYY-MM-DD[ HH:MM], Gregorian or Shamsi e.g. 1404-07-01)"),
    until: Optional[str] = typer.Option(None, "--until", help="Messages up to and including this date (default: now)"),
    style: str = typer.Option("both", "--style", help="descriptive (scholarly prose), claims (propositions with their evidence as bullets) or both (one note with both)"),
    attribute: bool = typer.Option(False, "--attribute", help="Name the participants in the taqrir (default: anonymous labels such as «شرکت‌کننده ۱»)"),
    no_transcribe: bool = typer.Option(False, "--no-transcribe", help="Don't transcribe voice/audio/video messages"),
    no_documents: bool = typer.Option(False, "--no-documents", help="Don't read documents (pdf, docx, pptx, txt...)"),
    no_images: bool = typer.Option(False, "--no-images", help="Don't read photos with the vision model"),
    types: Optional[str] = typer.Option(None, "--types", help="Only these message types: audio,voice,video,video_note,photo,document,text (default: all)"),
    limit: Optional[int] = typer.Option(None, "--limit", help="Use at most N messages"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output folder (default: output/<chat>/taqrir)"),
    output_lang: Optional[str] = typer.Option(None, "--output-lang", help="Language of the taqrir (default: same as the discussion)"),
    instruction: Optional[str] = typer.Option(None, "--instruction", help="Extra guidance for the taqrir (e.g. which topic to focus on)"),
    instruction_file: Optional[Path] = typer.Option(None, "--instruction-file", help="Path to a .md or .txt file with extra guidance for the taqrir"),
    doc_chars: int = typer.Option(30000, "--doc-chars", help="Use at most this many characters of each document"),
    max_chars: int = typer.Option(150000, "--max-chars", help="Logs longer than this are written up in parts (notes per part, then the taqrir from the notes)"),
    max_size: Optional[float] = typer.Option(None, "--max-size", help="Skip media larger than this many MB"),
    no_log: bool = typer.Option(False, "--no-log", help="Don't write the full message log note next to the taqrir"),
    force: bool = typer.Option(False, "--force", "-f", help="Ignore the cache: transcribe, read and take notes again"),
    dry_run: bool = typer.Option(False, "--dry-run", help="List the messages in the range without downloading or calling the LLM"),
    model: Optional[str] = typer.Option(None, help="LLM Model to use (overrides config)"),
    provider: Optional[str] = typer.Option(None, help="LLM Provider (Google, OpenAI, OpenRouter, AvalAI, OpenAICompatible)"),
    api_key: Optional[str] = typer.Option(None, help="API Key for the provider"),
    api_endpoint: Optional[str] = typer.Option(None, help="Custom API Endpoint"),
    proxy: Optional[str] = typer.Option(None, help="Proxy URL for the LLM provider"),
    telegram_proxy: Optional[str] = typer.Option(None, "--telegram-proxy", help="Proxy URL for Telegram (defaults to VERSLINE_TELEGRAM_PROXY, then --proxy)"),
    extra_body: Optional[str] = typer.Option(None, "--extra-body", help=EXTRA_BODY_HELP),
    note: Optional[str] = typer.Option(None, "--note", help="Additional instruction to append to the transcription prompt"),
    note_file: Optional[Path] = typer.Option(None, "--note-file", help="Path to a .md or .txt file with an additional transcription instruction"),
    chunk_size: int = typer.Option(900, help="Transcription chunk size in seconds"),
    overlap: int = typer.Option(180, help="Transcription overlap in seconds"),
    skip_blocked: bool = typer.Option(False, "--skip-blocked", help="Skip transcription chunks blocked by the provider"),
    export: Optional[str] = export_option(),
    export_frontmatter: Optional[bool] = export_frontmatter_option(),
):
    """Write a taqrir of the discussions in a chat between two dates: voices transcribed, documents and photos read."""
    from versline.services.channel_archive.discussion import STYLES, DiscussionBuilder, DiscussionOptions
    from versline.services.channel_archive.steps import StepContext

    if style not in STYLES:
        raise typer.BadParameter(f"Unknown style '{style}'. Choose from: {', '.join(STYLES)}", param_hint="--style")
    if doc_chars < 0 or max_chars < 2000:
        raise typer.BadParameter("--doc-chars must be ≥ 0 and --max-chars ≥ 2000")
    _apply_llm_overrides(model, provider, api_key, api_endpoint, proxy, extra_body)
    since_dt, until_dt = _date_range(since, until)
    type_set = _type_set(types)
    if since_dt is None and limit is None and not dry_run:
        console.print("[yellow]No --since given: the whole chat history will be read.[/yellow]")
    if not dry_run:
        _require_llm()
    instruction_text = resolve_text_input(instruction, str(instruction_file) if instruction_file else None, label="Instruction")

    source = _make_source(telegram_proxy)
    tracker = None
    try:
        transcriber = text_llm = None
        if not dry_run:
            from versline.services.channel_archive.llm import TextLLM
            from versline.services.pricing import TokenTracker

            if not no_transcribe:
                from versline.services.transcription import AudioTranscriber

                transcriber = AudioTranscriber(user_note=resolve_user_note(note=note, note_file=str(note_file) if note_file else None))
            tracker = transcriber.tracker if transcriber is not None else TokenTracker()
            text_llm = TextLLM(tracker)
        ctx = StepContext(
            source=source, channel=None, out_dir=output, temp_dir=Path(settings.temp_directory) / "telegram",
            transcribe=not no_transcribe, max_size_mb=max_size, force=force, chunk_size=chunk_size, overlap=overlap,
            skip_blocked=skip_blocked, transcriber=transcriber, text_llm=text_llm, output_lang=output_lang or "",
        )
        options = DiscussionOptions(
            out_dir=output, temp_dir=ctx.temp_dir, since=since_dt, until=until_dt, limit=limit, types=type_set,
            style=style, attribute=attribute, transcribe=not no_transcribe, documents=not no_documents,
            images=not no_images, doc_chars=doc_chars, max_chars=max_chars, force=force, dry_run=dry_run,
            write_log=not no_log, instruction=instruction_text,
        )
        builder = DiscussionBuilder(source, ctx, options, text_llm=text_llm)
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      redirect_stdout=True, redirect_stderr=True) as progress:
            task = progress.add_task("[green]Reading chat...", total=None)
            ctx.progress = lambda message: progress.update(task, description=f"[green]{message}")
            result = builder.run(chat)
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted. Transcripts and notes made so far are cached; run the same command again to resume.[/yellow]")
        raise typer.Exit(code=130)
    except Exception as exc:
        logger.error(f"Taqrir failed: {exc}")
        raise typer.Exit(code=1)
    finally:
        source.close()

    if not result.entries:
        console.print(f"[yellow]No messages in {result.channel.title} for this range.[/yellow]")
        return
    if dry_run:
        _print_taqrir_plan(result)
        return

    console.print(f"[bold]Taqrir:[/bold] {result.note_path}", soft_wrap=True)
    if result.log_path:
        console.print(f"[bold]Message log:[/bold] {result.log_path}", soft_wrap=True)
    counts = result.metadata
    console.print(
        f"messages: {counts.get('messages')}  voices: {counts.get('voices') or 0}  documents: {counts.get('documents') or 0}  "
        f"images: {counts.get('images') or 0}  LLM calls: {result.llm_calls}  cached notes: {result.cached_notes}"
    )
    for error in result.errors:
        console.print(f"[red]  {error}[/red]")
    if tracker is not None:
        from versline.services.pricing import print_cost_report

        print_cost_report(tracker, api_key=settings.llm.api_key)
    run_exports([result.note_path], export, export_frontmatter, force=True)


def _print_taqrir_plan(result) -> None:
    from versline.services.channel_archive.discussion import shamsi_datetime

    table = Table(title=f"{result.channel.title}: {len(result.entries)} messages")
    for column in ("ID", "Date", "Sender", "Type", "Size", "Text"):
        table.add_column(column)
    kinds: dict = {}
    for entry in result.entries:
        post = entry.post
        for item in post.media:
            kinds[item.kind] = kinds.get(item.kind, 0) + 1
        size = ""
        if post.media:
            duration = sum(i.duration or 0 for i in post.media)
            size = format_duration(duration) if duration else f"{sum(i.size or 0 for i in post.media) / 1048576:.1f} MB"
        preview = " ".join(post.text.split())[:60]
        table.add_row(str(post.id), shamsi_datetime(post.date), entry.speaker, post.media_type, size, preview)
    console.print(table)
    if kinds:
        console.print("Media: " + ", ".join(f"{k} ×{v}" for k, v in sorted(kinds.items())))
