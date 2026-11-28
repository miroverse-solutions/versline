"""Documents of a Telegram post as Obsidian notes (``telegram archive --to-markdown``).

A document (PDF, Word, PowerPoint, Excel, EPUB, HTML, plain text…) becomes one Markdown note with frontmatter that
links back to its post. MarkItDown does the conversion; legacy Office files go through LibreOffice first. With an
:class:`OcrReader`, PDF pages that have no text layer (scans) and image files are read by the multimodal model, and
every page read is cached so an interrupted run never pays for a page twice.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from loguru import logger

from versline.core.prompts import load_prompt
from versline.services.channel_archive import obsidian
from versline.services.channel_archive.filters import item_extension
from versline.services.channel_archive.models import ChannelInfo, ChannelPost, MediaItem
from versline.utils.common import sanitize_filename

DOCUMENTS_DIR = "documents"
OCR_CACHE_NAME = ".versline-ocr.json"
OCR_PROMPT = "telegram_document_ocr_prompt.md"
OCR_DPI = 200
MIN_PAGE_CHARS = 20  # a PDF page with less extractable text than this counts as a scan

TEXT_DOC_EXTS = {".txt", ".md", ".markdown", ".csv", ".json", ".srt", ".vtt", ".xml", ".yaml", ".yml"}
MARKITDOWN_EXTS = {"pdf", "docx", "pptx", "xlsx", "xls", "html", "htm", "epub", "ipynb"}
LIBREOFFICE_EXTS = {"doc": "docx", "rtf": "docx", "odt": "docx", "ppt": "pptx", "odp": "pptx", "ods": "xlsx"}
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "tif", "tiff", "bmp"}
CONVERTIBLE_EXTS = {e.lstrip(".") for e in TEXT_DOC_EXTS} | MARKITDOWN_EXTS | set(LIBREOFFICE_EXTS)

_PREAMBLE_RE = re.compile(r"^\s*(بله|حتماً|حتما|البته|باشه|چشم|Sure|Certainly|Here is|Here's)[^\n]{0,200}:\s*\n+", re.IGNORECASE)
# Arabic presentation forms, except the word ligatures U+FDF0-FDFF (\ufdfa \ufdfb \ufdfd...) written on purpose.
_PRESENTATION_FORMS_RE = re.compile("[\ufb50-\ufdef\ufe70-\ufefe]+")
_CONTROL_RE = re.compile("[\x00-\x08\x0b\x0e-\x1f\x7f\ufeff]")
_DATA_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(data:[^)]*\)")
_UNSAFE_LINK_CHARS = re.compile(r"[#^\[\]|]")
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


# ---------- text ----------

def strip_chatter(text: str) -> str:
    """Drop a model's opening line such as «بله، حتماً…:» / "Here is the text:"."""
    return _PREAMBLE_RE.sub("", text.strip(), count=1).strip()


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


