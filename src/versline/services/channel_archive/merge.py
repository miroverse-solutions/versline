"""Detect items a channel split across several consecutive posts and merge them into one post.

A post continues the previous one when they were sent close together and either the previous post
ends with a continuation marker (⬇️, 👇, «ادامه دارد», ...) or this one starts with one (⬆️, 👆, «ادامه», ...).
"""
from __future__ import annotations

import re
from dataclasses import replace
from datetime import timedelta
from typing import Iterable, Iterator, List, Optional

from versline.services.channel_archive.models import ChannelPost

DEFAULT_MAX_GAP = timedelta(minutes=15)

_DOWN = "⬇👇🔽↓⏬"
_UP = "⬆👆🔼↑⏫"
_INVISIBLE_RE = re.compile("[️︎‍‎‏⁦-⁩]")
_PUNCT = r"\s.…:!"
_NEXT = r"(?:بعد|بعدی|پسین)"
_PREV = r"(?:قبل|قبلی|پیشین|گذشته)"
_POST = r"(?:پست|فرسته|پیام|مطلب)(?:[‌\s]*(?:ها|های))?"

# whole last line: only down arrows, or «ادامه»/«ادامه دارد»/«ادامه در پست بعد»/«ادامه مطلب 👇» ...
_END_LINE_RE = re.compile(
    rf"^(?:[{_PUNCT}]*[{_DOWN}][{_DOWN}{_PUNCT}]*"
    rf"|[{_PUNCT}{_DOWN}]*ادامه(?:\s*(?:دارد|مطلب|(?:(?:را\s+)?در\s+{_POST}\s*{_NEXT}(?:\s*بخوانید)?)))?[{_PUNCT}{_DOWN}]*)$"
)
# whole first line: only up arrows, or «ادامه»/«ادامه‌ی مطلب قبل»/«ادامه از پست قبل» ...
_START_LINE_RE = re.compile(
    rf"^(?:[{_PUNCT}]*[{_UP}][{_UP}{_PUNCT}]*"
    rf"|[{_PUNCT}{_UP}]*ادامه(?:[‌\s]*ی)?(?:\s*(?:از|ی)?\s*(?:{_POST}|بحث)?\s*{_PREV})?[{_PUNCT}{_UP}]*)$"
)
# first line that starts with up arrows followed by text: only the arrows are the marker
_START_ARROWS_RE = re.compile(rf"^[{_PUNCT}]*[{_UP}][{_UP}\s]*")
# lines after the end marker that don't count: channel signatures, hashtags, links
_TAIL_LINE_RE = re.compile(r"^(?:\s*(?:@\w+|#\S+|https?://\S+)\s*)+$")


def _norm(line: str) -> str:
    return _INVISIBLE_RE.sub("", line).strip()


def _end_marker_index(lines: List[str]) -> Optional[int]:
    for index in range(len(lines) - 1, -1, -1):
        line = _norm(lines[index])
        if not line or _TAIL_LINE_RE.match(line):
            continue
        return index if _END_LINE_RE.match(line) else None
    return None


def _first_line_index(lines: List[str]) -> Optional[int]:
    for index, line in enumerate(lines):
        if _norm(line):
            return index
    return None


def ends_with_marker(text: str) -> bool:
    return _end_marker_index((text or "").splitlines()) is not None


def starts_with_marker(text: str) -> bool:
    lines = (text or "").splitlines()
    index = _first_line_index(lines)
    if index is None:
        return False
    line = _norm(lines[index])
    return bool(_START_LINE_RE.match(line) or _START_ARROWS_RE.match(line))


def strip_end_marker(text: str) -> str:
    lines = (text or "").splitlines()
    index = _end_marker_index(lines)
    if index is not None:
        del lines[index]
    return "\n".join(lines).strip()


def strip_start_marker(text: str) -> str:
    lines = (text or "").splitlines()
    index = _first_line_index(lines)
    if index is not None:
        line = _norm(lines[index])
        if _START_LINE_RE.match(line):
            del lines[index]
        elif _START_ARROWS_RE.match(line):
            lines[index] = _START_ARROWS_RE.sub("", line)
    return "\n".join(lines).strip()


def is_continuation(prev: ChannelPost, nxt: ChannelPost, max_gap: timedelta = DEFAULT_MAX_GAP) -> bool:
    gap = nxt.date - prev.date
    if gap < timedelta(0) or gap > max_gap:
        return False
    return ends_with_marker(prev.text) or starts_with_marker(nxt.text)


def merge_posts(parts: List[ChannelPost]) -> ChannelPost:
    """One post holding the text and media of all parts; identified by the first part."""
    texts = []
    for i, part in enumerate(parts):
        text = part.text or ""
        if i > 0:
            text = strip_start_marker(text)
        if i < len(parts) - 1:
            text = strip_end_marker(text)
        if text.strip():
            texts.append(text.strip())
    first = parts[0]
    views = [p.views for p in parts if p.views is not None]
    forwards = [p.forwards for p in parts if p.forwards is not None]
    edits = [p.edit_date for p in parts if p.edit_date is not None]
    hashtags: List[str] = []
    for part in parts:
        hashtags += [tag for tag in part.hashtags if tag not in hashtags]
    return replace(
        first,
        text="\n\n".join(texts),
        media=[item for part in parts for item in part.media],
        views=max(views) if views else None,
        forwards=sum(forwards) if forwards else None,
        edit_date=max(edits) if edits else None,
        hashtags=hashtags,
        grouped_id=None,
        parts=list(parts),
    )


def group_parts(posts: Iterable[ChannelPost], max_gap: timedelta = DEFAULT_MAX_GAP) -> Iterator[ChannelPost]:
    """Yield posts oldest-first, with each chain of continued posts merged into one."""
    chain: List[ChannelPost] = []
    for post in posts:
        if chain and is_continuation(chain[-1], post, max_gap):
            chain.append(post)
            continue
        if chain:
            yield chain[0] if len(chain) == 1 else merge_posts(chain)
        chain = [post]
    if chain:
        yield chain[0] if len(chain) == 1 else merge_posts(chain)
