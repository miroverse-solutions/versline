"""Read/write the per-user ``config.env`` (shared by `versline init/config`, telegram login and the bridge)."""
from pathlib import Path
from typing import Dict, Optional

from versline.userconfig import user_config_dir, user_env_path

PROVIDERS = ["Google", "OpenAI", "OpenRouter", "AvalAI", "OpenAICompatible"]
DEFAULT_MODELS = {
    "Google": "gemini-2.0-flash",
    "OpenAI": "gpt-4o-mini",
    "OpenRouter": "~google/gemini-flash-latest",
    "AvalAI": "gemini-2.0-flash",
    "OpenAICompatible": "",
}
SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "HASH", "PASSWORD")


def read_env(path: Optional[Path] = None) -> Dict[str, str]:
    path = Path(path) if path else user_env_path()
    values: Dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def write_env(values: Dict[str, str], path: Optional[Path] = None) -> Path:
    path = Path(path) if path else user_env_path()
    if path == user_env_path():
        user_config_dir().mkdir(parents=True, exist_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    tmp.replace(path)
    return path


def update_env(changes: Dict[str, Optional[str]], path: Optional[Path] = None) -> Dict[str, str]:
    """Apply changes (None or '' removes the key) and return the new values."""
    values = read_env(path)
    for key, value in changes.items():
        if value is None or value == "":
            values.pop(key, None)
        else:
            values[key] = str(value)
    write_env(values, path)
    return values


def is_secret(key: str) -> bool:
    return any(marker in key.upper() for marker in SECRET_MARKERS)


def mask(key: str, value: str) -> str:
    if value and is_secret(key):
        return value[:4] + "…" + value[-2:] if len(value) > 8 else "***"
    return value
