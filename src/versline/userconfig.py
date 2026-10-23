"""Per-user configuration location, so Versline works from any folder."""
import os
from pathlib import Path


def user_config_dir() -> Path:
    override = os.getenv("VERSLINE_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "versline"
    base = os.getenv("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "versline"


def user_env_path() -> Path:
    return user_config_dir() / "config.env"
