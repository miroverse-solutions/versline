from pathlib import Path

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
