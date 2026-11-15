"""Install or update the Versobs Obsidian plugin in a vault from its latest GitHub release.

The plugin is NOT bundled with Versline: its files (manifest.json, main.js, styles.css) are downloaded
from https://github.com/miroverse-solutions/versobs/releases. Only those files are replaced, so the
plugin's own settings (data.json) are kept. Obsidian still asks the user to enable a newly installed
plugin once (Settings → Community plugins).
"""
import json
import os
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

PLUGIN_REPO = "miroverse-solutions/versobs"
PLUGIN_ID = "versobs"
REQUIRED_FILES = ("manifest.json", "main.js")
OPTIONAL_FILES = ("styles.css",)


class PluginInstallError(RuntimeError):
    pass


@dataclass
class InstallResult:
    status: str  # "installed" | "updated" | "up-to-date" | "reinstalled"
    version: str
    previous: Optional[str]
    plugin_dir: str
    vault: str
    release_url: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


def obsidian_config_candidates() -> List[Path]:
    """Where Obsidian keeps obsidian.json (the list of known vaults) on this OS."""
    home = Path.home()
    if os.name == "nt":
        base = os.getenv("APPDATA") or str(home / "AppData" / "Roaming")
        return [Path(base) / "obsidian" / "obsidian.json"]
    if sys.platform == "darwin":
        return [home / "Library" / "Application Support" / "obsidian" / "obsidian.json"]
    xdg = Path(os.getenv("XDG_CONFIG_HOME") or home / ".config")
    return [
        xdg / "obsidian" / "obsidian.json",
        home / ".var" / "app" / "md.obsidian.Obsidian" / "config" / "obsidian" / "obsidian.json",  # Flatpak
        home / "snap" / "obsidian" / "current" / ".config" / "obsidian" / "obsidian.json",  # Snap
    ]


def known_vaults() -> List[Dict]:
    """Vaults registered in Obsidian, most recently opened first: [{path, name, open, exists, installed}]."""
    seen = set()
    vaults = []
    for config in obsidian_config_candidates():
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for entry in (data.get("vaults") or {}).values():
            raw = entry.get("path")
            if not raw or raw in seen:
                continue
            seen.add(raw)
            path = Path(raw)
            vaults.append({
                "path": str(path),
                "name": path.name,
                "open": bool(entry.get("open")),
                "ts": entry.get("ts") or 0,
                "exists": is_vault(path),
                "installed": installed_version(path) if is_vault(path) else None,
            })
    vaults.sort(key=lambda v: (not v["open"], -v["ts"]))
    return vaults


def is_vault(path: Path) -> bool:
    return (Path(path) / ".obsidian").is_dir()


def plugin_dir(vault: Path) -> Path:
    return Path(vault) / ".obsidian" / "plugins" / PLUGIN_ID


def installed_version(vault: Path) -> Optional[str]:
    try:
        return json.loads((plugin_dir(vault) / "manifest.json").read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError):
        return None


def resolve_vault(vault: Optional[Path]) -> Path:
    """The given vault (validated), or the single/most recent vault known to Obsidian."""
    if vault:
        path = Path(vault).expanduser().resolve()
        if not is_vault(path):
            raise PluginInstallError(f"{path} is not an Obsidian vault (no .obsidian folder). Open it in Obsidian once first.")
        return path
    candidates = [v for v in known_vaults() if v["exists"]]
    if not candidates:
        raise PluginInstallError("No Obsidian vault found. Pass --vault PATH.")
    return Path(candidates[0]["path"])


def _default_proxy(proxy: Optional[str]) -> Optional[str]:
    if proxy:
        return proxy
    try:
        from versline.config import settings

        return settings.llm.proxy or None
    except Exception:
        return None


def latest_plugin_release(tag: Optional[str] = None, proxy: Optional[str] = None, timeout: float = 20.0) -> Dict:
    from versline.services.releases import fetch_release

    try:
        release = fetch_release(PLUGIN_REPO, tag=tag, timeout=timeout, proxy=_default_proxy(proxy))
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 404:
            what = f"release {tag}" if tag else "published release"
            raise PluginInstallError(f"No {what} found at https://github.com/{PLUGIN_REPO}/releases") from exc
        if status in (403, 429):
            raise PluginInstallError("GitHub rate limit reached; try again later or set GITHUB_TOKEN.") from exc
        raise
    missing = [name for name in REQUIRED_FILES if name not in release["assets"]]
    if missing:
        raise PluginInstallError(
            f"Release {release['tag']} of {PLUGIN_REPO} has no {', '.join(missing)} asset."
        )
    return release


def plugin_status(vault: Path, proxy: Optional[str] = None, check_remote: bool = True) -> Dict:
    vault = resolve_vault(vault)
    status = {"vault": str(vault), "plugin_dir": str(plugin_dir(vault)), "installed": installed_version(vault),
              "latest": None, "update_available": False, "error": None}
    if check_remote:
        from versline.services.releases import is_newer

        try:
            release = latest_plugin_release(proxy=proxy)
            status["latest"] = (release["tag"] or "").lstrip("vV")
            status["update_available"] = status["installed"] is None or is_newer(status["latest"], status["installed"])
        except Exception as exc:
            status["error"] = str(exc)
    return status


def install_plugin(
    vault: Optional[Path] = None,
    tag: Optional[str] = None,
    proxy: Optional[str] = None,
    force: bool = False,
    timeout: float = 60.0,
) -> InstallResult:
    """Download the plugin release into <vault>/.obsidian/plugins/versobs (only replacing its own files)."""
    from versline.services.releases import download, version_tuple

    vault = resolve_vault(vault)
    proxy = _default_proxy(proxy)
    release = latest_plugin_release(tag=tag, proxy=proxy)
    target = plugin_dir(vault)
    previous = installed_version(vault)
    remote_version = (release["tag"] or "").lstrip("vV")

    if previous and not force and not tag and version_tuple(remote_version) <= version_tuple(previous):
        return InstallResult("up-to-date", previous, previous, str(target), str(vault), release.get("url"))

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".versobs-", dir=str(target.parent)))
    try:
        names = [n for n in REQUIRED_FILES + OPTIONAL_FILES if n in release["assets"]]
        for name in names:
            download(release["assets"][name], staging / name, timeout=timeout, proxy=proxy)
        try:
            manifest = json.loads((staging / "manifest.json").read_text(encoding="utf-8"))
        except ValueError as exc:
            raise PluginInstallError(f"Downloaded manifest.json is not valid JSON: {exc}")
        if manifest.get("id") != PLUGIN_ID:
            raise PluginInstallError(f"Downloaded manifest has id {manifest.get('id')!r}, expected {PLUGIN_ID!r}.")
        version = manifest.get("version") or remote_version

        target.mkdir(parents=True, exist_ok=True)
        # main.js first and manifest.json last, so a half-finished update never advertises a version it lacks.
        for name in sorted(names, key=lambda n: n == "manifest.json"):
            os.replace(staging / name, target / name)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    if previous is None:
        status = "installed"
    elif version_tuple(version) > version_tuple(previous):
        status = "updated"
    else:
        status = "reinstalled"
    return InstallResult(status, version, previous, str(target), str(vault), release.get("url"))
