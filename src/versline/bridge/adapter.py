"""Run an existing Typer command function in-process, translating its terminal UI into bridge events.

The CLI commands already hold the real behaviour (batching, resume, skip-if-done, exports), so the bridge
calls them instead of re-implementing them. While a command runs:

* its module-level ``Progress`` (Rich) is replaced by :class:`BridgeProgress`, which emits ``progress``;
* its ``print_cost_report`` emits a ``cost`` event instead of printing a table;
* ``typer.prompt``, ``input()`` and ``getpass.getpass`` become ``prompt`` events answered by the client;
* files created or changed under the given output paths are reported as ``artifact`` events.
"""
import builtins
import getpass
import importlib
import inspect
import time
import typing
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from versline.bridge.protocol import JobContext, guess_prompt_kind

_MAX_SNAPSHOT_FILES = 20000
_SKIP_DIRS = {".git", ".obsidian", ".trash", "node_modules", "__pycache__"}


class _Task:
    def __init__(self, description: str, total: Optional[float]):
        self.description = description
        self.total = total
        self.completed: float = 0
        self.finished = False


class BridgeProgress:
    """Drop-in for rich.progress.Progress that reports through the job context."""

    ctx: Optional[JobContext] = None  # set per invocation

    def __init__(self, *columns: Any, **kwargs: Any):
        self.tasks: Dict[int, _Task] = {}
        self._next = 0
        self._last_emit = 0.0
        self.console = None

    def __enter__(self) -> "BridgeProgress":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def add_task(self, description: str = "", total: Optional[float] = 100, completed: float = 0, **kwargs: Any) -> int:
        task_id = self._next
        self._next += 1
        task = _Task(description, total)
        task.completed = completed
        self.tasks[task_id] = task
        self._emit(task, force=True)
        return task_id

    def update(
        self,
        task_id: int,
        *,
        total: Optional[float] = None,
        completed: Optional[float] = None,
        advance: Optional[float] = None,
        description: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        task = self.tasks.get(task_id)
        if task is None:
            return
        changed_label = description is not None and description != task.description
        if total is not None:
            task.total = total
        if completed is not None:
            task.completed = completed
        if advance:
            task.completed += advance
        if description is not None:
            task.description = description
        self._emit(task, force=changed_label)

    def advance(self, task_id: int, advance: float = 1) -> None:
        self.update(task_id, advance=advance)

    def remove_task(self, task_id: int) -> None:
        self.tasks.pop(task_id, None)

    def _emit(self, task: _Task, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_emit < 0.25:
            return
        self._last_emit = now
        if BridgeProgress.ctx is not None:
            BridgeProgress.ctx.progress(task.completed, task.total, task.description)


class FakeTyperContext:
    """Enough of typer.Context for the ``@app.callback(invoke_without_command=True)`` commands."""

    invoked_subcommand = None

    def get_help(self) -> str:
        return ""


def _unwrap_default(value: Any) -> Any:
    from typer.models import ParameterInfo

    if isinstance(value, ParameterInfo):
        return value.default
    return value


def _is_path_type(annotation: Any) -> str:
    """'path', 'paths' or '' for Path, Optional[Path], List[Path], Optional[List[Path]]."""
    if annotation is Path:
        return "path"
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is typing.Union:
        for arg in args:
            kind = _is_path_type(arg)
            if kind:
                return kind
    if origin in (list, List) and args and args[0] is Path:
        return "paths"
    return ""


def call_command(func: Any, **kwargs: Any) -> Any:
    """Call a Typer command function directly: fill unspecified options with their defaults, coerce paths."""
    signature = inspect.signature(func)
    try:
        hints = typing.get_type_hints(func)
    except Exception:
        hints = {}
    unknown = set(kwargs) - set(signature.parameters)
    if unknown:
        raise TypeError(f"{func.__name__}() has no option(s): {', '.join(sorted(unknown))}")
    call: Dict[str, Any] = {}
    for name, param in signature.parameters.items():
        annotation = hints.get(name, param.annotation)
        if name == "ctx" or getattr(annotation, "__name__", "") == "Context":
            call[name] = FakeTyperContext()
            continue
        if name in kwargs:
            value = kwargs[name]
        else:
            value = _unwrap_default(param.default)
            if value is inspect.Parameter.empty or value is Ellipsis:
                raise TypeError(f"{func.__name__}() needs a value for {name!r}")
        kind = _is_path_type(annotation)
        if value is not None and kind == "path" and not isinstance(value, Path):
            value = Path(value)
        elif value is not None and kind == "paths":
            value = [Path(v) for v in value]
        call[name] = value
    return func(**call)


@contextmanager
def _patched(target: Any, name: str, value: Any) -> Iterator[None]:
    missing = object()
    original = getattr(target, name, missing)
    setattr(target, name, value)
    try:
        yield
    finally:
        if original is missing:
            delattr(target, name)
        else:
            setattr(target, name, original)


@contextmanager
def interactive(ctx: JobContext) -> Iterator[None]:
    """Route typer.prompt / input() / getpass() through ``prompt`` events."""
    import typer

    def prompt(text: str, default: Any = None, hide_input: bool = False, **kwargs: Any) -> Any:
        answer = ctx.ask(text, secret=hide_input, kind=guess_prompt_kind(text),
                         default=None if default is None else str(default))
        if answer == "" and default is not None:
            answer = str(default)
        value_type = kwargs.get("type")
        return value_type(answer) if callable(value_type) else answer

    def ask_input(text: str = "") -> str:
        return ctx.ask(text, kind=guess_prompt_kind(text))

    def ask_secret(text: str = "Password: ", stream: Any = None) -> str:
        return ctx.ask(text, secret=True, kind=guess_prompt_kind(text) or "password")

    def confirm(text: str, default: bool = False, **kwargs: Any) -> bool:
        answer = ctx.ask(text, kind="confirm", default="y" if default else "n", choices=["y", "n"])
        return answer.strip().lower() in ("y", "yes", "true", "1", "بله")

    with _patched(typer, "prompt", prompt), _patched(typer, "confirm", confirm), \
            _patched(builtins, "input", ask_input), _patched(getpass, "getpass", ask_secret):
        yield


class OutputWatch:
    """Snapshot files under some paths before a run, then report what is new or changed."""

    def __init__(self, paths: Iterable[Optional[Path]]):
        self.paths = [Path(p).resolve() for p in paths if p]
        self.started = time.time() - 1
        self.before = self._snapshot()

    def _walk(self, root: Path) -> Iterator[Path]:
        if root.is_file():
            yield root
            return
        if not root.is_dir():
            return
        count = 0
        stack = [root]
        while stack:
            folder = stack.pop()
            try:
                entries = list(folder.iterdir())
            except OSError:
                continue
            for entry in entries:
                if entry.is_dir():
                    if entry.name not in _SKIP_DIRS:
                        stack.append(entry)
                elif entry.is_file():
                    count += 1
                    if count > _MAX_SNAPSHOT_FILES:
                        return
                    yield entry

    def _snapshot(self) -> Dict[Path, float]:
        snap: Dict[Path, float] = {}
        for root in self.paths:
            for path in self._walk(root):
                try:
                    snap[path] = path.stat().st_mtime
                except OSError:
                    pass
        return snap

    def changed(self) -> List[Path]:
        after = self._snapshot()
        result = [p for p, mtime in after.items() if p not in self.before or mtime > self.before[p]]
        # An explicit output file that already existed (skipped as up to date) is still the result.
        for root in self.paths:
            if root.is_file() and root not in result:
                result.append(root)
        return sorted(result, key=lambda p: (p.suffix.lower() not in (".md", ".markdown"), str(p)))


def run_command(
    ctx: JobContext,
    module_name: str,
    func_name: str,
    outputs: Iterable[Optional[Path]] = (),
    **kwargs: Any,
) -> List[Path]:
    """Run ``module.func(**kwargs)`` with the bridge patches; returns the files it produced."""
    from versline.config import settings
    from versline.services.pricing import cost_summary

    module = importlib.import_module(module_name)
    func = getattr(module, func_name)
    watch = OutputWatch(outputs)

    def report_cost(tracker: Any, api_key: Optional[str] = None, proxy: Optional[str] = None, **_: Any) -> None:
        if tracker is not None:
            ctx.cost(cost_summary(tracker, api_key=api_key or settings.llm.api_key, proxy=proxy))

    BridgeProgress.ctx = ctx
    try:
        with ExitStack() as stack:
            stack.enter_context(interactive(ctx))
            if hasattr(module, "Progress"):
                stack.enter_context(_patched(module, "Progress", BridgeProgress))
            if hasattr(module, "print_cost_report"):
                stack.enter_context(_patched(module, "print_cost_report", report_cost))
            try:
                call_command(func, **kwargs)
            except _EXIT_ERRORS as exc:
                if exc.exit_code:
                    raise CommandFailed(ctx.last_error or f"{module_name.rsplit('.', 1)[-1]} failed (exit {exc.exit_code})")
    finally:
        BridgeProgress.ctx = None
    produced = watch.changed()
    ctx.artifacts_from(produced)
    return produced


class CommandFailed(RuntimeError):
    pass


def _exit_errors() -> tuple:
    import click
    import typer

    return tuple({typer.Exit, click.exceptions.Exit})


_EXIT_ERRORS = _exit_errors()
