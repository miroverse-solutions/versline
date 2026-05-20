from pathlib import Path
from typing import Optional


def resolve_user_note(note: Optional[str] = None, note_file: Optional[str] = None) -> Optional[str]:
    """Return user note text from a direct string or a .md/.txt file path.

    Parameters
    ----------
    note:
        A note string supplied directly on the CLI.
    note_file:
        Path to a ``.md`` or ``.txt`` file whose content is used as the note.

    Returns ``None`` when neither argument is provided.
    Raises ``FileNotFoundError`` if *note_file* is given but does not exist.
    Raises ``ValueError`` if *note_file* has an unsupported extension.
    """
    if note_file:
        path = Path(note_file)
        if not path.exists():
            raise FileNotFoundError(f"Note file not found: {note_file}")
        if path.suffix.lower() not in (".md", ".txt", ""):
            raise ValueError(
                f"Note file must be a .md or .txt file, got: {path.suffix!r}"
            )
        return path.read_text(encoding="utf-8").strip() or None
    if note:
        return note.strip() or None
    return None


def get_default_prompt_path(filename: str) -> Path:
    """Get the absolute path to a default prompt file in the package."""
    # Current file is in src/versline/core/prompts.py
    # Resources are in src/versline/resources/prompts/
    base_dir = Path(__file__).parent.parent 
    prompt_path = base_dir / "resources" / "prompts" / filename
    return prompt_path

def load_prompt(filename: str) -> str:
    """Load content of a prompt file."""
    path = get_default_prompt_path(filename)
    if not path.exists():
        # Fallback for dev environment if structure matches source but not installed package
        # e.g. if running from src root
        pass 
        
    if path.exists():
        return path.read_text(encoding="utf-8")
    
    raise FileNotFoundError(f"Prompt file not found: {path}")
