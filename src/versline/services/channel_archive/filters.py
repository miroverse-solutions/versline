from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import List, Optional, Pattern, Sequence, Set

from versline.services.channel_archive.models import ChannelPost, MediaItem

MATCH_TARGETS = ("name", "caption", "any")
EXT_ALIASES = {"word": {"doc", "docx"}}
MIME_EXTS = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/rtf": "rtf",
    "application/vnd.oasis.opendocument.text": "odt",
    "application/epub+zip": "epub",
    "application/zip": "zip",
}

# Arabic forms of Persian letters, tatweel and diacritics; ZWNJ and "_" count as spaces so "جزوه فقه" finds "جزوه_فقه.pdf".
_CHAR_MAP = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ـ": None, "‌": " ", "_": " "})
_DIACRITICS_RE = re.compile(r"[ً-ٰٟ]")


def _normalize_pattern(pattern: str) -> str:
    """Character substitutions only: casefolding would turn regex classes like \\D into \\d."""
    return _DIACRITICS_RE.sub("", pattern.translate(_CHAR_MAP))


def normalize_fa(text: str) -> str:
    return " ".join(_normalize_pattern(text).casefold().split())


def item_extension(item: MediaItem) -> Optional[str]:
    """Lower-case extension without the dot, from the file name or else the mime type."""
    if item.file_name:
        suffix = PurePosixPath(item.file_name).suffix.lstrip(".").lower()
        if suffix:
            return suffix
    return MIME_EXTS.get((item.mime or "").lower())


def parse_extensions(value: str) -> Set[str]:
    exts: Set[str] = set()
    for part in value.split(","):
        part = part.strip().lstrip(".").lower()
        if part:
            exts |= EXT_ALIASES.get(part, {part})
    return exts


def _compile(patterns: Sequence[str], option: str) -> List[Pattern]:
    compiled = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(_normalize_pattern(pattern), re.IGNORECASE))
        except re.error as exc:
            raise ValueError(f"Invalid {option} pattern {pattern!r}: {exc}") from None
    return compiled


@dataclass
class FileFilter:
    """Selects media items by extension and by regexes on the file name and/or the post caption."""

    extensions: Optional[Set[str]] = None
    include: List[Pattern] = field(default_factory=list)  # any match keeps the item
    exclude: List[Pattern] = field(default_factory=list)  # any match drops it (wins over include)
    match_in: str = "name"

    @classmethod
    def build(
        cls,
        ext: Optional[str] = None,
        match: Sequence[str] = (),
        exclude: Sequence[str] = (),
        match_in: str = "name",
    ) -> Optional["FileFilter"]:
        """None when no filter is given; ValueError on a bad regex or --match-in value."""
        if match_in not in MATCH_TARGETS:
            raise ValueError(f"--match-in must be one of: {', '.join(MATCH_TARGETS)}")
        extensions = parse_extensions(ext) if ext else None
        include, excluded = _compile(match, "--match"), _compile(exclude, "--exclude")
        if not (extensions or include or excluded):
            return None
        return cls(extensions=extensions, include=include, exclude=excluded, match_in=match_in)

    def _texts(self, post: ChannelPost, item: MediaItem) -> List[str]:
        texts = []
        if self.match_in in ("name", "any"):
            texts.append(normalize_fa(item.file_name or ""))
        if self.match_in in ("caption", "any"):
            texts.append(normalize_fa(post.text))
        return texts

    def accepts(self, post: ChannelPost, item: MediaItem) -> bool:
        if self.extensions and item_extension(item) not in self.extensions:
            return False
        texts = self._texts(post, item)
        if self.include and not any(p.search(t) for p in self.include for t in texts):
            return False
        return not any(p.search(t) for p in self.exclude for t in texts)

    def matching_indices(self, post: ChannelPost) -> List[int]:
        return [i for i, item in enumerate(post.media) if self.accepts(post, item)]
