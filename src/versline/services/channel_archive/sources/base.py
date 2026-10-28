from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator, Optional, Protocol

from versline.services.channel_archive.models import ChannelInfo, ChannelPost, MediaItem


class ChannelSource(Protocol):
    """A place posts come from. Telegram is the first implementation."""

    def resolve(self, ref: str) -> ChannelInfo: ...

    def iter_posts(
        self,
        channel: ChannelInfo,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterator[ChannelPost]:
        """Yield posts oldest-first with since <= date <= until (aware datetimes)."""
        ...

    def download(
        self,
        post: ChannelPost,
        item: MediaItem,
        dest_dir: Path,
        stem: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Path: ...

    def close(self) -> None: ...
