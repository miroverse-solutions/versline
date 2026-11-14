"""Turn a finished channel archive into a tidy, shareable pack: book + per-post Word/PDF, catalog, notes, README, ZIP.

Works offline from the archive folder (``.versline-channel.json`` + the post notes); nothing is re-downloaded.
"""
from __future__ import annotations

import csv
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import jdatetime
from loguru import logger

from versline.services.channel_archive import obsidian
from versline.services.channel_archive.models import ChannelInfo
from versline.services.channel_archive.state import MANIFEST_NAME, ChannelState
from versline.services.docexport import (
    ExportItem, ExportOptions, ExportResult, PAGE_BREAK, metadata_table, split_front_matter,
)
from versline.utils.common import format_duration, sanitize_filename

MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
_PERSIAN = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_EMBED_RE = re.compile(r"!\[\[([^\]\|\n]+)")
_HEADING_RE = re.compile(r"^(#{1,6})([ \t].*)$")
_BOOK_META_KEYS = ("date_shamsi", "media_type", "duration", "views", "url")
CATALOG_COLUMNS = [
    ("post_ids", "شناسه پست"), ("date", "تاریخ"), ("date_shamsi", "تاریخ شمسی"), ("title", "عنوان"),
    ("type", "نوع"), ("duration", "مدت"), ("views", "بازدید"), ("forwards", "بازنشر"), ("url", "پیوند"),
    ("note", "یادداشت"), ("docx", "Word"), ("pdf", "PDF"), ("attachments", "پیوست‌ها"),
]


@dataclass
class PackOptions:
    formats: Tuple[str, ...] = ("docx", "pdf")
    front_matter: bool = True
    per_post: bool = True
    media: bool = True
    make_zip: bool = True
    toc: bool = True  # table of contents in the book
    since: Optional[datetime] = None
    until: Optional[datetime] = None
    force: bool = False
    out_dir: Optional[Path] = None  # parent folder of the pack (default: <archive>/../<slug>_pack)
    page_format: str = "A4"
    margin: str = "15mm"
    font_size: int = 12


@dataclass
class PackPost:
    entry: dict
    note: Path  # absolute path to the note in the archive
    meta: Dict[str, Any]
    body: str
    date: datetime
    attachments: List[str] = field(default_factory=list)

    @property
    def stem(self) -> str:
        return self.note.stem

    @property
    def title(self) -> str:
        return self.entry.get("title") or self.meta.get("title") or self.stem


@dataclass
class PackResult:
    root: Path
    zip_path: Optional[Path]
    posts: int
    book_files: List[Path] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)


def _digits(text: str) -> str:
    return text.translate(_PERSIAN)


def collect_posts(archive_dir: Path, since: Optional[datetime] = None, until: Optional[datetime] = None) -> Tuple[ChannelInfo, List[PackPost]]:
    """Done, non-merged posts whose note exists, oldest first, inside the optional date window."""
    state = ChannelState(archive_dir)
    if not state.posts:
        raise FileNotFoundError(f"No Telegram archive found in {archive_dir} (missing {MANIFEST_NAME}).")
    ch = state.channel or {}
    title = ch.get("title") or archive_dir.name
    username = ch.get("username")
    info = ChannelInfo(ref=f"@{username}" if username else title, title=title, username=username, channel_id=ch.get("id"))
    posts: List[PackPost] = []
    for entry in state.posts.values():
        if entry.get("status") != "done" or entry.get("merged_into") or not entry.get("note"):
            continue
        note = archive_dir / entry["note"]
        if not note.is_file():
            logger.warning(f"Note missing, skipped: {note}")
            continue
        try:
            when = datetime.fromisoformat(entry["date"])
        except (KeyError, ValueError):
            continue
        if when.tzinfo is None:
            when = when.astimezone()
        if (since and when < since) or (until and when > until):
            continue
        meta, body = split_front_matter(note.read_text(encoding="utf-8"))
        attachments = list(dict.fromkeys(m.group(1).strip() for m in _EMBED_RE.finditer(body)))
        posts.append(PackPost(entry, note, meta, body, when, attachments))
    posts.sort(key=lambda p: (p.date, p.stem))
    return info, posts


