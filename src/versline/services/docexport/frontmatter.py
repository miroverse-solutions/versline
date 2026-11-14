"""Tiny YAML front-matter reader and a metadata table renderer (standard library only).

The reader understands what ``channel_archive.obsidian.render_frontmatter`` writes: ``key: value`` lines
whose values are JSON-compatible scalars (double-quoted strings, numbers, booleans) or flow lists.
"""
import json
import re
from typing import Any, Dict, Tuple

_FM_RE = re.compile(r"\A\ufeff?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.DOTALL)
_KEY_RE = re.compile(r"^([^\s:#][^:\n]*?):(?:[ \t]+(.*)|[ \t]*)$")

FA_LABELS = {
    "title": "عنوان", "source": "منبع", "channel": "کانال", "channel_title": "عنوان کانال",
    "post_id": "شناسه پست", "url": "پیوند", "date": "تاریخ", "date_shamsi": "تاریخ شمسی",
    "media_type": "نوع رسانه", "duration": "مدت", "file_name": "نام فایل", "views": "بازدید",
    "forwards": "بازنشر", "forwarded_from": "بازنشر از", "album_size": "تعداد رسانه",
    "tags": "برچسب‌ها", "archived_at": "زمان آرشیو", "transcribed": "پیاده‌سازی شده",
    "transcription_model": "مدل پیاده‌سازی", "summary_model": "مدل خلاصه", "taqrir_model": "مدل تقریر",
    "model": "مدل", "provider": "ارائه‌دهنده", "language": "زبان", "target_language": "زبان مقصد",
    "mode": "حالت", "section": "بخش", "stage": "مرحله", "type": "نوع", "count": "تعداد",
    "generated_at": "تاریخ تولید", "workspace": "پوشه کاری", "post_count": "تعداد پست‌ها",
    "range_from": "از", "range_to": "تا", "updated": "به‌روزرسانی", "didactic": "آموزشی",
    "compression": "درصد فشرده‌سازی",
}
HIDDEN_KEYS = {"aliases", "post_ids", "part_urls", "skipped_media", "merged_into"}
_DURATION_KEYS = {"duration"}


def _parse_value(raw: str) -> Any:
    raw = raw.strip()
    if not raw:
        return ""
    try:
        return json.loads(raw)
    except ValueError:
        pass
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1].replace("''", "'")
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        return [_parse_value(p) for p in inner.split(",")] if inner else []
    return raw


def split_front_matter(text: str) -> Tuple[Dict[str, Any], str]:
    """Return ``(metadata, body)``. Text without a real ``key:`` front-matter block is returned unchanged."""
    match = _FM_RE.match(text)
    if not match:
        return {}, text
    meta: Dict[str, Any] = {}
    for line in match.group(1).splitlines():
        km = _KEY_RE.match(line)
        if km:
            meta[km.group(1).strip()] = _parse_value(km.group(2) or "")
    if not meta:
        return {}, text
    return meta, text[match.end():]


def _fmt_duration(value: Any) -> str:
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return str(value)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def _cell(key: str, value: Any) -> str:
    if isinstance(value, bool):
        return "بله" if value else "خیر"
    if isinstance(value, (list, tuple)):
        value = "، ".join(str(v) for v in value)
    elif key in _DURATION_KEYS:
        value = _fmt_duration(value)
    text = str(value).replace("|", "\\|").replace("\n", " ").strip()
    if re.match(r"https?://\S+$", text):
        return f"[{text}]({text})"
    return text


def visible_items(meta: Dict[str, Any]):
    for key, value in meta.items():
        if key in HIDDEN_KEYS or value is None or value == "" or value == []:
            continue
        if key == "tags" and isinstance(value, list) and set(value) <= {"telegram"}:
            continue
        yield key, value


def metadata_table(meta: Dict[str, Any], labels: Dict[str, str] = FA_LABELS) -> str:
    """Render metadata as a two-column Markdown table ('' when there is nothing to show)."""
    rows = [f"| {labels.get(k, k)} | {_cell(k, v)} |" for k, v in visible_items(meta)]
    if not rows:
        return ""
    return "\n".join(["| مشخصه | مقدار |", "| --- | --- |", *rows])
