from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

AUDIO_KINDS = ("audio", "voice")
VIDEO_KINDS = ("video", "video_note")
TRANSCRIBABLE_KINDS = AUDIO_KINDS + VIDEO_KINDS


@dataclass
class ChannelInfo:
    ref: str
    title: str
    username: Optional[str] = None
    channel_id: Optional[int] = None
    kind: Optional[str] = None  # channel | supergroup | group | user (None when the source can't tell)

    @property
    def slug(self) -> str:
        if self.username:
            return self.username
        prefix = "chat" if self.kind in ("group", "user") else "channel"
        return f"{prefix}_{self.channel_id or 'unknown'}"

    @property
    def linkable(self) -> bool:
        """Whether t.me links to single messages exist (channels and supergroups only)."""
        return self.kind not in ("group", "user")


@dataclass
class MediaItem:
    kind: str  # audio | voice | video | video_note | photo | document
    file_name: Optional[str] = None
    mime: Optional[str] = None
    size: Optional[int] = None
    duration: Optional[float] = None
    source_ref: Any = None  # opaque handle used by ChannelSource.download
    downloadable: bool = True  # False when the source can't serve the file (e.g. audio on the web preview)

    @property
    def transcribable(self) -> bool:
        return self.kind in TRANSCRIBABLE_KINDS


@dataclass
class ChannelPost:
    id: int
    date: datetime  # timezone-aware
    text: str = ""
    media: List[MediaItem] = field(default_factory=list)
    url: Optional[str] = None
    views: Optional[int] = None
    forwards: Optional[int] = None
    hashtags: List[str] = field(default_factory=list)
    grouped_id: Optional[int] = None
    forwarded_from: Optional[str] = None
    edit_date: Optional[datetime] = None
    sender_id: Optional[int] = None
    sender_name: Optional[str] = None
    reply_to: Optional[int] = None  # id of the message this one replies to
    parts: List["ChannelPost"] = field(default_factory=list)  # set when several posts were merged into this one

    @property
    def part_ids(self) -> List[int]:
        return [part.id for part in self.parts] or [self.id]

    @property
    def media_type(self) -> str:
        return self.media[0].kind if self.media else "text"


@dataclass
class PostRecord:
    """What the steps build up for a post; the writer renders it without knowing which step added what."""

    post: ChannelPost
    frontmatter: Dict[str, Any] = field(default_factory=dict)
    sections: Dict[str, str] = field(default_factory=dict)  # key -> markdown body (rendered in insertion order)
    attachments: List[str] = field(default_factory=list)  # vault-relative paths to embed
    note_path: Optional[Path] = None
    work: Dict[str, Any] = field(default_factory=dict)  # scratch space shared between steps
