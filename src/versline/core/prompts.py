from functools import lru_cache
from pathlib import Path
from typing import Optional


def resolve_text_input(
    text: Optional[str] = None,
    text_file: Optional[str] = None,
    *,
    label: str,
    allowed_suffixes: tuple[str, ...] = (".md", ".txt", ""),
) -> Optional[str]:
    if text_file:
        path = Path(text_file)
        if not path.exists():
            raise FileNotFoundError(f"{label} file not found: {text_file}")
        if path.suffix.lower() not in allowed_suffixes:
            allowed = ", ".join(sorted(suffix or "(no suffix)" for suffix in allowed_suffixes))
            raise ValueError(f"{label} file must be one of: {allowed}")
        return path.read_text(encoding="utf-8").strip() or None
    if text:
        return text.strip() or None
    return None


def resolve_user_note(note: Optional[str] = None, note_file: Optional[str] = None) -> Optional[str]:
    """Return user note text from a direct string or a .md/.txt file path."""
    return resolve_text_input(note, note_file, label="Note")


def get_default_prompt_path(filename: str) -> Path:
    """Get the absolute path to a default prompt file in the package."""
    base_dir = Path(__file__).parent.parent
    prompt_path = base_dir / "resources" / "prompts" / filename
    return prompt_path


@lru_cache(maxsize=None)
def load_prompt(filename: str) -> str:
    """Load content of a prompt file."""
    path = get_default_prompt_path(filename)
    if path.exists():
        return path.read_text(encoding="utf-8")

    raise FileNotFoundError(f"Prompt file not found: {path}")
