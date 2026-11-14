"""Thin adapter over MdPersia (optional dependency, imported lazily)."""
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

INSTALL_HINT = 'MdPersia is not installed. Install it with: pip install "versline[export]" (needs Python 3.11+).'
BROWSER_HINT = "No usable browser for PDF output. Run: versline export --install-browser (or install Chrome/Edge)."


class ExportError(RuntimeError):
    """Export failed; the message already contains a hint for the user."""


@dataclass(frozen=True)
class EngineOptions:
    page_format: str = "A4"
    margin: str = "15mm"
    landscape: bool = False
    font_size: int = 12


def available() -> bool:
    try:
        import mdpersia  # noqa: F401
        return True
    except ImportError:
        return False


def font_file() -> Optional[Path]:
    from versline.resources.assets import ASSETS_DIR
    path = Path(ASSETS_DIR) / "Vazirmatn[wght].ttf"
    return path if path.is_file() else None


def convert(pairs: Sequence[Tuple[Path, Path]], fmt: str, opts: EngineOptions) -> List[Tuple[Path, Optional[str]]]:
    """Convert ``(markdown, output)`` pairs to ``fmt`` in one batch. Returns ``(output, error-or-None)`` per pair."""
    if not pairs:
        return []
    try:
        from mdpersia import ConvertOptions, convert_jobs
        from fa_md_pdf.converter import ConvertJob
    except ImportError as exc:
        raise ExportError(INSTALL_HINT) from exc

    font = font_file()
    options = ConvertOptions(
        output_format=fmt,
        page_format=opts.page_format,
        margin=opts.margin,
        landscape=opts.landscape,
        docx_font_size_pt=opts.font_size,
        font_file=font,
        ignore_mermaid_errors=True,
    )
    jobs = [ConvertJob(source=Path(src), output=Path(out)) for src, out in pairs]
    try:
        results = convert_jobs(jobs, options=options)
    except Exception as exc:  # playwright raises many types
        raise ExportError(_explain(exc)) from exc
    return [(r.job.output, None if r.ok else _explain_text(r.error)) for r in results]


def _explain_text(message: Optional[str]) -> str:
    message = message or "unknown error"
    if "Could not launch browser" in message or "Executable doesn't exist" in message:
        return f"{message}\n{BROWSER_HINT}"
    return message


def _explain(exc: Exception) -> str:
    return _explain_text(str(exc))


def install_browser() -> int:
    """Download Playwright's Chromium (one-time, ~150 MB)."""
    return subprocess.call([sys.executable, "-m", "playwright", "install", "chromium"])
