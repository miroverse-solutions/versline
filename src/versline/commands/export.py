import sys
from pathlib import Path
from typing import List, Optional

import typer
from loguru import logger

from versline.commands._batch import expand_inputs
from versline.commands._common import INTERSPERSED

app = typer.Typer(help="Export Markdown files to Word (.docx) and PDF.", context_settings=INTERSPERSED)


@app.callback(invoke_without_command=True)
def export_command(
    ctx: typer.Context,
    inputs: Optional[List[Path]] = typer.Argument(None, help="Markdown file(s), folder(s) or glob(s)."),
    to: str = typer.Option("docx,pdf", "--to", "-t", help="Formats: docx, pdf, 'docx,pdf' or all."),
    front_matter: Optional[bool] = typer.Option(
        None, "--front-matter/--no-front-matter",
        help="Show the file's front matter (plus generated info) as a metadata table under the title. Default: on.",
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output folder (default: next to each file). A folder input keeps its sub-folder layout."),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Also search sub-folders of folder inputs."),
    force: bool = typer.Option(False, "--force", "-f", help="Re-export files whose output is already up to date."),
    page_format: Optional[str] = typer.Option(None, "--page-format", help="Page size (A4, Letter, ...). Default: A4."),
    margin: Optional[str] = typer.Option(None, "--margin", help="Page margin, e.g. 15mm or 1in."),
    landscape: bool = typer.Option(False, "--landscape", help="Landscape pages."),
    font_size: Optional[int] = typer.Option(None, "--font-size", help="Body font size (pt) for Word output."),
    install_browser: bool = typer.Option(False, "--install-browser", help="Download the Chromium browser needed for PDF output, then exit."),
):
    """Convert Markdown (Persian/RTL aware, Obsidian embeds and wikilinks handled) to .docx and .pdf."""
    if ctx.invoked_subcommand is not None:
        return
    from versline.services import docexport

    if install_browser:
        raise typer.Exit(code=docexport.install_browser())
    if not inputs:
        typer.echo(ctx.get_help())
        raise typer.Exit(code=1)
    try:
        opts = docexport.ExportOptions.from_settings(
            formats=to, front_matter=front_matter, page_format=page_format, margin=margin,
            landscape=landscape, font_size=font_size, force=force,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--to")

    files = expand_inputs(inputs, {".md", ".markdown"}, recursive=recursive)
    if not files:
        logger.error("No Markdown files found.")
        raise typer.Exit(code=1)

    roots = [p.resolve() for p in inputs if Path(p).is_dir()]
    items = []
    for path in files:
        path = Path(path)
        if output:
            rel = Path(path.name)
            for root in roots:
                try:
                    rel = path.resolve().relative_to(root)
                    break
                except ValueError:
                    continue
            base = Path(output) / rel.with_suffix("")
        else:
            base = path.with_suffix("")
        items.append(docexport.ExportItem(out_base=base, source=path))

    try:
        results = docexport.export_items(items, opts)
    except docexport.ExportError as exc:
        logger.error(str(exc))
        raise typer.Exit(code=1)
    for r in results:
        if r.ok:
            (logger.info if r.skipped else logger.success)(f"{'Up to date' if r.skipped else 'Exported'} {r.fmt.upper()}: {r.output}")
    failed = [r for r in results if not r.ok]
    if failed:
        raise typer.Exit(code=1)
