"""Shared field definitions for bridge tools."""
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional

from versline.bridge.registry import F

MEDIA = [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wma", ".amr",
         ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".flv", ".wmv", ".mpeg", ".mpg", ".3gp"]
MARKDOWN = [".md", ".markdown", ".txt"]
DOCUMENTS = [".md", ".markdown", ".txt", ".pdf", ".docx", ".pptx", ".html", ".htm", ".epub", ".xlsx", ".csv"]


def note_field():
    return F(None, en="Extra instruction", fa="دستور اضافه",
             help_en="Appended to the prompt, e.g. a glossary or a focus.",
             help_fa="به پرامپت اضافه می‌شود؛ مثلاً واژه‌نامه یا نکته‌ای که باید رعایت شود.",
             widget="textarea", advanced=True)


def force_field():
    return F(False, en="Redo from scratch", fa="انجام دوباره از اول",
             help_en="Ignore existing output and saved progress.",
             help_fa="خروجی موجود و پیشرفت ذخیره‌شده نادیده گرفته شود.", advanced=True)


def as_paths(values: Optional[List[str]]) -> List[Path]:
    return [Path(v).expanduser() for v in values or []]


def parent_dirs(paths: List[Path]) -> List[Path]:
    return sorted({p.parent if p.suffix else p for p in paths})


@contextmanager
def scratch_dir(prefix: str) -> Iterator[Path]:
    """A temporary folder under the bridge work folder (the current directory), removed afterwards."""
    base = Path("temp") / "bridge"
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix=prefix, dir=str(base))).resolve()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
