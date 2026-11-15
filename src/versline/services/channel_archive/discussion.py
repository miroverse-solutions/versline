"""Taqrir of a chat's discussions over a date range (``versline telegram taqrir``).

Messages are fetched from the source, their media turned into text (voice/video transcripts, document text,
image text), and the resulting message log is written up by the LLM as one taqrir note for the whole range:
a descriptive exposition, a list of claims with their evidence, or both. Long logs go through map/reduce:
style-neutral notes per part (cached), then each style is written from the notes.

Everything expensive is cached in ``<out>/.versline-taqrir.json`` so an interrupted run resumes and a rerun with a
different style only repeats the final write-up.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import jdatetime
from loguru import logger

from versline.config import settings
from versline.core.prompts import load_prompt
from versline.services.channel_archive import obsidian
from versline.services.channel_archive.models import ChannelInfo, ChannelPost, MediaItem, TRANSCRIBABLE_KINDS
from versline.services.channel_archive.sources.base import ChannelSource
from versline.services.channel_archive.steps import StepContext, _language_instruction, transcribe_media
from versline.utils.common import sanitize_filename

STYLES = ("descriptive", "claims", "both")
CACHE_NAME = ".versline-taqrir.json"
CACHE_VERSION = 1

SECTION_LABELS = {
    "descriptive": "تقریر",
    "claims": "ادعاها و ادله",
    "sources": "منابع",
    "log": "متن کامل گفتگو",
}
KIND_LABELS = {
    "voice": "پیام صوتی",
    "audio": "فایل صوتی",
    "video": "ویدیو",
    "video_note": "ویدیوی کوتاه",
    "document": "سند",
    "photo": "تصویر",
}
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
TEXT_DOC_EXTS = {".txt", ".md", ".markdown", ".csv", ".json", ".srt", ".vtt", ".xml", ".yaml", ".yml"}
_CITE_RE = re.compile(r"\[(#\d+(?:\s*[,،]\s*#?\d+)*)\](?!\()")
_PREAMBLE_RE = re.compile(r"^\s*(بله|حتماً|حتما|البته|باشه|چشم|Sure|Certainly|Here is|Here's)[^\n]{0,200}:\s*\n+", re.IGNORECASE)


@dataclass
class DiscussionOptions:
    out_dir: Optional[Path] = None  # default: output/<chat>/taqrir
    temp_dir: Path = Path("temp") / "telegram"
    since: Optional[datetime] = None
    until: Optional[datetime] = None
    limit: Optional[int] = None
    types: Optional[Set[str]] = None
    style: str = "both"
    attribute: bool = False  # name the participants (default: anonymous labels)
    transcribe: bool = True
    documents: bool = True
    images: bool = True
    doc_chars: int = 30000  # per document, after extraction
    max_chars: int = 150000  # longer logs go through map/reduce
    force: bool = False
    dry_run: bool = False
    write_log: bool = True
    instruction: Optional[str] = None  # extra guidance for the taqrir prompts


@dataclass
class LogEntry:
    """One message of the log: its own text plus the text extracted from its media."""

    post: ChannelPost
    speaker: str = ""
    parts: List[Dict[str, str]] = field(default_factory=list)  # {kind, file_name, text}

    @property
    def id(self) -> int:
        return self.post.id


@dataclass
class DiscussionResult:
    channel: ChannelInfo
    out_dir: Path
    entries: List[LogEntry] = field(default_factory=list)
    note_path: Optional[Path] = None
    log_path: Optional[Path] = None
    counts: Dict[str, int] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    llm_calls: int = 0
    cached_notes: int = 0
    metadata: Dict[str, object] = field(default_factory=dict)


# ---------- helpers ----------

def fa_digits(value: object) -> str:
    return str(value).translate(_FA_DIGITS)


def shamsi_datetime(dt: datetime) -> str:
    local = dt.astimezone()
    return jdatetime.datetime.fromgregorian(datetime=local.replace(tzinfo=None)).strftime("%Y-%m-%d %H:%M")


def read_document(path: Path) -> str:
    """Text of a document: plain-text files decoded directly, everything else through MarkItDown."""
    if path.suffix.lower() in TEXT_DOC_EXTS:
        raw = path.read_bytes()
        for encoding in ("utf-8", "utf-8-sig", "cp1256", "cp1252"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("latin-1")
    from versline.services.document_processor import convert_to_markdown

    return convert_to_markdown(str(path)) or ""


def truncate(text: str, limit: int) -> str:
    text = text.strip()
    if limit and len(text) > limit:
        return text[:limit].rsplit("\n", 1)[0].rstrip() + "\n[… بقیه متن حذف شد]"
    return text


def strip_chatter(text: str) -> str:
    return _PREAMBLE_RE.sub("", text.strip(), count=1).strip()


def _hash(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()[:24]


class TaqrirCache:
    """Extracted media text (by message and media index) and map-step notes (by prompt hash)."""

    def __init__(self, path: Path, enabled: bool = True):
        self.path = path
        self.data: Dict[str, Dict] = {"version": CACHE_VERSION, "media": {}, "notes": {}}
        if enabled and path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if loaded.get("version") == CACHE_VERSION:
                    self.data["media"] = loaded.get("media", {})
                    self.data["notes"] = loaded.get("notes", {})
            except (OSError, ValueError):
                logger.warning(f"Ignoring unreadable cache {path}")

    def media(self, post_id: int, index: int) -> Optional[str]:
        return self.data["media"].get(f"{post_id}:{index}", {}).get("text")

    def put_media(self, post_id: int, index: int, item: MediaItem, text: str) -> None:
        self.data["media"][f"{post_id}:{index}"] = {
            "kind": item.kind, "file_name": item.file_name, "text": text, "model": settings.llm.model,
        }
        self.save()

    def notes(self, key: str) -> Optional[str]:
        return self.data["notes"].get(key)

    def put_notes(self, key: str, text: str) -> None:
        self.data["notes"][key] = text
        self.save()

    def save(self) -> None:
        obsidian.write_text_atomic(self.path, json.dumps(self.data, ensure_ascii=False, indent=1))


# ---------- the log ----------

def assign_speakers(entries: List[LogEntry], attribute: bool) -> List[str]:
    """Set each entry's speaker; returns the participants in order of appearance."""
    labels: Dict[str, str] = {}
    for entry in entries:
        post = entry.post
        key = str(post.sender_id) if post.sender_id is not None else (post.sender_name or "")
        if key not in labels:
            if attribute:
                labels[key] = post.sender_name or (f"کاربر {post.sender_id}" if post.sender_id is not None else "ناشناس")
            else:
                labels[key] = f"شرکت‌کننده {fa_digits(len(labels) + 1)}"
        entry.speaker = labels[key]
    return list(dict.fromkeys(labels.values()))


