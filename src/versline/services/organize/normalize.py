"""Name normalization helpers shared by every organize step.

Nothing here renames files on disk: ``norm_name`` is only used for comparing/searching, and
``windows_safe_name`` is applied to *destination* names when a new structure is built.
"""
from __future__ import annotations

import os
import re
import unicodedata

# Arabic code points that look like (and are typed instead of) the Persian ones.
_CHAR_MAP = str.maketrans({"ي": "ی", "ك": "ک", "ى": "ی"})
# Arabic diacritics (harakat, tanwin, superscript alef, Quranic marks) and tatweel.
_DIACRITICS = re.compile("[ً-ٰٟۖ-ۭـ]")
_SPACES = re.compile(r"\s+")
_INVALID_WIN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_WIN = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}


def normalize_text(text: str) -> str:
    """Safe, meaning-preserving cleanup: NFC, Arabic ي/ك/ى → Persian ی/ک, collapsed whitespace."""
    text = unicodedata.normalize("NFC", text).translate(_CHAR_MAP)
    return _SPACES.sub(" ", text).strip()


def norm_name(name: str) -> str:
    """Comparison key for a file name: ``normalize_text`` + no diacritics/tatweel + lower-case Latin."""
    return _DIACRITICS.sub("", normalize_text(name)).lower()


def split_ext(name: str):
    """``("book", "pdf")`` for ``book.pdf``; dot-files and names without a dot have no extension."""
    index = name.rfind(".")
    if index <= 0 or index == len(name) - 1:
        return name, ""
    return name[:index], name[index + 1:]


def windows_safe_name(name: str, max_len: int = 150) -> str:
    """A file/folder name that is valid on Windows (NTFS) and Linux, keeping the extension."""
    text = _INVALID_WIN.sub("_", normalize_text(name)).rstrip(" .")
    if not text:
        text = "_"
    stem, ext = split_ext(text)
    if stem.split(".")[0].upper() in _RESERVED_WIN:
        stem = stem + "_"
    ext = ext[:20]
    room = max_len - (len(ext) + 1 if ext else 0)
    stem = stem[:max(room, 1)].rstrip(" .") or "_"
    return f"{stem}.{ext}" if ext else stem


def fs_path(path) -> str:
    """Absolute path string usable for file I/O; on Windows prefixed with ``\\\\?\\`` so paths over
    260 characters still work."""
    text = os.path.abspath(str(path))
    if os.name != "nt" or text.startswith("\\\\?\\"):
        return text
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text[2:]
    return "\\\\?\\" + text