def clean_for_obsidian(text: str) -> str:
    """Make converted text safe and tidy as an Obsidian note body.

    Arabic presentation forms (common in text taken from Persian PDFs) become ordinary letters, control characters
    and inline data-URI images are dropped, and ``[[``/``]]``/``%%`` are escaped so they don't turn into links or
    hidden comments."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _PRESENTATION_FORMS_RE.sub(lambda m: unicodedata.normalize("NFKC", m.group(0)), text)
    text = _CONTROL_RE.sub("", text)
    text = _DATA_IMAGE_RE.sub("", text)
    text = text.replace("[[", r"\[\[").replace("]]", r"\]\]").replace("%%", r"\%\%")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def document_extension(item: MediaItem) -> Optional[str]:
    ext = item_extension(item)
    if not ext and item.mime:
        guessed = mimetypes.guess_extension(item.mime.split(";")[0].strip())
        ext = guessed.lstrip(".").lower() if guessed else None
    return {"jpe": "jpg"}.get(ext or "", ext)


def is_convertible(item: MediaItem, ocr: bool = False) -> bool:
    """Documents --to-markdown turns into notes; image files only when they can be read with OCR."""
    if item.kind != "document":
        return False
    ext = document_extension(item)
    return bool(ext) and (ext in CONVERTIBLE_EXTS or (ocr and ext in IMAGE_EXTS))


def needs_conversion(previous: Optional[dict], out_dir: Path, ocr: bool, force: bool) -> bool:
    """Whether a document recorded in the manifest (``previous``; None = never converted) must be converted again:
    with --force, after a failure, when its note is gone, or when --ocr can now read its scanned pages."""
    if force or not previous or previous.get("error") or not previous.get("note"):
        return True
    if not (out_dir / previous["note"]).is_file():
        return True
    return ocr and bool(previous.get("unread_pages"))


# ---------- OCR ----------

def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class OcrReader:
    """Reads page images with the multimodal model (``TextLLM.generate_with_image``), caching every page.

    The cache (``.versline-ocr.json`` in the output folder) is keyed by the file's sha256 and the page number, and
    saved after each page. ``force`` ignores pages cached by earlier runs (pages read in this run are still reused)."""

    def __init__(self, llm, cache_path: Optional[Path] = None, max_pages: int = 200, force: bool = False,
                 model: str = "", all_pages: bool = False):
        self.llm = llm
        self.all_pages = all_pages  # read every PDF page, not only scans (broken or legacy-font text layers)
        self.max_pages = max_pages
        self.force = force
        self.model = model
        self.cache_path: Optional[Path] = None
        self._fresh: Set[str] = set()
        self._data: Dict[str, Dict[str, str]] = {}
        if cache_path:
            self.bind_cache(cache_path)

    def bind_cache(self, cache_path: Path) -> None:
        """Point the reader at the output folder's cache once that folder is known."""
        if self.cache_path == cache_path:
            return
        self.cache_path = cache_path
        self._data, self._fresh = {}, set()
        if cache_path.is_file():
            try:
                self._data = json.loads(cache_path.read_text(encoding="utf-8")).get("files", {})
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def cached(self, digest: str, page: int) -> Optional[str]:
        key = f"{digest}:{page}"
        if self.force and key not in self._fresh:
            return None
        return self._data.get(digest, {}).get(str(page))

    def read(self, digest: str, page: int, render: Callable[[], Path]) -> str:
        hit = self.cached(digest, page)
        if hit is not None:
            return hit
        image = render()
        text = strip_chatter(self.llm.generate_with_image(load_prompt(OCR_PROMPT), image))
        self._data.setdefault(digest, {})[str(page)] = text
        self._fresh.add(f"{digest}:{page}")
        self._save()
        return text

    def _save(self) -> None:
        if not self.cache_path:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_name(self.cache_path.name + ".tmp")
        tmp.write_text(json.dumps({"version": 1, "files": self._data}, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.cache_path)


# ---------- conversion ----------

@dataclass
class DocResult:
    text: str
    converter: str  # text | markitdown | libreoffice+markitdown | pymupdf | pymupdf+ocr | ocr
    pages: Optional[int] = None
    ocr_pages: int = 0
    unread_pages: int = 0  # scanned pages left unread (no --ocr, or over --ocr-max-pages)
    warnings: List[str] = field(default_factory=list)


def _page_marker(number: int) -> str:
    return f"%% صفحه {str(number).translate(_FA_DIGITS)} %%"


def _join_pages(pages: List[str]) -> str:
    if len(pages) == 1:
        return pages[0]
    return "\n\n".join(f"{_page_marker(i)}\n\n{text}".rstrip() for i, text in enumerate(pages, 1))


def _convert_pdf(path: Path, ocr: Optional[OcrReader], temp_dir: Path) -> DocResult:
    """Page by page with PyMuPDF, which keeps Persian/Arabic in reading order (pdfminer, behind MarkItDown, often
    reverses it). Pages without a text layer are read with OCR when there is an OcrReader."""
    from versline.services.document_processor import _import_pymupdf

    fitz = _import_pymupdf()
    doc = fitz.open(str(path))
    try:
        count = len(doc)
        texts = [clean_for_obsidian(doc[i].get_text()) for i in range(count)]
        if ocr is not None and ocr.all_pages:
            scans = list(range(count))
        else:
            scans = [i for i in range(count) if len(texts[i]) < MIN_PAGE_CHARS and doc[i].get_images()]
        result = DocResult(text="", converter="pymupdf", pages=count)
        if scans and ocr is None:
            result.unread_pages = len(scans)
            result.warnings.append(
                f"{len(scans)} of {count} pages have no text layer (scanned); run with --ocr to read them"
            )
        elif scans:
            digest = file_digest(path)
            skipped = new_reads = 0
            for i in scans:
                if ocr.cached(digest, i + 1) is None:
                    if new_reads >= ocr.max_pages:  # the cap counts pages sent to the model, not cached ones
                        texts[i] = "[صفحه خوانده نشد: بیش از سقف --ocr-max-pages]"
                        skipped += 1
                        continue
                    new_reads += 1

                def render(index: int = i) -> Path:
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    image = temp_dir / f"{path.stem}_p{index + 1}.png"
                    doc[index].get_pixmap(dpi=OCR_DPI).save(str(image))
                    return image

                try:
                    texts[i] = clean_for_obsidian(ocr.read(digest, i + 1, render))
                finally:
                    (temp_dir / f"{path.stem}_p{i + 1}.png").unlink(missing_ok=True)
                result.ocr_pages += 1
            result.unread_pages = skipped
            if skipped:
                result.warnings.append(f"{skipped} scanned pages over --ocr-max-pages ({ocr.max_pages}) were not read")
            result.converter = "ocr" if result.ocr_pages == count else "pymupdf+ocr"
        result.text = _join_pages(texts) if any(texts) else ""
        return result
    finally:
        doc.close()


def convert_document(path: Path, ext: Optional[str] = None, ocr: Optional[OcrReader] = None,
                     temp_dir: Optional[Path] = None) -> DocResult:
    """Markdown of one document file, already cleaned for Obsidian; raises when the file can't be read at all."""
    ext = (ext or path.suffix.lstrip(".")).lower()
    temp_dir = temp_dir or path.parent
    if ext == "pdf":
        result = _convert_pdf(path, ocr, temp_dir)  # cleans page by page, around its page markers
    else:
        result = _convert_other(path, ext, ocr)
        result.text = clean_for_obsidian(result.text)
    if not result.text.strip() and not result.warnings:
        result.warnings.append("no text could be extracted" + ("" if ocr else "; if it is a scan, run with --ocr"))
    return result


def _convert_other(path: Path, ext: str, ocr: Optional[OcrReader]) -> DocResult:
    if f".{ext}" in TEXT_DOC_EXTS:
        return DocResult(text=read_document(path), converter="text")
    if ext in IMAGE_EXTS:
        if ocr is None:
            raise ValueError("image files need --ocr")
        result = DocResult(text=ocr.read(file_digest(path), 1, lambda: path), converter="ocr", pages=1, ocr_pages=1)
    elif ext in LIBREOFFICE_EXTS:
        from versline.services.document_processor import convert_with_libreoffice

        converted = Path(convert_with_libreoffice(str(path), LIBREOFFICE_EXTS[ext], f".{ext}"))
        try:
            result = DocResult(text=read_document(converted), converter="libreoffice+markitdown")
        finally:
            shutil.rmtree(converted.parent, ignore_errors=True)
    else:
        result = DocResult(text=read_document(path), converter="markitdown")
    return result


# ---------- notes ----------

def note_stem(file_name: str) -> str:
    stem = Path(file_name).stem if Path(file_name).suffix else file_name
    return _UNSAFE_LINK_CHARS.sub("", sanitize_filename(stem)).strip(" .") or "document"


def link_target(rel_path: str) -> str:
    """A vault-relative note path as a wikilink target (without the .md extension)."""
    return rel_path[:-3] if rel_path.endswith(".md") else rel_path


def render_document_note(
    *,
    title: str,
    result: DocResult,
    channel: ChannelInfo,
    post: ChannelPost,
    item: MediaItem,
    file_name: str,
    post_note: Optional[str] = None,
    post_title: Optional[str] = None,
    source_file: Optional[str] = None,
    ocr_model: Optional[str] = None,
) -> str:
    local = post.date.astimezone()
    tags = ["telegram", "document"] + [t for t in obsidian.extract_hashtags(post.text) if t not in ("telegram", "document")]
    frontmatter = {
        "title": title,
        "type": "telegram-document",
        "source": "telegram",
        "channel": f"@{channel.username}" if channel.username else channel.ref,
        "channel_title": channel.title,
        "post_id": post.id,
        "url": post.url,
        "date": local,
        "date_shamsi": obsidian.to_shamsi(local),
        "post": f"[[{link_target(post_note)}]]" if post_note else None,
        "file_name": file_name,
        "source_file": f"[[{source_file}]]" if source_file else None,
        "file_size": item.size,
        "mime": item.mime,
        "pages": result.pages,
        "converter": result.converter,
        "ocr_model": ocr_model if result.ocr_pages else None,
        "ocr_pages": result.ocr_pages or None,
        "conversion_warnings": result.warnings or None,
        "tags": tags,
        "aliases": [file_name] if file_name != title else [],
        "converted_at": datetime.now().astimezone(),
    }
    lines = [obsidian.render_frontmatter(frontmatter), "", f"# {title}", ""]
    refs = []
    if post_note:
        refs.append(f"{obsidian.LABELS['post']}: [[{link_target(post_note)}|{post_title or post.id}]]")
    if source_file:
        refs.append(f"{obsidian.LABELS['document_file']}: [[{source_file}|{file_name}]]")
    if refs:
        lines += [" · ".join(refs), ""]
    for warning in result.warnings:
        lines += [f"> [!warning] {warning}", ""]
    body = result.text.strip()
    if body:
        lines += [body, ""]
    if post.url:
        lines += ["---", f"[{obsidian.LABELS['source']}]({post.url})", ""]
    return "\n".join(lines)


def documents_section(links: List[str]) -> str:
    """Body of the post note's «اسناد» section: one wikilink per document note."""
    return "\n".join(f"- {link}" for link in links)


def note_link(rel_note: str, file_name: str) -> str:
    return f"[[{link_target(rel_note)}|{file_name.replace('|', ' ')}]]"


def write_document_note(
    out_dir: Path,
    rel_note: str,
    *,
    path: Path,
    ext: Optional[str],
    ocr: Optional[OcrReader],
    temp_dir: Path,
    **render_kwargs,
) -> DocResult:
    """Convert `path` and write its note at out_dir/rel_note."""
    result = convert_document(path, ext, ocr=ocr, temp_dir=temp_dir)
    for warning in result.warnings:
        logger.warning(f"{render_kwargs.get('file_name') or path.name}: {warning}")
    title = note_stem(render_kwargs.get("file_name") or path.name)
    content = render_document_note(title=title, result=result, ocr_model=ocr.model if ocr else None, **render_kwargs)
    obsidian.write_text_atomic(out_dir / rel_note, content)
    return result


def unique_note_path(out_dir: Path, folder: str, file_name: str, post_id: int, owned: Set[str],
                     taken: Set[str]) -> str:
    """`folder/<name>.md`, or `<name> (post <id>).md` when another post's document already has that name."""
    stem = note_stem(file_name)
    candidates = [f"{stem}.md", f"{stem} (post {post_id}).md"] + [f"{stem} (post {post_id}-{n}).md" for n in range(2, 100)]
    for name in candidates:
        rel = f"{folder}/{name}" if folder else name
        if rel in taken:
            continue
        if rel in owned or not (out_dir / rel).exists():
            return rel
    raise RuntimeError(f"No free note name for {file_name}")