def _block_id(post_id: int) -> str:
    return f"m{post_id}"


def _part_label(part: Dict[str, str]) -> str:
    label = KIND_LABELS.get(part["kind"], part["kind"])
    if part.get("file_name") and part["kind"] in ("document", "audio"):
        label += f": {part['file_name']}"
    return label


_HEADING_UNSAFE = re.compile(r"[#^\[\]|*_`]")


def render_entry(entry: LogEntry, for_note: bool = False, known_ids: Optional[Set[int]] = None) -> str:
    """One message: `[#id | date | speaker | in reply to #x]` + text + media text (for the LLM), or for the log
    note a `### id · date · speaker` heading, a line with reply/forward/link ending in the ^m<id> anchor that
    citations point to, the text, and long extracted text in collapsed callouts."""
    post = entry.post
    if not for_note:
        extra = []
        if post.reply_to:
            extra.append(f"در پاسخ به #{post.reply_to}")
        if post.forwarded_from:
            extra.append(f"بازنشر از {post.forwarded_from}")
        lines = ["[" + " | ".join([f"#{post.id}", shamsi_datetime(post.date), entry.speaker] + extra) + "]"]
        if post.text.strip():
            lines.append(post.text.strip())
        for part in entry.parts:
            lines.append(f"({_part_label(part)})")
            if part.get("text"):
                lines.append(part["text"].strip())
        return "\n".join(lines)

    speaker = _HEADING_UNSAFE.sub("", entry.speaker).strip()
    when = shamsi_datetime(post.date)
    heading = f"### {post.id} · {when[11:]} · {speaker}"  # the day is the ## heading above
    meta = [when]
    if post.reply_to:
        target = f"[[#^{_block_id(post.reply_to)}|#{post.reply_to}]]" if known_ids and post.reply_to in known_ids else f"#{post.reply_to}"
        meta.append(f"در پاسخ به {target}")
    if post.forwarded_from:
        meta.append(f"بازنشر از {post.forwarded_from}")
    if post.url:
        meta.append(f"[پیام در تلگرام]({post.url})")
    # Obsidian block ids can't sit on a heading, so the anchor goes on the line under it.
    blocks = [heading, f"{' · '.join(meta)} ^{_block_id(post.id)}"]
    if post.text.strip():
        blocks.append(post.text.strip())
    for part in entry.parts:
        text = (part.get("text") or "").strip()
        if part["kind"] in TRANSCRIBABLE_KINDS and text:
            blocks.append(f"*({_part_label(part)})*\n{text}")
        elif text:
            quoted = "\n".join(f"> {line}" if line.strip() else ">" for line in text.splitlines())
            blocks.append(f"> [!quote]- {_part_label(part)}\n{quoted}")
        else:
            blocks.append(f"*({_part_label(part)})*")
    return "\n\n".join(blocks)


