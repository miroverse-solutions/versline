"""Shared Markdown -> Word/PDF export used by every module."""
import re
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from loguru import logger

from versline.config import settings
from versline.services.docexport import engine
from versline.services.docexport.engine import EngineOptions, ExportError
from versline.services.docexport.frontmatter import metadata_table, split_front_matter
from versline.services.docexport.normalize import prepare_markdown

ALL_FORMATS = ("docx", "pdf")
_ALIASES = {"word": "docx", "doc": "docx", "docx": "docx", "pdf": "pdf"}
_H1_RE = re.compile(r"^#[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)


def parse_formats(value) -> Tuple[str, ...]:
    """'docx,pdf' / 'word' / 'all' / iterable -> validated tuple. Empty input gives ()."""
    if value is None:
        return ()
    items = [v for v in re.split(r"[,\s+]+", value) if v] if isinstance(value, str) else list(value)
    result: List[str] = []
    for item in items:
        item = item.strip().lower().lstrip(".")
        if item == "all":
            names = list(ALL_FORMATS)
        elif item in _ALIASES:
            names = [_ALIASES[item]]
        else:
            raise ValueError(f"Unknown export format '{item}' (use docx, pdf or all)")
        result += [n for n in names if n not in result]
    return tuple(result)


@dataclass
class ExportOptions:
    formats: Tuple[str, ...] = ALL_FORMATS
    front_matter: bool = True
    page_format: str = "A4"
    margin: str = "15mm"
    landscape: bool = False
    font_size: int = 12
    force: bool = False

    @classmethod
    def from_settings(cls, formats=None, front_matter: Optional[bool] = None, **overrides) -> "ExportOptions":
        cfg = settings.export
        return cls(
            formats=parse_formats(formats if formats is not None else cfg.formats),
            front_matter=cfg.front_matter if front_matter is None else front_matter,
            page_format=overrides.pop("page_format", None) or cfg.page_format,
            margin=overrides.pop("margin", None) or cfg.margin,
            landscape=overrides.pop("landscape", None) or cfg.landscape,
            font_size=overrides.pop("font_size", None) or cfg.font_size,
            **overrides,
        )


@dataclass
class ExportItem:
    """One document to export. Give ``source`` (a .md path) or ``text``."""
    out_base: Path  # output path without extension; ``.docx``/``.pdf`` is appended
    source: Optional[Path] = None
    text: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    title: Optional[str] = None
    base_dir: Optional[Path] = None  # where relative images/embeds resolve (default: source's folder)
    asset_dirs: Sequence[Path] = ()  # extra folders searched for embeds (e.g. an archive's root)


@dataclass
class ExportResult:
    item: ExportItem
    fmt: str
    output: Path
    ok: bool
    skipped: bool = False
    error: Optional[str] = None


def _out_path(item: ExportItem, fmt: str) -> Path:
    return item.out_base.with_name(item.out_base.name + "." + fmt)


def _up_to_date(item: ExportItem, out: Path) -> bool:
    if not out.is_file() or item.source is None or not item.source.is_file():
        return False
    return out.stat().st_mtime >= item.source.stat().st_mtime


def build_markdown(item: ExportItem, front_matter: bool, as_uri: bool) -> str:
    """Final Markdown for one item: normalized, with the metadata table after the title (or none)."""
    raw = item.text if item.text is not None else Path(item.source).read_text(encoding="utf-8")
    file_meta, body = split_front_matter(raw)
    meta = {**item.metadata, **file_meta}  # the document's own front matter wins
    base = item.base_dir or (item.source.parent if item.source else Path.cwd())
    body = prepare_markdown(body, base, as_uri=as_uri).lstrip("\n")
    if not front_matter:
        return body
    table = metadata_table(meta)
    if not table:
        return body
    match = _H1_RE.search(body)
    if match:
        return f"{body[:match.end()]}\n\n{table}\n{body[match.end():]}"
    title = item.title or meta.get("title") or (item.source.stem if item.source else item.out_base.name)
    return f"# {title}\n\n{table}\n\n{body}"


def export_items(
    items: Iterable[ExportItem],
    opts: Optional[ExportOptions] = None,
    on_progress: Optional[Callable[[ExportResult], None]] = None,
) -> List[ExportResult]:
    """Export all items in one batch per format (one browser launch for PDFs). Raises ExportError if the engine is unusable."""
    opts = opts or ExportOptions.from_settings()
    items = list(items)
    results: List[ExportResult] = []
    if not items or not opts.formats:
        return results
    if not engine.available():
        raise ExportError(engine.INSTALL_HINT)

    tmp_root = Path(settings.temp_directory) / "export" / uuid.uuid4().hex[:10]
    tmp_root.mkdir(parents=True, exist_ok=True)
    eopts = EngineOptions(opts.page_format, opts.margin, opts.landscape, opts.font_size)
    try:
        for fmt in opts.formats:
            pairs: List[Tuple[Path, Path]] = []
            by_out: Dict[Path, ExportItem] = {}
            for index, item in enumerate(items):
                out = _out_path(item, fmt)
                if not opts.force and _up_to_date(item, out):
                    results.append(ExportResult(item, fmt, out, ok=True, skipped=True))
                    continue
                md = tmp_root / f"{index:05d}_{fmt}" / f"{item.out_base.name[:80] or 'doc'}.md"
                md.parent.mkdir(parents=True, exist_ok=True)
                md.write_text(build_markdown(item, opts.front_matter, as_uri=(fmt == "pdf")), encoding="utf-8")
                out.parent.mkdir(parents=True, exist_ok=True)
                pairs.append((md, out))
                by_out[out] = item
            for out, error in engine.convert(pairs, fmt, eopts):
                result = ExportResult(by_out[out], fmt, out, ok=error is None, error=error)
                results.append(result)
                if on_progress:
                    on_progress(result)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
        try:
            tmp_root.parent.rmdir()  # only succeeds when empty
        except OSError:
            pass
    for r in results:
        if not r.ok:
            logger.error(f"Export failed for {r.output}: {r.error}")
    return results


def export_markdown_files(
    paths: Iterable[Path],
    opts: Optional[ExportOptions] = None,
    metadata_for: Optional[Callable[[Path], Dict[str, Any]]] = None,
    out_dir: Optional[Path] = None,
) -> List[ExportResult]:
    """Export existing .md files next to themselves (or into ``out_dir``)."""
    items = []
    for path in map(Path, paths):
        base = (Path(out_dir) if out_dir else path.parent) / path.stem
        items.append(ExportItem(out_base=base, source=path, metadata=metadata_for(path) if metadata_for else {}))
    return export_items(items, opts)
