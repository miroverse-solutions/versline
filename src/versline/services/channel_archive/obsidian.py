from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import jdatetime

from versline.services.channel_archive.models import ChannelInfo, ChannelPost, PostRecord
from versline.utils.common import format_duration, sanitize_filename

# Headings used in generated notes; change them here only.
LABELS = {
    "caption": "توضیحات",
    "summary": "خلاصه",
    "transcript": "متن پیاده‌شده",
    "taqrir": "تقریر و صورت‌بندی",
    "attachments": "پیوست‌ها",
    "source": "پست اصلی",
    "untitled": "پست",
    "date": "تاریخ",
    "post": "پست",
    "type": "نوع",
    "duration": "مدت",
}

_HASHTAG_RE = re.compile(r"(?<!\w)#([^\s#.,;:!?؟،؛()\[\]{}\"'«»]+)", re.UNICODE)
_URL_RE = re.compile(r"https?://\S+")
_UNSAFE_LINK_CHARS = re.compile(r"[#^\[\]|]")
_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_TITLE_MAX = 80


# ---------- text helpers ----------

def normalize_tag(raw: str) -> str:
    """Make a hashtag valid for Obsidian: ZWNJ/space -> '_', and only letters, digits, '_', '-', '/' are kept."""
    tag = re.sub(r"[\u200c\u200d\s]+", "_", raw)
    tag = re.sub(r"[^\w/-]", "", tag)
    return tag.strip("_")


def extract_hashtags(text: str) -> List[str]:
    seen: List[str] = []
    for match in _HASHTAG_RE.finditer(text or ""):
        tag = normalize_tag(match.group(1))
        if tag and not tag.isdigit() and tag not in seen:
            seen.append(tag)
    return seen


_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)\s]*\)")


def make_title(post: ChannelPost) -> str:
    for line in (post.text or "").splitlines():
        line = _MD_LINK_RE.sub(lambda m: m.group(1) if re.search(r"\w", m.group(1)) else "", line)
        cleaned = _URL_RE.sub("", _HASHTAG_RE.sub("", line))
        cleaned = re.sub(r"[*_`>~]+", "", cleaned)
        cleaned = " ".join(cleaned.split()).strip(" -–—:|")
        if cleaned:
            if len(cleaned) > _TITLE_MAX:
                cleaned = cleaned[:_TITLE_MAX].rsplit(" ", 1)[0].rstrip() + "…"
            return cleaned
    return f"{LABELS['untitled']} {post.id}"


def note_stem(post: ChannelPost, title: str, tz: Optional[Any] = None) -> str:
    local = post.date.astimezone(tz) if tz else post.date.astimezone()
    safe_title = _UNSAFE_LINK_CHARS.sub("", sanitize_filename(title)).strip(" .")
    stem = f"{local:%Y-%m-%d} - {post.id}"
    return f"{stem} - {safe_title}" if safe_title else stem


def to_shamsi(dt: datetime) -> str:
    return jdatetime.date.fromgregorian(date=dt.date()).isoformat()


# ---------- date arguments ----------

def parse_date_arg(value: str, *, end: bool = False) -> datetime:
    """Parse YYYY-MM-DD[ HH:MM] (Gregorian, or Shamsi when year < 1700) as an aware local datetime.

    A date without a time is the start of that day, or the last instant of it when end=True.
    """
    raw = value.strip().translate(_PERSIAN_DIGITS).replace("/", "-").replace("T", " ")
    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?", raw)
    if not match:
        raise ValueError(f"Invalid date '{value}'. Use YYYY-MM-DD (optionally HH:MM), Gregorian or Shamsi.")
    year, month, day = (int(g) for g in match.groups()[:3])
    try:
        if year < 1700:
            day_date: date = jdatetime.date(year, month, day).togregorian()
        else:
            day_date = date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"Invalid date '{value}': {exc}") from exc

    if match.group(4) is not None:
        local = datetime.combine(day_date, time(int(match.group(4)), int(match.group(5))))
        if end:
            local += timedelta(seconds=59, microseconds=999999)
    elif end:
        local = datetime.combine(day_date, time.max)
    else:
        local = datetime.combine(day_date, time.min)
    return local.astimezone()


# ---------- frontmatter ----------

def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return json.dumps(str(value), ensure_ascii=False)  # valid YAML double-quoted string


def render_frontmatter(data: Dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            lines.append(f"{key}: [{', '.join(_yaml_scalar(v) for v in value)}]")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


# ---------- notes ----------

def render_note(record: PostRecord, title: str) -> str:
    parts = [render_frontmatter(record.frontmatter), "", f"# {title}", ""]
    for key, body in record.sections.items():
        if not body or not body.strip():
            continue
        parts += [f"## {LABELS.get(key, key)}", "", body.strip(), ""]
    if record.attachments:
        parts += [f"## {LABELS['attachments']}", ""]
        parts += [f"![[{path}]]" for path in record.attachments]
        parts.append("")
    if record.post.url:
        parts += ["---", f"[{LABELS['source']}]({record.post.url})", ""]
    return "\n".join(parts)


def read_note_transcript(path: Path) -> Optional[Tuple[str, Optional[str]]]:
    """(transcript, transcription model) stored in a note we wrote earlier, or None when it has no transcript."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    heading = f"\n## {LABELS['transcript']}\n"
    start = text.find(heading)
    if start < 0:
        return None
    body = text[start + len(heading):]
    end = re.search(rf"\n## |\n---\n\[{re.escape(LABELS['source'])}\]", body)
    body = (body[: end.start()] if end else body).strip()
    if not body:
        return None
    model = re.search(r'^transcription_model: "(.*)"$', text, re.MULTILINE)
    return body, model.group(1) if model else None


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_index(
    channel: ChannelInfo,
    entries: Iterable[dict],
    range_from: Optional[str],
    range_to: Optional[str],
) -> str:
    """Index note built from manifest entries (done posts only), oldest first."""
    done = sorted((e for e in entries if e.get("status") == "done"), key=lambda e: e.get("date", ""))
    frontmatter = {
        "title": channel.title,
        "source": "telegram",
        "channel": f"@{channel.username}" if channel.username else channel.ref,
        "type": "channel-index",
        "post_count": len(done),
        "range_from": range_from,
        "range_to": range_to,
        "updated": datetime.now().astimezone(),
    }
    lines = [render_frontmatter(frontmatter), "", f"# {channel.title}", ""]
    lines.append(f"| {LABELS['date']} | {LABELS['post']} | {LABELS['type']} | {LABELS['duration']} |")
    lines.append("| --- | --- | --- | --- |")
    for entry in done:
        stem = Path(entry["note"]).with_suffix("").as_posix()
        link = f"[[{stem}\\|{_cell(entry.get('title') or stem)}]]"
        duration = format_duration(entry["duration"]) if entry.get("duration") else ""
        lines.append(f"| {entry.get('date', '')[:10]} | {link} | {entry.get('media_type', '')} | {duration} |")
    lines.append("")
    return "\n".join(lines)