def render_log(entries: List[LogEntry], for_note: bool = False) -> List[Tuple[str, List[str]]]:
    """[(Shamsi day, [rendered messages])] in chronological order."""
    days: List[Tuple[str, List[str]]] = []
    known_ids = {entry.id for entry in entries}
    for entry in entries:
        day = shamsi_datetime(entry.post.date)[:10]
        if not days or days[-1][0] != day:
            days.append((day, []))
        days[-1][1].append(render_entry(entry, for_note, known_ids))
    return days


def log_text(days: List[Tuple[str, List[str]]], heading: str = "==") -> str:
    out: List[str] = []
    for day, blocks in days:
        out.append(f"{heading} {day} {heading}" if heading == "==" else f"{heading} {day}")
        out += blocks
    return "\n\n".join(out)


def split_log(days: List[Tuple[str, List[str]]], max_chars: int) -> List[str]:
    """Pieces of at most ~max_chars, cut between days where possible, else between messages."""
    chunks: List[str] = []
    current: List[Tuple[str, List[str]]] = []
    size = 0

    def flush():
        nonlocal current, size
        if current:
            chunks.append(log_text(current))
        current, size = [], 0

    for day, blocks in days:
        day_size = sum(len(b) + 2 for b in blocks) + len(day) + 8
        if size + day_size <= max_chars:
            current.append((day, blocks))
            size += day_size
            continue
        flush()
        if day_size <= max_chars:
            current, size = [(day, blocks)], day_size
            continue
        for block in blocks:  # one day longer than a piece: cut between its messages
            if size and size + len(block) + 2 > max_chars:
                flush()
            if not current or current[-1][0] != day:
                current.append((day, []))
            current[-1][1].append(block)
            size += len(block) + 2
    flush()
    return chunks


