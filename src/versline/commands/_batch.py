"""Shared helpers for commands that accept several inputs (files, folders, globs)."""
import glob
import re
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence

import typer
from loguru import logger

TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}
MEDIA_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wma", ".amr",
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".flv", ".wmv", ".mpeg", ".mpg", ".3gp",
}

# Files this toolkit generates itself; skipped when a folder is expanded so reruns don't feed outputs back in.
GENERATED_NAME_PATTERNS = (
    re.compile(r"_translated$"),
    re.compile(r"_summary_(outline|detailed|slides)$"),
    re.compile(r"_qual_\d"),
    re.compile(r"_(central_concepts|segments|detailed)_\d"),
    re.compile(r"_full$"),
)

SKIPPED = "skipped"
DONE = "done"

_GLOB_CHARS = set("*?[")


def is_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def _is_generated(path: Path) -> bool:
    return any(p.search(path.stem) for p in GENERATED_NAME_PATTERNS)


def _walk_dir(directory: Path, extensions: Iterable[str], recursive: bool) -> List[Path]:
    exts = {e.lower() for e in extensions}
    candidates = directory.rglob("*") if recursive else directory.iterdir()
    found = [
        p for p in candidates
        if p.is_file() and p.suffix.lower() in exts and not p.name.startswith(".") and not _is_generated(p)
    ]
    return sorted(found, key=lambda p: [s.lower() for s in p.parts])


def expand_inputs(
    inputs: Optional[Sequence],
    extensions: Iterable[str],
    recursive: bool = False,
    allow_urls: bool = False,
) -> List:
    """Expand files, folders and glob patterns into a de-duplicated, ordered list of inputs.

    Explicitly named files are always kept (whatever their extension); only folder expansion filters.
    """
    result: List = []
    seen = set()

    def add(item):
        key = item if isinstance(item, str) else str(item.resolve())
        if key not in seen:
            seen.add(key)
            result.append(item)

    for raw in inputs or []:
        text = str(raw)
        if allow_urls and is_url(text):
            add(text)
            continue
        path = Path(text).expanduser()
        if path.is_dir():
            files = _walk_dir(path, extensions, recursive)
            if not files:
                logger.warning(f"No matching files found in folder: {path}")
            for f in files:
                add(f)
        elif path.exists():
            add(path)
        elif _GLOB_CHARS & set(text):
            matches = sorted(Path(m) for m in glob.glob(text, recursive=True))
            matches = [m for m in matches if m.is_file()]
            if not matches:
                raise typer.BadParameter(f"No files match: {text}")
            for m in matches:
                add(m)
        else:
            raise typer.BadParameter(f"Path does not exist: {text}")
    return result


def resolve_batch_output(output: Optional[Path], item_count: int) -> Optional[Path]:
    """With several inputs, -o is an output directory (created if needed); with one, it is left as given."""
    if output is None or item_count <= 1:
        return output
    if output.exists() and not output.is_dir():
        raise typer.BadParameter("-o must be a directory when more than one input is given")
    output.mkdir(parents=True, exist_ok=True)
    return output


def run_batch(items: Sequence, process_one: Callable[[object], Optional[str]]) -> None:
    """Run process_one on every item, continuing past failures.

    process_one returns SKIPPED when the item was already complete, anything else counts as done.
    Raises typer.Exit(1) if any item failed. A lone item that fails still exits 1, as it always did.
    """
    total = len(items)
    done = skipped = 0
    failed: List[str] = []

    for index, item in enumerate(items, start=1):
        if total > 1:
            logger.info(f"[{index}/{total}] {item}")
        try:
            status = process_one(item)
        except typer.Exit as exc:
            if exc.exit_code:
                failed.append(str(item))
            else:
                done += 1
            continue
        except Exception as exc:
            logger.error(f"Failed: {item}: {exc}")
            failed.append(str(item))
            continue
        if status == SKIPPED:
            skipped += 1
        else:
            done += 1

    if total > 1:
        logger.info(f"Batch finished: {done} done, {skipped} skipped (already complete), {len(failed)} failed")
        for name in failed:
            logger.error(f"  failed: {name}")
    if failed:
        raise typer.Exit(code=1)


def output_is_complete(*paths: Path) -> bool:
    """True when every given output exists and is non-empty."""
    return all(p.exists() and p.stat().st_size > 0 for p in paths)