def _export_options(opts: PackOptions, formats: Tuple[str, ...]) -> ExportOptions:
    return ExportOptions(formats=formats, front_matter=opts.front_matter, page_format=opts.page_format,
                         margin=opts.margin, font_size=opts.font_size, force=opts.force)


def export_posts(archive_dir: Path, posts: List[PackPost], dest_root: Path, opts: PackOptions,
                 extra: Optional[Dict[str, List[ExportItem]]] = None) -> List[ExportResult]:
    """Export every post into ``dest_root/<fmt>/<note stem>.<fmt>`` (resumable). ``extra`` adds items per format."""
    from versline.services.docexport import export_items

    results: List[ExportResult] = []
    for fmt in opts.formats:
        items = list((extra or {}).get(fmt, []))
        for post in posts:
            items.append(ExportItem(out_base=dest_root / fmt / post.stem, source=post.note, base_dir=archive_dir,
                                    title=post.title))
        results += export_items(items, _export_options(opts, (fmt,)))
    return results


# ---------- book ----------

def _demote(body: str, levels: int) -> str:
    out, fenced = [], False
    for line in body.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        m = None if fenced else _HEADING_RE.match(line)
        out.append(f"{'#' * min(6, len(m.group(1)) + levels)}{m.group(2)}" if m else line)
    return "\n".join(out)


def _strip_title(body: str) -> str:
    return re.sub(r"\A\s*#[ \t][^\n]*\n", "", body, count=1)


def _shamsi_month(when: datetime) -> Tuple[int, int]:
    j = jdatetime.date.fromgregorian(date=when.date())
    return j.year, j.month


def _same(a: str, b: str) -> bool:
    """Heading text equality that ignores punctuation (markdown-it's typographer rewrites quotes and dashes)."""
    return re.sub(r"[\W_]+", "", a) == re.sub(r"[\W_]+", "", b)


def _heading_ids(markdown: str) -> Optional[List[Tuple[str, str, str]]]:
    """(tag, label, id) of every heading, using MdPersia's own renderer so anchors match exactly. None if unavailable."""
    try:
        from fa_md_pdf.html_builder import build_markdown_renderer
    except ImportError:
        return None
    tokens = build_markdown_renderer().parse(markdown)
    found = []
    for i, token in enumerate(tokens[:-1]):
        if token.type == "heading_open":
            label = "".join(t.content for t in (tokens[i + 1].children or []) if t.type in {"text", "code_inline"})
            found.append((token.tag, label, token.attrGet("id") or ""))
    return found


def build_book_markdown(info: ChannelInfo, posts: List[PackPost], front_matter: bool, toc: bool = True) -> str:
    """Cover, optional clickable table of contents, then every post (a month chapter, each post on a new page)."""
    months: Dict[Tuple[int, int], List[PackPost]] = {}
    for post in posts:
        months.setdefault(_shamsi_month(post.date), []).append(post)
    month_label = {key: f"{MONTHS[key[1] - 1]} {_digits(str(key[0]))}" for key in months}

    head = [f"# {info.title}", ""]
    if toc:
        head += [PAGE_BREAK, "", "## فهرست مطالب", "", "@@TOC@@", ""]
    body: List[str] = []
    for key, group in months.items():
        body += [PAGE_BREAK, "", f"## {month_label[key]}", ""]
        for index, post in enumerate(group):
            if index:
                body += [PAGE_BREAK, ""]
            body += [f"### {post.title}", ""]
            if front_matter:
                table = metadata_table({k: post.meta[k] for k in _BOOK_META_KEYS if k in post.meta})
                if table:
                    body += [table, ""]
            body += [_demote(_strip_title(post.body).strip(), 2), ""]
    if not toc:
        return "\n".join(head + body)

    # Heading ids are generated in document order (with -1, -2 for duplicates), so read them back from the parse.
    ids = _heading_ids("\n".join(head + body).replace("@@TOC@@", ""))
    month_ids: Dict[Tuple[int, int], str] = {}
    post_ids: Dict[int, str] = {}
    if ids:
        queue: List[Tuple[str, str, Any]] = []
        for key, group in months.items():
            queue.append(("h2", month_label[key], key))
            queue += [("h3", p.title, id(p)) for p in group]
        # walk both sequences; skip headings that are not ours (e.g. a '#' inside a post body)
        wanted = iter(queue)
        current = next(wanted, None)
        for tag, label, anchor in (h for h in ids if h[0] in ("h2", "h3")):
            if current and tag == current[0] and _same(label, current[1]):
                (month_ids if tag == "h2" else post_ids)[current[2]] = anchor
                current = next(wanted, None)

    def link(text: str, anchor: Optional[str]) -> str:
        return f"[{text}](#{anchor})" if anchor else text

    toc_lines: List[str] = []
    number = 0
    for key, group in months.items():
        toc_lines += [f"**{link(month_label[key], month_ids.get(key))}**", ""]
        for post in group:
            number += 1
            shamsi = post.meta.get("date_shamsi") or jdatetime.date.fromgregorian(date=post.date.date()).isoformat()
            toc_lines.append(f"{_digits(str(number))}. {_digits(str(shamsi))} — {link(post.title, post_ids.get(id(post)))}")
        toc_lines.append("")
    return "\n".join(head + body).replace("@@TOC@@", "\n".join(toc_lines))