def link_citations(text: str, urls: Dict[int, Optional[str]], log_stem: Optional[str]) -> str:
    """[#12] / [#12, #15] -> links to the messages (t.me when the chat has links, else the log note's block)."""

    def one(raw: str) -> str:
        pid = int(raw.lstrip("#"))
        if urls.get(pid):
            return f"[#{pid}]({urls[pid]})"
        if log_stem and pid in urls:
            return f"[[{log_stem}#^{_block_id(pid)}|#{pid}]]"
        return f"#{pid}"

    def repl(match: re.Match) -> str:
        ids = re.split(r"\s*[,،]\s*", match.group(1))
        return "(" + "، ".join(one(i) for i in ids) + ")"

    return _CITE_RE.sub(repl, text)


# ---------- builder ----------

class DiscussionBuilder:
    def __init__(self, source: ChannelSource, ctx: StepContext, options: DiscussionOptions, text_llm=None):
        if options.style not in STYLES:
            raise ValueError(f"Unknown style '{options.style}'. Choose from: {', '.join(STYLES)}")
        self.source = source
        self.ctx = ctx
        self.options = options
        self.text_llm = text_llm
        self.result: Optional[DiscussionResult] = None

    # -- fetch --

    def _wanted(self, post: ChannelPost) -> bool:
        return self.options.types is None or post.media_type in self.options.types

    def _fetch(self, channel: ChannelInfo) -> List[LogEntry]:
        entries: List[LogEntry] = []
        for post in self.source.iter_posts(channel, since=self.options.since, until=self.options.until):
            if not self._wanted(post):
                continue
            entries.append(LogEntry(post=post))
            self.ctx.progress(f"Reading messages… {len(entries)}")
            if self.options.limit and len(entries) >= self.options.limit:
                break
        return entries

    # -- media -> text --

    def _enabled(self, item: MediaItem) -> bool:
        if item.kind in TRANSCRIBABLE_KINDS:
            return self.options.transcribe and self.ctx.transcriber is not None
        if item.kind == "document":
            return self.options.documents
        if item.kind == "photo":
            return self.options.images and self.text_llm is not None
        return False

    def _extract_item(self, post: ChannelPost, index: int, item: MediaItem, temp_files: List[Path]) -> str:
        stem = sanitize_filename(f"{self.ctx.channel.slug}_{post.id}_{index + 1}")
        self.ctx.progress(f"Downloading {item.kind} of message {post.id}…")
        path = self.source.download(post, item, self.ctx.temp_dir, stem)
        temp_files.append(path)
        if item.kind in TRANSCRIBABLE_KINDS:
            return transcribe_media(self.ctx, post, item, path, temp_files)
        if item.kind == "document":
            self.ctx.progress(f"Reading document of message {post.id}…")
            return truncate(read_document(path), self.options.doc_chars)
        self.ctx.progress(f"Reading image of message {post.id}…")
        return strip_chatter(self.text_llm.generate_with_image(load_prompt("telegram_image_read_prompt.md"), path))

    def _extract(self, entry: LogEntry, cache: TaqrirCache, result: DiscussionResult) -> None:
        post = entry.post
        for index, item in enumerate(post.media):
            part = {"kind": item.kind, "file_name": item.file_name or "", "text": ""}
            entry.parts.append(part)
            if not self._enabled(item):
                continue
            cached = cache.media(post.id, index)
            if cached is not None:
                part["text"] = cached
                result.counts[item.kind] = result.counts.get(item.kind, 0) + 1
                continue
            if not item.downloadable:
                part["text"] = "[قابل دریافت نبود]"
                continue
            if self.ctx.max_size_mb and item.size and item.size > self.ctx.max_size_mb * 1024 * 1024:
                part["text"] = "[بزرگ‌تر از حد مجاز؛ خوانده نشد]"
                continue
            temp_files: List[Path] = []
            try:
                text = self._extract_item(post, index, item, temp_files)
            except Exception as exc:  # one unreadable file must not sink the whole taqrir
                logger.warning(f"Message {post.id}: could not read {item.kind}: {exc}")
                result.errors.append(f"#{post.id} {item.kind}{' ' + item.file_name if item.file_name else ''}: {exc}")
                part["text"] = "[خوانده نشد]"
                continue
            finally:
                for path in temp_files:
                    try:
                        path.unlink()
                    except OSError:
                        pass
            part["text"] = text
            cache.put_media(post.id, index, item, text)
            result.counts[item.kind] = result.counts.get(item.kind, 0) + 1

    # -- LLM --

    def _date_range(self, entries: List[LogEntry]) -> Tuple[datetime, datetime]:
        start = self.options.since or entries[0].post.date
        end = self.options.until or entries[-1].post.date
        return start, end

    def _prompt_vars(self, channel: ChannelInfo, date_range: str) -> Dict[str, str]:
        if self.options.attribute:
            attribution = ("Refer to participants by the names given in the message headers when stating who said "
                           "what.")
        else:
            attribution = ("Do not use real names of participants, even if they appear in the messages; refer to them "
                           "only by the labels in the message headers (e.g. «شرکت‌کننده ۱») or impersonally "
                           "(«یکی از حاضران», «در پاسخ گفته شد»).")
        instruction = f"* Additional instruction from the user: {self.options.instruction.strip()}" if (
            self.options.instruction and self.options.instruction.strip()) else ""
        return {
            "chat_title": channel.title,
            "date_range": date_range,
            "attribution_instruction": attribution,
            "language_instruction": _language_instruction(self.ctx),
            "instruction": instruction,
        }

    def _generate(self, prompt: str, result: DiscussionResult) -> str:
        result.llm_calls += 1
        return strip_chatter(self.text_llm.generate(prompt))

    def _write_styles(self, log: str, days, channel: ChannelInfo, date_range: str, cache: TaqrirCache,
                      result: DiscussionResult) -> Dict[str, str]:
        variables = self._prompt_vars(channel, date_range)
        if len(log) <= self.options.max_chars:
            source_text, input_kind = log, "the full message log"
        else:
            pieces = split_log(days, self.options.max_chars)
            notes: List[str] = []
            for i, piece in enumerate(pieces, 1):
                prompt = load_prompt("telegram_taqrir_notes_prompt.md").format(
                    text=piece, part=i, parts=len(pieces), **variables)
                key = _hash(prompt, settings.llm.provider or "", settings.llm.model or "")
                cached = None if self.options.force else cache.notes(key)
                if cached is not None:
                    result.cached_notes += 1
                    notes.append(cached)
                    continue
                self.ctx.progress(f"Taking notes on part {i}/{len(pieces)}…")
                text = self._generate(prompt, result)
                cache.put_notes(key, text)
                notes.append(text)
            source_text = "\n\n".join(f"--- part {i} ---\n\n{n}" for i, n in enumerate(notes, 1))
            input_kind = (f"structured notes taken, in order, from the {len(pieces)} consecutive parts of the message "
                          "log (the same topic may continue across parts; merge it)")
        styles = ["descriptive", "claims"] if self.options.style == "both" else [self.options.style]
        sections: Dict[str, str] = {}
        for style in styles:
            self.ctx.progress(f"Writing the {style} taqrir…")
            prompt = load_prompt(f"telegram_taqrir_{style}_prompt.md").format(
                text=source_text, input_kind=input_kind, **variables)
            sections[style] = self._generate(prompt, result)
        return sections

    # -- output --

    def _stems(self, start: datetime, end: datetime) -> Tuple[str, str]:
        base = f"{start.astimezone():%Y-%m-%d} تا {end.astimezone():%Y-%m-%d}"
        return f"{base} - تقریر", f"{base} - {SECTION_LABELS['log']}"

    def _sources_section(self, entries: List[LogEntry], urls, log_stem) -> str:
        lines = []
        for entry in entries:
            for part in entry.parts:
                if part["kind"] not in ("document", "audio") or not part.get("file_name"):
                    continue
                ref = link_citations(f"[#{entry.id}]", urls, log_stem)
                lines.append(f"- {part['file_name']} {ref}")
        return "\n".join(lines)

    def run(self, ref: str) -> DiscussionResult:
        channel = self.source.resolve(ref)
        self.ctx.channel = channel
        out_dir = Path(self.options.out_dir) if self.options.out_dir else Path(settings.output_directory) / channel.slug / "taqrir"
        self.ctx.out_dir = out_dir
        result = DiscussionResult(channel=channel, out_dir=out_dir)
        self.result = result
        entries = self._fetch(channel)
        result.entries = entries
        participants = assign_speakers(entries, attribute=True if self.options.dry_run else self.options.attribute)
        if self.options.dry_run or not entries:
            return result

        cache = TaqrirCache(out_dir / CACHE_NAME, enabled=not self.options.force)
        self.ctx.temp_dir.mkdir(parents=True, exist_ok=True)
        for n, entry in enumerate(entries, 1):
            self.ctx.progress(f"Message {n}/{len(entries)}")
            self._extract(entry, cache, result)

        start, end = self._date_range(entries)
        date_range = f"{obsidian.to_shamsi(start.astimezone())} تا {obsidian.to_shamsi(end.astimezone())}"
        llm_days = render_log(entries)
        log = log_text(llm_days)
        sections = self._write_styles(log, llm_days, channel, date_range, cache, result) if self.text_llm else {}

        note_stem, log_stem = self._stems(start, end)
        urls = {e.id: e.post.url for e in entries}
        link_stem = log_stem if self.options.write_log else None
        title = f"تقریر مباحث {channel.title} ({fa_digits(date_range)})"
        meta = {
            "title": title,
            "source": "telegram",
            "type": "chat-taqrir",
            "chat": f"@{channel.username}" if channel.username else channel.ref,
            "chat_title": channel.title,
            "chat_type": channel.kind,
            "since": start.astimezone(),
            "until": end.astimezone(),
            "since_shamsi": obsidian.to_shamsi(start.astimezone()),
            "until_shamsi": obsidian.to_shamsi(end.astimezone()),
            "messages": len(entries),
            "participant_count": len(participants),
            "participants": participants if self.options.attribute else None,
            "voices": sum(result.counts.get(k, 0) for k in TRANSCRIBABLE_KINDS) or None,
            "documents": result.counts.get("document") or None,
            "images": result.counts.get("photo") or None,
            "style": self.options.style,
            "taqrir_model": settings.llm.model if sections else None,
            "generated_at": datetime.now().astimezone(),
            "tags": ["telegram", "taqrir"],
        }
        result.metadata = meta

        body = [obsidian.render_frontmatter(meta), "", f"# {title}", ""]
        for style in ("descriptive", "claims"):
            if sections.get(style):
                body += [f"## {SECTION_LABELS[style]}", "", link_citations(sections[style], urls, link_stem), ""]
        sources = self._sources_section(entries, urls, link_stem)
        if sources:
            body += [f"## {SECTION_LABELS['sources']}", "", sources, ""]
        if link_stem:
            body += ["---", f"[[{log_stem}|{SECTION_LABELS['log']}]]", ""]
        result.note_path = out_dir / f"{note_stem}.md"
        obsidian.write_text_atomic(result.note_path, "\n".join(body))

        if self.options.write_log:
            log_meta = {
                "title": f"{SECTION_LABELS['log']}: {channel.title}",
                "source": "telegram",
                "type": "chat-log",
                "chat": meta["chat"],
                "chat_title": channel.title,
                "since_shamsi": meta["since_shamsi"],
                "until_shamsi": meta["until_shamsi"],
                "messages": len(entries),
                "tags": ["telegram"],
            }
            log_body = [obsidian.render_frontmatter(log_meta), "", f"# {log_meta['title']}", "",
                        f"[[{note_stem}|{SECTION_LABELS['descriptive']}]]", "",
                        log_text(render_log(entries, for_note=True), heading="##"), ""]
            result.log_path = out_dir / f"{log_stem}.md"
            obsidian.write_text_atomic(result.log_path, "\n".join(log_body))
        return result
