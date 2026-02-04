"""Assets for Versqude (CSS styles, etc.)."""

from pathlib import Path

ASSETS_DIR = Path(__file__).parent


def get_default_css() -> str:
    """Load the default CSS style for HTML output."""
    css_file = ASSETS_DIR / "default-style.css"
    if not css_file.exists():
        return ""
    with open(css_file, "r", encoding="utf-8") as f:
        return f.read()


def load_css(css_path: str | Path | None = None) -> str:
    """Load CSS content from a file or return default.
    
    Args:
        css_path: Path to custom CSS file, or None for default.
        
    Returns:
        CSS content as string.
    """
    if css_path:
        css_file = Path(css_path)
        if not css_file.exists():
            print(f"Warning: CSS file not found: {css_file}")
            return ""
        with open(css_file, "r", encoding="utf-8") as f:
            return f.read()
    return get_default_css()