# ---------- catalog / README ----------

def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def write_catalog(root: Path, rows: List[Dict[str, Any]]) -> List[Path]:
    csv_path = root / "catalog.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([label for _, label in CATALOG_COLUMNS])
        for row in rows:
            writer.writerow([row.get(key, "") for key, _ in CATALOG_COLUMNS])
    written = [csv_path]
    try:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "catalog"
        ws.sheet_view.rightToLeft = True
        ws.append([label for _, label in CATALOG_COLUMNS])
        for row in rows:
            ws.append([row.get(key, "") for key, _ in CATALOG_COLUMNS])
        wb.save(root / "catalog.xlsx")
        written.append(root / "catalog.xlsx")
    except ImportError:
        logger.warning("openpyxl is not installed; catalog.xlsx skipped")
    return written


def build_readme(info: ChannelInfo, posts: List[PackPost], book_name: str, opts: PackOptions) -> str:
    first, last = posts[0].date, posts[-1].date
    total = sum(int(p.entry.get("duration") or 0) for p in posts)
    link = f"https://t.me/{info.username}" if info.username else ""
    lines = [f"# {info.title}", "", "بسته کامل آرشیو کانال تلگرام", ""]
    rows = {
        "کانال": f"@{info.username}" if info.username else info.title,
        "پیوند": link,
        "از تاریخ": f"{first.date().isoformat()} ({_digits(jdatetime.date.fromgregorian(date=first.date()).isoformat())})",
        "تا تاریخ": f"{last.date().isoformat()} ({_digits(jdatetime.date.fromgregorian(date=last.date()).isoformat())})",
        "تعداد پست‌ها": _digits(str(len(posts))),
        "مجموع مدت صوت/تصویر": format_duration(total) if total else "",
        "تاریخ تهیه بسته": datetime.now().date().isoformat(),
    }
    lines += ["| مشخصه | مقدار |", "| --- | --- |"] + [f"| {k} | {v} |" for k, v in rows.items() if v] + ["", "## محتوای بسته", ""]
    fmts = "/".join(f.upper() for f in opts.formats)
    lines.append(f"- **{book_name}.{'/'.join(opts.formats)}** — کتاب کامل ({fmts}): فهرست مطالب و همه پست‌ها به ترتیب تاریخ")
    if opts.per_post:
        lines.append("- **posts/** — هر پست در یک فایل جدا، پوشه‌بندی بر اساس قالب فایل")
    lines.append("- **notes/** — یادداشت‌های Markdown (قابل باز شدن در Obsidian) به‌همراه فهرست کانال" + (" و پیوست‌ها" if opts.media else ""))
    lines.append("- **catalog.csv / catalog.xlsx** — فهرست جدولی همه پست‌ها (تاریخ، عنوان، نوع، مدت، پیوند، فایل‌ها)")
    return "\n".join(lines) + "\n"


# ---------- main entry ----------

def _copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or dest.stat().st_size != src.stat().st_size or dest.stat().st_mtime < src.stat().st_mtime:
        shutil.copy2(src, dest)


