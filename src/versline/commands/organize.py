"""`versline organize`: catalogue a large archive, find duplicates and (later) build a clean copy.

Read-only on the sources. Design: docs/fa/organize-design.md · guide: docs/fa/organize.md
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

import typer
from loguru import logger
from rich.console import Console
from rich.progress import BarColumn, DownloadColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

app = typer.Typer(help="Catalogue a large file archive, find duplicates and plan a clean structure (sources stay untouched).")
console = Console()

WORKSPACE_HELP = ("Workspace folder holding the catalog and reports. Default: _versline_organize at the root of the "
                  "drive of the first source (scan), or the current folder / its _versline_organize subfolder.")
_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kmgt]?)b?\s*$", re.IGNORECASE)


def parse_size(text: str) -> int:
    """``"1"`` → 1, ``"10MB"`` → 10485760."""
    match = _SIZE_RE.match(str(text))
    if not match:
        raise typer.BadParameter(f"Invalid size: {text} (examples: 1, 500KB, 10MB, 1GB)")
    number, unit = float(match.group(1)), match.group(2).lower()
    return int(number * 1024 ** " kmgt".index(unit or " "))


def _resolve_workspace(workspace: Optional[Path], sources: Optional[List[Path]] = None) -> Path:
    from versline.services.organize.catalog import CATALOG_NAME, WORKSPACE_DIRNAME, default_workspace_for

    if workspace:
        return workspace
    if sources:
        return default_workspace_for(sources[0])
    cwd = Path.cwd()
    if (cwd / CATALOG_NAME).is_file():
        return cwd
    if (cwd / WORKSPACE_DIRNAME / CATALOG_NAME).is_file():
        return cwd / WORKSPACE_DIRNAME
    console.print("[red]No workspace found.[/red] Pass [bold]-w PATH[/bold] (the _versline_organize folder) "
                  "or run this from the drive root.")
    raise typer.Exit(1)


def _open_catalog(workspace: Path, create: bool = False):
    from versline.services.organize.catalog import Catalog

    try:
        catalog = Catalog(workspace, create=create)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    catalog.log_sink = logger.add(str(catalog.workspace / "logs" / "organize.log"), level="INFO", encoding="utf-8",
                                  format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {message}")
    return catalog


def _close(catalog) -> None:
    # Release the log file too: an open handle would keep the workspace locked on Windows.
    try:
        logger.remove(catalog.log_sink)
    except (AttributeError, ValueError):
        pass
    catalog.close()


@app.command("scan")
def scan(
    sources: List[Path] = typer.Argument(..., help="Source folders to catalogue (never modified)."),
    workspace: Optional[Path] = typer.Option(None, "-w", "--workspace", help=WORKSPACE_HELP),
    no_stats: bool = typer.Option(False, "--no-stats", help="Do not write reports/stats.md afterwards."),
):
    """Walk the source folders and record every file (name, size, date, kind) in the catalog. Incremental: rerun any time."""
    from versline.services.organize.reports import human_size, write_stats
    from versline.services.organize.scanner import scan_sources

    workspace = _resolve_workspace(workspace, sources)
    catalog = _open_catalog(workspace, create=True)
    console.print(f"Workspace: [bold]{catalog.workspace}[/bold]")
    logger.info(f"scan started: {[str(s) for s in sources]}")
    try:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console, transient=True) as bar:
            task = bar.add_task("Scanning…")

            def on_progress(result, current):
                bar.update(task, description=f"{result.files:,} files · {human_size(result.bytes)} · {current[-70:]}")

            result = scan_sources(catalog, sources, progress=on_progress)
        logger.info(f"scan finished: {result}")
        table = Table(title="Scan")
        for column in ("files", "size", "new", "changed", "unchanged", "missing", "errors"):
            table.add_column(column, justify="right")
        table.add_row(f"{result.files:,}", human_size(result.bytes), f"{result.new:,}", f"{result.changed:,}",
                      f"{result.unchanged:,}", f"{result.missing:,}", f"{result.errors:,}")
        console.print(table)
        if not no_stats:
            console.print(f"Report: {write_stats(catalog)}")
    except NotADirectoryError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    finally:
        _close(catalog)


@app.command("stats")
def stats(workspace: Optional[Path] = typer.Option(None, "-w", "--workspace", help=WORKSPACE_HELP)):
    """Write reports/stats.md (sizes by source and kind, scanned-book and software folders, errors)."""
    from versline.services.organize.reports import write_stats

    catalog = _open_catalog(_resolve_workspace(workspace))
    try:
        console.print(f"Report: {write_stats(catalog)}")
    finally:
        _close(catalog)


@app.command("dupes")
def dupes(
    workspace: Optional[Path] = typer.Option(None, "-w", "--workspace", help=WORKSPACE_HELP),
    min_size: str = typer.Option("1", "--min-size", help="Ignore files smaller than this (e.g. 1, 100KB, 1MB)."),
    folder_ratio: float = typer.Option(0.9, "--folder-ratio", help="Share of a folder's bytes that must exist elsewhere to call it redundant."),
):
    """Find identical files (size → partial hash → full SHA-256). Resumable; writes reports/duplicates.md/.csv."""
    from versline.services.organize.dupes import duplicate_groups, find_duplicates, redundant_folders
    from versline.services.organize.reports import human_size, write_duplicates

    minimum = parse_size(min_size)
    catalog = _open_catalog(_resolve_workspace(workspace))
    logger.info(f"dupes started (min_size={minimum})")
    try:
        columns = (SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), DownloadColumn(),
                   TimeRemainingColumn())
        with Progress(*columns, console=console, transient=True) as bar:
            tasks = {}

            def on_progress(state):
                if state.stage not in tasks:
                    tasks[state.stage] = bar.add_task(f"{state.stage} hash", total=max(state.total_bytes, 1))
                bar.update(tasks[state.stage], completed=state.done_bytes,
                           description=f"{state.stage} hash {state.done_files:,}/{state.total_files:,}")

            summary = find_duplicates(catalog, min_size=minimum, progress=on_progress)
        groups = duplicate_groups(catalog, minimum)
        folders = redundant_folders(catalog, groups, min_ratio=folder_ratio)
        report = write_duplicates(catalog, groups, folders)
        logger.info(f"dupes finished: {summary}; redundant folders: {len(folders)}")
        console.print(f"[green]{summary.groups:,}[/green] duplicate groups, {summary.files:,} files, "
                      f"[bold]{human_size(summary.wasted_bytes)}[/bold] in extra copies; "
                      f"{len(folders):,} redundant folders; {summary.errors:,} read errors.")
        console.print(f"Report: {report}")
    finally:
        _close(catalog)


@app.command("export")
def export(workspace: Optional[Path] = typer.Option(None, "-w", "--workspace", help=WORKSPACE_HELP)):
    """Write reports/files.csv: every catalogued file with kind, size, date, SHA-256 (if computed) and copy count."""
    from versline.services.organize.reports import export_files

    catalog = _open_catalog(_resolve_workspace(workspace))
    try:
        console.print(f"Report: {export_files(catalog)}")
    finally:
        _close(catalog)


@app.command("status")
def status(workspace: Optional[Path] = typer.Option(None, "-w", "--workspace", help=WORKSPACE_HELP)):
    """Show what is in the catalog and which steps have run."""
    from versline.services.organize.reports import human_size

    catalog = _open_catalog(_resolve_workspace(workspace))
    try:
        conn = catalog.conn
        table = Table(title=f"Catalog: {catalog.path}")
        for column in ("source", "path", "files", "size", "partial hashed", "full hashed", "last scan"):
            table.add_column(column)
        for root in catalog.roots():
            count, size, partial, full = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(size),0), COUNT(partial_hash), COUNT(full_hash) FROM files "
                "WHERE root_id=? AND present=1", (root["id"],)).fetchone()
            table.add_row(root["label"], root["path"], f"{count:,}", human_size(size), f"{partial:,}", f"{full:,}",
                          root["last_scan_finished"] or "[yellow]unfinished[/yellow]")
        console.print(table)
        errors = conn.execute("SELECT COUNT(*) FROM scan_errors").fetchone()[0]
        console.print(f"Errors recorded: {errors:,} · reports in {catalog.workspace / 'reports'}")
    finally:
        _close(catalog)
