from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

MANIFEST_NAME = ".versline-channel.json"


class ChannelState:
    """Per-channel manifest: which posts are done/failed, so reruns skip finished work."""

    def __init__(self, root: Path):
        self.path = root / MANIFEST_NAME
        self.posts: Dict[str, dict] = {}
        self.channel: dict = {}
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.posts = data.get("posts", {})
                self.channel = data.get("channel", {})
            except (json.JSONDecodeError, OSError):
                pass

    def get(self, post_id: int) -> Optional[dict]:
        return self.posts.get(str(post_id))

    def is_done(self, post_id: int) -> bool:
        entry = self.get(post_id)
        return bool(entry and entry.get("status") == "done")

    def set(self, post_id: int, **entry) -> None:
        self.posts[str(post_id)] = entry

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"channel": self.channel, "posts": self.posts}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)
