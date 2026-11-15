"""Execute one bridge tool: parse the request, run it, stream events, return the exit code."""
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Optional, TextIO

from versline.bridge import PROTOCOL_VERSION
from versline.bridge.protocol import Cancelled, Emitter, JobContext, LogStream, real_stdout

LLM_OVERRIDES = ("provider", "model", "api_key", "api_endpoint", "proxy")


def default_workdir() -> Path:
    """Where relative caches (work_dir/, temp/, output/) live for bridge jobs."""
    override = os.getenv("VERSLINE_BRIDGE_WORKDIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "versline" / "bridge"
    base = os.getenv("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "versline" / "bridge"


def manifest() -> Dict[str, Any]:
    from versline import __version__
    from versline.bridge.registry import all_tools

    return {
        "versline": __version__,
        "protocol": PROTOCOL_VERSION,
        "tools": [t.manifest() for t in sorted(all_tools().values(), key=lambda t: (t.category, t.name))],
    }


def apply_llm_overrides(llm: Optional[Dict[str, Any]]) -> None:
    if not llm:
        return
    from versline.config import parse_extra_body, settings

    for key in LLM_OVERRIDES:
        value = llm.get(key)
        if value:
            setattr(settings.llm, key, value)
    extra = llm.get("extra_body")
    if extra:
        settings.llm.extra_body = extra if isinstance(extra, dict) else parse_extra_body(str(extra))


def _install_log_sink(ctx: JobContext, verbose: bool) -> None:
    from loguru import logger

    def sink(message: Any) -> None:
        record = message.record
        level = record["level"].name.lower()
        text = str(record["message"])
        if level in ("error", "critical"):
            ctx.last_error = text
        ctx.emitter.emit("log", level=level, message=text)

    logger.remove()
    logger.add(sink, level="DEBUG" if verbose else "INFO", format="{message}", colorize=False)


def run(tool_name: str, request: Dict[str, Any], stdin: Optional[TextIO], workdir: Optional[Path] = None,
        verbose: bool = False, out: Optional[TextIO] = None) -> int:
    """Run a tool, writing events to ``out`` (default: the real stdout). Returns the process exit code."""
    emitter = Emitter(out or real_stdout())
    previous_stdout = sys.stdout
    # While the tool runs, stray prints become log events and never corrupt the protocol stream.
    sys.stdout = LogStream(emitter, "info")
    try:
        return _run(tool_name, request, stdin, workdir, verbose, emitter)
    finally:
        try:
            sys.stdout.flush()
        except Exception:
            pass
        sys.stdout = previous_stdout


def _run(tool_name: str, request: Dict[str, Any], stdin: Optional[TextIO], workdir: Optional[Path],
         verbose: bool, emitter: Emitter) -> int:
    from pydantic import ValidationError

    from versline import __version__
    from versline.bridge.registry import get_tool

    ctx = JobContext(emitter, stdin)
    _install_log_sink(ctx, verbose)
    # Rich wraps console output at the terminal width (80 without a tty); log lines should stay whole.
    os.environ.setdefault("COLUMNS", "160")
    emitter.emit("hello", versline=__version__, protocol=PROTOCOL_VERSION, tool=tool_name)

    try:
        tool = get_tool(tool_name)
    except KeyError:
        emitter.emit("error", code="unknown_tool", message=f"Unknown tool: {tool_name}")
        return 2

    try:
        params = tool.params.model_validate(request.get("params") or {})
    except ValidationError as exc:
        emitter.emit("error", code="invalid_params", message=str(exc),
                     details=json.loads(exc.json(include_url=False)))
        return 2

    workdir = Path(workdir or request.get("workdir") or default_workdir()).expanduser()
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        os.chdir(workdir)
    except OSError as exc:
        emitter.emit("error", code="workdir", message=f"Cannot use work folder {workdir}: {exc}")
        return 1

    import click
    import typer

    from versline.bridge.adapter import CommandFailed

    # Recent Typer vendors its own click, so accept both families of exceptions.
    exit_errors = tuple({typer.Exit, click.exceptions.Exit})
    usage_errors = tuple({typer.BadParameter, click.ClickException, *[c for c in typer.BadParameter.__mro__
                                                                         if c.__name__ == "ClickException"]})

    try:
        apply_llm_overrides(request.get("llm"))
        data = tool.run(params, ctx)
    except Cancelled as exc:
        emitter.emit("error", code="cancelled", message=str(exc) or "Cancelled")
        return 130
    except CommandFailed as exc:
        emitter.emit("error", code="failed", message=str(exc))
        return 1
    except exit_errors as exc:
        if exc.exit_code:
            emitter.emit("error", code="failed", message=ctx.last_error or f"Failed (exit {exc.exit_code})")
            return 1
        data = None
    except usage_errors + (ValueError, FileNotFoundError) as exc:
        message = exc.format_message() if hasattr(exc, "format_message") else str(exc)
        emitter.emit("error", code="bad_input", message=message)
        return 1
    except Exception as exc:
        emitter.emit("log", level="debug", message=traceback.format_exc())
        emitter.emit("error", code="exception", message=f"{type(exc).__name__}: {exc}")
        return 1

    emitter.emit("result", data=data if data is not None else {}, artifacts=ctx.artifacts)
    return 0
