"""NDJSON event stream and the job context handed to every bridge tool.

stdout belongs to the protocol: one JSON object per line. Anything else the code prints (Rich tables,
print(), typer.echo) is turned into ``log`` events, and loguru goes through a sink that does the same.

Events (all carry "type"):
    hello     {versline, protocol, tool}
    progress  {current, total, label}            total may be null (indeterminate)
    log       {level, message}
    prompt    {id, message, secret, kind, default, choices}
    artifact  {path, kind, exists}
    cost      {input_tokens, output_tokens, cached_tokens, usd, irt, error}
    result    {data}                              last event of a successful run
    error     {code, message}                     last event of a failed run

Requests on stdin (after the first request line):
    {"type": "answer", "id": "...", "value": "..."}   reply to a prompt (value null = declined)
    {"type": "cancel"}                                 stop the job
"""
import io
import json
import os
import queue
import re
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, TextIO

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_MARKUP_RE = re.compile(r"\[/?[a-z_ ]+(?: [a-z_]+)*\]")

MEDIA_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac", ".mp4", ".mkv", ".mov", ".webm"}


class Cancelled(Exception):
    """Raised inside a job when the client cancelled it or closed stdin while a prompt was pending."""


def plain(text: Any) -> str:
    """Strip ANSI escapes and Rich markup such as [green]...[/green]."""
    value = _ANSI_RE.sub("", str(text if text is not None else ""))
    try:
        from rich.text import Text

        return Text.from_markup(value).plain
    except Exception:
        return _MARKUP_RE.sub("", value)


def artifact_kind(path: Path) -> str:
    if path.is_dir():
        return "folder"
    ext = path.suffix.lower()
    if ext in (".md", ".markdown"):
        return "note"
    if ext in MEDIA_EXT:
        return "media"
    return ext.lstrip(".") or "file"


class Emitter:
    """Thread-safe NDJSON writer bound to the real stdout."""

    def __init__(self, stream: TextIO):
        self._stream = stream
        self._lock = threading.Lock()

    def emit(self, type_: str, **data: Any) -> None:
        line = json.dumps({"type": type_, **data}, ensure_ascii=False, default=str)
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()


class LogStream(io.TextIOBase):
    """A text stream that turns every written line into a ``log`` event (stands in for sys.stdout)."""

    def __init__(self, emitter: Emitter, level: str = "info"):
        self._emitter = emitter
        self._level = level
        self._buffer = ""

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return "utf-8"

    def writable(self) -> bool:
        return True

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        raise io.UnsupportedOperation("fileno")

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._send(line)
        return len(text)

    def flush(self) -> None:
        if self._buffer:
            self._send(self._buffer)
            self._buffer = ""

    def _send(self, line: str) -> None:
        line = plain(line).rstrip()
        if line.strip():
            self._emitter.emit("log", level=self._level, message=line)


class JobContext:
    """What a tool can do while it runs: report progress, log, ask the user, announce outputs."""

    def __init__(self, emitter: Emitter, stdin: Optional[TextIO] = None):
        self.emitter = emitter
        self.last_error: Optional[str] = None
        self.artifacts: List[Dict[str, Any]] = []
        self.cancelled = threading.Event()
        self._answers: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._prompt_counter = 0
        self._stdin_closed = threading.Event()
        self._reader: Optional[threading.Thread] = None
        if stdin is not None:
            self._reader = threading.Thread(target=self._read_stdin, args=(stdin,), daemon=True)
            self._reader.start()
        else:
            self._stdin_closed.set()

    # -- incoming messages --

    def _read_stdin(self, stdin: TextIO) -> None:
        try:
            for raw in stdin:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    message = json.loads(raw)
                except ValueError:
                    continue
                kind = message.get("type")
                if kind == "answer":
                    self._answers.put(message)
                elif kind == "cancel":
                    self.cancel()
        except (OSError, ValueError):
            pass
        finally:
            self._stdin_closed.set()
            self._answers.put({"type": "eof"})

    def cancel(self) -> None:
        """Stop now. Long jobs keep their resumable caches, so hard-exiting is safe and immediate."""
        self.cancelled.set()
        self.emitter.emit("error", code="cancelled", message="Cancelled")
        os._exit(130)

    def check_cancel(self) -> None:
        if self.cancelled.is_set():
            raise Cancelled()

    # -- outgoing events --

    def progress(self, current: Optional[float] = None, total: Optional[float] = None, label: Optional[str] = None) -> None:
        self.emitter.emit("progress", current=current, total=total, label=plain(label) if label else None)

    def log(self, message: str, level: str = "info") -> None:
        self.emitter.emit("log", level=level, message=plain(message))

    def cost(self, summary: Dict[str, Any]) -> None:
        self.emitter.emit("cost", **summary)

    def artifact(self, path: Path, kind: Optional[str] = None) -> None:
        path = Path(path).resolve()
        if any(a["path"] == str(path) for a in self.artifacts):
            return
        entry = {"path": str(path), "kind": kind or artifact_kind(path), "exists": path.exists()}
        self.artifacts.append(entry)
        self.emitter.emit("artifact", **entry)

    def artifacts_from(self, paths: Iterable[Path]) -> None:
        for path in paths:
            self.artifact(Path(path))

    def ask(
        self,
        message: str,
        secret: bool = False,
        kind: Optional[str] = None,
        default: Optional[str] = None,
        choices: Optional[List[str]] = None,
    ) -> str:
        """Ask the client a question and block until it answers. Declining or a closed stdin cancels the job."""
        if self._stdin_closed.is_set() and self._answers.empty():
            raise Cancelled("A prompt needs an answer but stdin is closed: " + plain(message))
        self._prompt_counter += 1
        prompt_id = f"p{self._prompt_counter}"
        self.emitter.emit(
            "prompt", id=prompt_id, message=plain(message).strip(), secret=secret, kind=kind,
            default=default, choices=choices,
        )
        while True:
            answer = self._answers.get()
            if answer.get("type") == "eof":
                raise Cancelled("stdin closed while waiting for an answer")
            if answer.get("id") != prompt_id:
                continue
            value = answer.get("value")
            if value is None:
                raise Cancelled("The user declined: " + plain(message))
            return str(value)


def guess_prompt_kind(message: str) -> Optional[str]:
    """Classify common prompts (Telethon login) so clients can show a localized question."""
    text = (message or "").lower()
    if "phone" in text:
        return "phone"
    if "code" in text:
        return "code"
    if "password" in text:
        return "password"
    if "api_id" in text:
        return "api_id"
    if "api_hash" in text:
        return "api_hash"
    return None


def real_stdout() -> TextIO:
    """The process stdout, UTF-8, regardless of what sys.stdout currently points to."""
    stream = sys.__stdout__ or sys.stdout
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    return stream
