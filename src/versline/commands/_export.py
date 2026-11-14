"""Shared ``--export`` options and runner so every command offers Word/PDF output the same way."""
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import typer
from loguru import logger

EXPORT_HELP = "Also export the result to Word/PDF: docx, pdf, 'docx,pdf' or all (needs: pip install 'versline[export]')"
FRONTMATTER_HELP = "Show document metadata as a table under the title in the exported files (default: on)"


def export_option():
    return typer.Option(None, "--export", "-X", help=EXPORT_HELP)


def export_frontmatter_option():
    return typer.Option(None, "--export-frontmatter/--no-export-frontmatter", help=FRONTMATTER_HELP)


def run_exports(
    paths: Iterable[Path],
    export: Optional[str],
    front_matter: Optional[bool] = None,
    metadata: Optional[Dict[str, Any]] = None,
    force: bool = False,
) -> None:
    """Export the given .md files when ``--export`` (or VERSLINE_EXPORT_FORMATS) asks for it; no-op otherwise."""
    from versline.config import settings

    if export is None and not settings.export.formats:
        return
    from versline.services.docexport import ExportError, ExportOptions, export_markdown_files

    try:
        opts = ExportOptions.from_settings(formats=export, front_matter=front_matter, force=force)
        if not opts.formats:
            return
        paths = [Path(p) for p in paths if Path(p).is_file()]
        results = export_markdown_files(paths, opts, metadata_for=(lambda _p: dict(metadata)) if metadata else None)
    except (ExportError, ValueError) as exc:
        logger.error(f"Export failed: {exc}")
        raise typer.Exit(code=1)
    for r in results:
        if r.ok and not r.skipped:
            logger.success(f"Exported {r.fmt.upper()}: {r.output}")
    if any(not r.ok for r in results):
        raise typer.Exit(code=1)
