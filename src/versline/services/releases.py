"""GitHub release lookup and download, shared by `versline update` and the Obsidian plugin installer.

Kept dependency-light (httpx only, imported lazily) so light commands stay fast.
"""
import os
from pathlib import Path
from typing import Dict, Optional, Tuple


def version_tuple(tag: str) -> Tuple[int, ...]:
    """'v1.10.2' -> (1, 10, 2); non-digit noise in a piece is ignored ('1rc2' -> 12)."""
    parts = []
    for piece in (tag or "").strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(candidate: Optional[str], current: Optional[str]) -> bool:
    return bool(candidate) and version_tuple(candidate) > version_tuple(current or "0")


def _client(timeout: float, proxy: Optional[str]):
    import httpx

    headers = {"Accept": "application/vnd.github+json", "User-Agent": "versline"}
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(timeout=timeout, follow_redirects=True, proxy=proxy or None, headers=headers)


def fetch_release(repo: str, tag: Optional[str] = None, timeout: float = 15.0, proxy: Optional[str] = None) -> Dict:
    """Return {"tag": str, "assets": {name: download_url}, "url": html_url} for the latest (or a tagged) release."""
    path = f"tags/{tag}" if tag else "latest"
    with _client(timeout, proxy) as client:
        resp = client.get(f"https://api.github.com/repos/{repo}/releases/{path}")
        if resp.status_code == 404 and tag and not tag.startswith("v"):
            resp = client.get(f"https://api.github.com/repos/{repo}/releases/tags/v{tag}")
        resp.raise_for_status()
        data = resp.json()
    assets = {a.get("name", ""): a.get("browser_download_url") for a in data.get("assets", []) if a.get("name")}
    return {"tag": data.get("tag_name"), "assets": assets, "url": data.get("html_url")}


def download(url: str, dest: Path, timeout: float = 60.0, proxy: Optional[str] = None) -> Path:
    """Download url to dest (parent created). Raises on HTTP errors."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with _client(timeout, proxy) as client:
        with client.stream("GET", url, headers={"Accept": "application/octet-stream"}) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as handle:
                for chunk in resp.iter_bytes():
                    handle.write(chunk)
    return dest
