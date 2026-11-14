"""`versline organize`: catalogue a large archive, find duplicates and rebuild it in a clean structure.

scan/stats/dupes/export/plan/verify only read the sources. apply copies files (sources untouched) and moves
audio/video on the same drive (journaled, reversible with revert-moves). Design: docs/fa/organize-design.md
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

app = typer.Typer(help="Catalogue a large file archive, find duplicates and rebuild it in a clean structure (copies; audio/video moved, reversibly).")
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


def _export_reports(paths, export, export_frontmatter, workspace) -> None:
    if export is None:
        return
    from versline.commands._export import run_exports

    run_exports(paths, export, export_frontmatter, {"type": "organize report", "workspace": str(workspace)}, force=True)


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
def stats(
    workspace: Optional[Path] = typer.Option(None, "-w", "--workspace", help=WORKSPACE_HELP),
    export: Optional[str] = typer.Option(None, "--export", "-X", help="Also export the .md report to Word/PDF: docx, pdf, 'docx,pdf' or all (needs versline[export])."),
    export_frontmatter: Optional[bool] = typer.Option(None, "--export-frontmatter/--no-export-frontmatter", help="Show a metadata table under the title in exported files."),
):
    """Write reports/stats.md (sizes by source and kind, scanned-book and software folders, errors)."""
    from versline.services.organize.reports import write_stats

    catalog = _open_catalog(_resolve_workspace(workspace))
    try:
        report = write_stats(catalog)
        console.print(f"Report: {report}")
    finally:
        _close(catalog)
    _export_reports([report], export, export_frontmatter, report.parent.parent)
    _export_reports([report], export, export_frontmatter, report.parent.parent)


@app.command("dupes")
def dupes(
    workspace: Optional[Path] = typer.Option(None, "-w", "--workspace", help=WORKSPACE_HELP),
    min_size: str = typer.Option("1", "--min-size", help="Ignore files smaller than this (e.g. 1, 100KB, 1MB)."),
    folder_ratio: float = typer.Option(0.9, "--folder-ratio", help="Share of a folder's bytes that must exist elsewhere to call it redundant."),
    export: Optional[str] = typer.Option(None, "--export", "-X", help="Also export the .md report to Word/PDF: docx, pdf, 'docx,pdf' or all (needs versline[export])."),
    export_frontmatter: Optional[bool] = typer.Option(None, "--export-frontmatter/--no-export-frontmatter", help="Show a metadata table under the title in exported files."),
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


# ---------------------------------------------------------------------------------------------------------------
# plan / apply / verify / revert-moves
# ---------------------------------------------------------------------------------------------------------------

def _load_ruleset(catalog, rules: Optional[Path]):
    from versline.services.organize.rules import load_rules

    path = rules or catalog.workspace / "rules.txt"
    if not path.is_file():
        console.print(f"[red]No rules file at {path}.[/red] See docs/fa/organize.md for the format.")
        raise typer.Exit(1)
    ruleset = load_rules(path)
    from versline.services.organize.rules import load_assignments

    assigned = load_assignments(catalog.workspace / "assignments.csv", ruleset)
    if assigned:
        console.print(f"assignments.csv: {assigned:,} per-file destinations")
    for error in ruleset.errors:
        console.print(f"[yellow]rules.txt {error}[/yellow]")
    return ruleset


def _plan_path(catalog, plan: Optional[Path]) -> Path:
    return plan or catalog.workspace / "plan" / "plan.csv"


def _read_plan_or_exit(path: Path):
    from versline.services.organize.planner import read_plan

    if not path.is_file():
        console.print(f"[red]No plan at {path}. Run 'versline organize plan' first.[/red]")
        raise typer.Exit(1)
    try:
        return read_plan(path)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)


@app.command("plan")
def plan_command(
    workspace: Optional[Path] = typer.Option(None, "-w", "--workspace", help=WORKSPACE_HELP),
    rules: Optional[Path] = typer.Option(None, "--rules", help="Rules file (default: <workspace>/rules.txt)."),
    export: Optional[str] = typer.Option(None, "--export", "-X", help="Also export the .md report to Word/PDF: docx, pdf, 'docx,pdf' or all (needs versline[export])."),
    export_frontmatter: Optional[bool] = typer.Option(None, "--export-frontmatter/--no-export-frontmatter", help="Show a metadata table under the title in exported files."),
):
    """Build plan/plan.csv and plan/plan_summary.md from the catalog and rules.txt. Changes no files."""
    from versline.services.organize.planner import build_plan, write_plan, write_plan_summary
    from versline.services.organize.reports import human_size
    from versline.services.organize.rules import load_taxonomy

    catalog = _open_catalog(_resolve_workspace(workspace))
    try:
        ruleset = _load_ruleset(catalog, rules)
        taxonomy = load_taxonomy(catalog.workspace / "taxonomy.txt")
        rows, stats = build_plan(catalog, ruleset, taxonomy)
        plan_dir = catalog.workspace / "plan"
        write_plan(rows, plan_dir / "plan.csv")
        write_plan_summary(rows, stats, ruleset, plan_dir / "plan_summary.md")
        table = Table(title="Plan (nothing executed yet)")
        for column in ("action", "files", "size"):
            table.add_column(column)
        totals = {}
        for row in rows:
            entry = totals.setdefault(row.action, [0, 0])
            entry[0] += 1
            entry[1] += row.size
        for action, (count, size) in sorted(totals.items()):
            table.add_row(action, f"{count:,}", human_size(size))
        console.print(table)
        logger.info(f"plan built: { {k: v[0] for k, v in totals.items()} }")
        console.print(f"Review: {plan_dir / 'plan_summary.md'} and {plan_dir / 'plan.csv'}")
    finally:
        _close(catalog)
    _export_reports([plan_dir / "plan_summary.md"], export, export_frontmatter, plan_dir.parent)


@app.command("apply")
def apply_command(
    workspace: Optional[Path] = typer.Option(None, "-w", "--workspace", help=WORKSPACE_HELP),
    plan: Optional[Path] = typer.Option(None, "--plan", help="Plan CSV (default: <workspace>/plan/plan.csv)."),
    rules: Optional[Path] = typer.Option(None, "--rules", help="Rules file, for @dest_root."),
    only: Optional[str] = typer.Option(None, "--only", help="Run only 'move' or only 'copy' rows."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen; change nothing."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask for confirmation."),
    skip_unclassified: bool = typer.Option(False, "--skip-unclassified",
                                           help="Leave files without a rule (bound for the @default archive) for later."),
):
    """Execute the approved plan: move audio/video (same-drive rename, journaled) and copy the rest (SHA-256 checked).
    Resumable: rerun to continue. Never overwrites or deletes."""
    import shutil

    from versline.services.organize.applier import apply_plan
    from versline.services.organize.reports import human_size

    if only not in (None, "move", "copy"):
        raise typer.BadParameter("--only must be 'move' or 'copy'")
    catalog = _open_catalog(_resolve_workspace(workspace))
    try:
        ruleset = _load_ruleset(catalog, rules)
        dest_root = catalog.base.joinpath(*ruleset.dest_root.split("/"))
        rows = _read_plan_or_exit(_plan_path(catalog, plan))
        preview = apply_plan(catalog, rows, dest_root, only=only, dry_run=True, skip_unclassified=skip_unclassified)
        free = shutil.disk_usage(str(catalog.base)).free
        console.print(f"Destination: [bold]{dest_root}[/bold]\n"
                      f"To move: {preview.moved:,} files · to copy: {preview.copied:,} files "
                      f"({human_size(preview.bytes_copied)}) · already done / not approved: {preview.skipped:,} · "
                      f"free space: {human_size(free)}")
        if dry_run or (preview.moved + preview.copied) == 0:
            return
        if not yes and not typer.confirm("Proceed?"):
            raise typer.Exit(1)
        logger.info(f"apply started (only={only})")
        columns = (SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), DownloadColumn(),
                   TimeRemainingColumn())
        with Progress(*columns, console=console, transient=True) as bar:
            task = bar.add_task("apply", total=max(preview.bytes_copied, 1))

            def on_progress(state):
                bar.update(task, completed=state.done_bytes,
                           description=f"{state.done_files:,}/{state.total_files:,} {state.current[-50:]}")

            try:
                result = apply_plan(catalog, rows, dest_root, only=only, progress=on_progress,
                                    skip_unclassified=skip_unclassified)
            except (OSError, ValueError) as exc:
                console.print(f"[red]{exc}[/red]")
                raise typer.Exit(1)
        logger.info(f"apply finished: {result}")
        console.print(f"[green]moved {result.moved:,}[/green] · [green]copied {result.copied:,}[/green] "
                      f"({human_size(result.bytes_copied)}) · errors {result.errors:,}. "
                      "Run 'versline organize verify' next.")
        if result.errors:
            raise typer.Exit(1)
    finally:
        _close(catalog)


@app.command("verify")
def verify_command(
    workspace: Optional[Path] = typer.Option(None, "-w", "--workspace", help=WORKSPACE_HELP),
    plan: Optional[Path] = typer.Option(None, "--plan", help="Plan CSV (default: <workspace>/plan/plan.csv)."),
    rules: Optional[Path] = typer.Option(None, "--rules", help="Rules file, for @dest_root."),
    deep: bool = typer.Option(False, "--deep", help="Re-hash every copied file (slow)."),
    export: Optional[str] = typer.Option(None, "--export", "-X", help="Also export the .md report to Word/PDF: docx, pdf, 'docx,pdf' or all (needs versline[export])."),
    export_frontmatter: Optional[bool] = typer.Option(None, "--export-frontmatter/--no-export-frontmatter", help="Show a metadata table under the title in exported files."),
):
    """Check every plan row against the destination and write reports/verify.md + coverage.csv."""
    from versline.services.organize.applier import verify

    catalog = _open_catalog(_resolve_workspace(workspace))
    try:
        ruleset = _load_ruleset(catalog, rules)
        dest_root = catalog.base.joinpath(*ruleset.dest_root.split("/"))
        counts = verify(catalog, _read_plan_or_exit(_plan_path(catalog, plan)), dest_root, deep=deep)
        for state, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            console.print(f"{state:<32} {count:>8,}")
        verify_report = catalog.workspace / "reports" / "verify.md"
        console.print(f"Report: {verify_report}")
    finally:
        _close(catalog)
    _export_reports([verify_report], export, export_frontmatter, verify_report.parent.parent)


@app.command("revert-moves")
def revert_moves_command(
    workspace: Optional[Path] = typer.Option(None, "-w", "--workspace", help=WORKSPACE_HELP),
    rules: Optional[Path] = typer.Option(None, "--rules", help="Rules file, for @dest_root."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only count what would be moved back."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask for confirmation."),
):
    """Move every moved audio/video file back to where it was. Copies are not touched."""
    from versline.services.organize.applier import revert_moves

    catalog = _open_catalog(_resolve_workspace(workspace))
    try:
        ruleset = _load_ruleset(catalog, rules)
        dest_root = catalog.base.joinpath(*ruleset.dest_root.split("/"))
        preview = revert_moves(catalog, dest_root, dry_run=True)
        console.print(f"Files to move back: {preview['reverted']:,}")
        if dry_run or not preview["reverted"]:
            return
        if not yes and not typer.confirm("Move them back?"):
            raise typer.Exit(1)
        counts = revert_moves(catalog, dest_root)
        logger.info(f"revert-moves: {counts}")
        console.print(f"Reverted {counts['reverted']:,}, errors {counts['errors']:,}.")
    finally:
        _close(catalog)
