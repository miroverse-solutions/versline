"""`versline bridge`: machine-readable interface used by the Versobs Obsidian plugin and other front ends."""
import json
import sys
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="Machine-readable interface (JSON) for other programs, e.g. the Versobs Obsidian plugin.")


@app.command("info")
def info(
    pretty: bool = typer.Option(False, "--pretty", help="Indent the JSON"),
):
    """Print versions and every tool with its parameter schema as one JSON document."""
    from versline.bridge.runner import manifest

    typer.echo(json.dumps(manifest(), ensure_ascii=False, indent=2 if pretty else None))


@app.command("run")
def run(
    tool: str = typer.Argument(..., help="Tool name, e.g. summarize.file (see `versline bridge info`)"),
    params: Optional[str] = typer.Option(None, "--params", help="Request JSON inline instead of the first stdin line"),
    params_file: Optional[Path] = typer.Option(None, "--params-file", exists=True, dir_okay=False,
                                               help="Read the request JSON from a file instead of stdin"),
    workdir: Optional[Path] = typer.Option(None, "--workdir", help="Folder for caches and temporary files"),
    verbose: bool = typer.Option(False, "--debug", help="Also emit debug log events"),
):
    """Run one tool and stream NDJSON events on stdout.

    The request is {"params": {...}, "llm": {"model": ..., "provider": ..., "proxy": ...}}, or just the params
    object. After it, stdin may carry {"type":"answer","id":...,"value":...} and {"type":"cancel"} lines.
    """
    from versline.bridge.runner import run as run_tool

    stdin = sys.stdin
    try:
        if params is not None:
            raw = params
        elif params_file is not None:
            raw = params_file.read_text(encoding="utf-8")
        else:
            raw = stdin.readline()
        request = json.loads(raw) if raw and raw.strip() else {}
    except ValueError as exc:
        sys.__stdout__.write(json.dumps({"type": "error", "code": "invalid_request", "message": str(exc)}) + "\n")
        raise typer.Exit(2)
    if not isinstance(request, dict):
        request = {}
    if "params" not in request and "llm" not in request and "workdir" not in request:
        request = {"params": request}
    try:
        code = run_tool(tool, request, stdin, workdir=workdir, verbose=verbose)
    except Exception as exc:  # a bug in the bridge itself: still answer in protocol form
        sys.__stdout__.write(json.dumps({"type": "error", "code": "internal", "message": f"{type(exc).__name__}: {exc}"},
                                        ensure_ascii=False) + "\n")
        code = 1
    sys.__stdout__.flush()
    raise typer.Exit(code)
