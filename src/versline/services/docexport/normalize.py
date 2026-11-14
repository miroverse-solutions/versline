"""Convert Obsidian-flavoured Markdown into plain Markdown that MdPersia can render."""
import re
from pathlib import Path
from urllib.parse import quote, unquote

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
PAGE_BREAK = '<div class="page-break"></div>'

_EMBED_RE = re.compile(r"!\[\[([^\]\n]+?)\]\]")
_WIKILINK_RE = re.compile(r"\[\[([^\]\n]+?)\]\]")
_MD_IMAGE_RE = re.compile(r"(!\[[^\]\n]*\]\()(<?)([^)\n>]+)(>?)(\))")
_CALLOUT_RE = re.compile(r"^(\s*>\s*)\[!(\w+)\][+-]?", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"(^```.*?^```|^~~~.*?^~~~)", re.DOTALL | re.MULTILINE)
_SPLIT_PIPE = re.compile(r"\\?\|")


def _split_target(inner: str):
    parts = _SPLIT_PIPE.split(inner, maxsplit=1)
    return parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")


def _resolve(target: str, base_dir: Path) -> Path:
    path = Path(unquote(target.split("#", 1)[0]))
    return path if path.is_absolute() else (base_dir / path).resolve()


def _image_ref(path: Path, as_uri: bool) -> str:
    """DOCX wants a plain filesystem path. PDF pages are loaded from file://, but markdown-it refuses file: links,
    so give a percent-encoded absolute path ('/C:/x/y.png' on Windows) that resolves against the page's base URL."""
    posix = path.as_posix()
    if not as_uri:
        return posix
    if re.match(r"^[A-Za-z]:", posix):
        posix = "/" + posix
    return quote(posix, safe="/:")


def _normalize_segment(text: str, base_dir: Path, as_uri: bool) -> str:
    def embed(m):
        target, _alias = _split_target(m.group(1))
        path = _resolve(target, base_dir)
        if path.suffix.lower() in IMAGE_EXTS:
            return f"![](<{_image_ref(path, as_uri)}>)" if path.is_file() else f"📎 {path.name}"
        return f"📎 {path.name or target}"

    def link(m):
        target, alias = _split_target(m.group(1))
        return alias or Path(target.split("#", 1)[0]).stem or target

    def image(m):
        src = m.group(3).strip()
        if re.match(r"^[a-z][a-z0-9+.-]*:", src, re.I) and not re.match(r"^[a-z]:[\\/]", src, re.I):
            return m.group(0)
        path = _resolve(src, base_dir)
        if not path.is_file():
            return m.group(0)
        return f"{m.group(1)}<{_image_ref(path, as_uri)}>{m.group(5)}"

    text = _EMBED_RE.sub(embed, text)
    text = _WIKILINK_RE.sub(link, text)
    text = _MD_IMAGE_RE.sub(image, text)
    return _CALLOUT_RE.sub(lambda m: f"{m.group(1)}[!{m.group(2).upper()}]", text)


def prepare_markdown(text: str, base_dir: Path, as_uri: bool = False) -> str:
    """Make Obsidian embeds/wikilinks/callouts standard; images become absolute paths (code fences untouched)."""
    base_dir = Path(base_dir)
    pieces = _CODE_FENCE_RE.split(text)
    for i in range(0, len(pieces), 2):  # odd indexes are the fenced blocks
        pieces[i] = _normalize_segment(pieces[i], base_dir, as_uri)
    return "".join(pieces)