def build_pack(archive_dir: Path, opts: PackOptions, log: Callable[[str], None] = lambda _m: None) -> PackResult:
    from versline.config import settings

    archive_dir = Path(archive_dir).resolve()
    info, posts = collect_posts(archive_dir, opts.since, opts.until)
    if not posts:
        raise ValueError("No archived posts match (check the date range and that the archive has finished posts).")

    slug = sanitize_filename(info.slug)
    span = f"{posts[0].date.date().isoformat()}_{posts[-1].date.date().isoformat()}"
    parent = Path(opts.out_dir) if opts.out_dir else Path(settings.output_directory) / f"{slug}_pack"
    root = parent / f"{slug}_{span}"
    root.mkdir(parents=True, exist_ok=True)
    book_name = sanitize_filename(info.title) or slug

    # notes/: a working Obsidian vault limited to the selected posts
    log("Copying notes…")
    notes_root = root / "notes"
    for post in posts:
        _copy(post.note, notes_root / post.entry["note"])
        if opts.media:
            for ref in post.attachments:
                source = archive_dir / ref
                if source.is_file():
                    _copy(source, notes_root / ref)
    entries = [p.entry for p in posts]
    index = obsidian.render_index(info, entries, posts[0].date.date().isoformat(), posts[-1].date.date().isoformat())
    obsidian.write_text_atomic(notes_root / f"{book_name}.md", index)

    readme = build_readme(info, posts, book_name, opts)
    obsidian.write_text_atomic(root / "README.md", readme)

    # Word / PDF
    result = PackResult(root=root, zip_path=None, posts=len(posts))
    book_meta = {
        "channel": f"@{info.username}" if info.username else info.title,
        "url": f"https://t.me/{info.username}" if info.username else None,
        "range_from": posts[0].date.date().isoformat(), "range_to": posts[-1].date.date().isoformat(),
        "post_count": len(posts),
    }
    total = sum(int(p.entry.get("duration") or 0) for p in posts)
    if total:
        book_meta["duration"] = total
    book_text = build_book_markdown(info, posts, opts.front_matter, opts.toc)
    readme_fmt = "pdf" if "pdf" in opts.formats else (opts.formats[0] if opts.formats else None)
    exports: List[ExportResult] = []
    if opts.formats:
        from versline.services.docexport import export_items

        log("Exporting book…")
        for fmt in opts.formats:
            items = [ExportItem(out_base=root / book_name, text=book_text, metadata=book_meta, title=info.title,
                                base_dir=archive_dir)]
            if fmt == readme_fmt:
                items.append(ExportItem(out_base=root / "README", text=readme, title=info.title, base_dir=root))
            exports += export_items(items, _export_options(opts, (fmt,)))
        if opts.per_post:
            log(f"Exporting {len(posts)} posts…")
            exports += export_posts(archive_dir, posts, root / "posts", opts)
    result.failures = [f"{r.output.name}: {r.error}" for r in exports if not r.ok]
    result.book_files = [r.output for r in exports if r.ok and r.output.parent == root and r.output.stem == book_name]

    # catalog (after exports, so it only points at files that exist)
    rows = []
    for post in posts:
        row: Dict[str, Any] = {
            "post_ids": "+".join(str(i) for i in post.entry.get("parts") or [post.meta.get("post_id", "")]),
            "date": post.date.date().isoformat(),
            "date_shamsi": post.meta.get("date_shamsi", ""),
            "title": post.title,
            "type": post.entry.get("media_type", ""),
            "duration": format_duration(post.entry["duration"]) if post.entry.get("duration") else "",
            "views": post.meta.get("views", ""),
            "forwards": post.meta.get("forwards", ""),
            "url": post.meta.get("url", ""),
            "note": _rel(notes_root / post.entry["note"], root),
            "attachments": " | ".join(post.attachments) if opts.media else "",
        }
        for fmt in ("docx", "pdf"):
            path = root / "posts" / fmt / f"{post.stem}.{fmt}"
            row[fmt] = _rel(path, root) if path.is_file() else ""
        rows.append(row)
    write_catalog(root, rows)

    if opts.make_zip:
        log("Creating ZIP…")
        result.zip_path = _zip_folder(root)
    return result


def _zip_folder(root: Path) -> Path:
    target = root.parent / (root.name + ".zip")
    tmp = target.with_name(target.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zf.write(path, Path(root.name) / path.relative_to(root))
    tmp.replace(target)
    return target
