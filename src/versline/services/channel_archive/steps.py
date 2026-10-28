from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

from loguru import logger

from versline.config import settings
from versline.services import media as media_utils
from versline.services.channel_archive.models import (
    ChannelInfo,
    ChannelPost,
    MediaItem,
    PostRecord,
    VIDEO_KINDS,
)
from versline.services.channel_archive.sources.base import ChannelSource
from versline.utils.common import sanitize_filename


@dataclass
class StepContext:
    source: ChannelSource
    channel: ChannelInfo
    out_dir: Optional[Path]
    temp_dir: Path
    keep_media: bool = False
    transcribe: bool = True
    max_size_mb: Optional[float] = None
    force: bool = False
    chunk_size: int = 900
    overlap: int = 180
    skip_blocked: bool = False
    transcriber: Any = None  # object with process_file(); created lazily by the command
    progress: Callable[[str], None] = lambda message: None


class PostStep(Protocol):
    """One unit of per-post processing. Steps only add to the PostRecord (frontmatter / sections / attachments)."""

    name: str

    def run(self, post: ChannelPost, record: PostRecord, ctx: StepContext) -> None: ...


def _is_video(item: MediaItem) -> bool:
    return item.kind in VIDEO_KINDS or (item.mime or "").startswith("video/")


class MediaStep:
    """Downloads the media a later step (or --keep-media) needs."""

    name = "media"

    def run(self, post: ChannelPost, record: PostRecord, ctx: StepContext) -> None:
        files: Dict[int, Path] = record.work.setdefault("files", {})
        dest_dir = ctx.out_dir / "attachments" if ctx.keep_media else ctx.temp_dir
        for index, item in enumerate(post.media):
            wanted = ctx.keep_media or (ctx.transcribe and item.transcribable)
            if not wanted:
                continue
            if ctx.max_size_mb and item.size and item.size > ctx.max_size_mb * 1024 * 1024:
                logger.warning(f"Post {post.id}: media is {item.size / 1048576:.0f} MB, over --max-size; skipping it.")
                record.frontmatter.setdefault("skipped_media", []).append(f"{item.kind} too large")
                continue
            stem = sanitize_filename(f"{ctx.channel.slug}_{post.id}" + (f"_{index + 1}" if len(post.media) > 1 else ""))
            ctx.progress(f"Downloading {item.kind} for post {post.id}…")
            path = ctx.source.download(post, item, dest_dir, stem)
            files[index] = path
            if ctx.keep_media:
                record.attachments.append(path.relative_to(ctx.out_dir).as_posix())


class TranscribeStep:
    """Transcribes audio/video media and stores the text as the `transcript` section."""

    name = "transcribe"

    def run(self, post: ChannelPost, record: PostRecord, ctx: StepContext) -> None:
        if not ctx.transcribe or ctx.transcriber is None:
            return
        files: Dict[int, Path] = record.work.get("files", {})
        texts: List[str] = []
        total_duration = 0.0
        for index, item in enumerate(post.media):
            if not item.transcribable or index not in files:
                continue
            source_path = files[index]
            audio_path = source_path
            if _is_video(item):
                audio_path = ctx.temp_dir / f"{source_path.stem}.mp3"
                ctx.progress(f"Extracting audio for post {post.id}…")
                media_utils.extract_audio(str(source_path), str(audio_path))
                record.work.setdefault("temp_files", []).append(audio_path)
            ctx.progress(f"Transcribing post {post.id}…")
            text = ctx.transcriber.process_file(
                str(audio_path),
                chunk_length=ctx.chunk_size,
                overlap=ctx.overlap,
                force=ctx.force,
                skip_blocked=ctx.skip_blocked,
            )
            texts.append(text.strip() if isinstance(text, str) else str(text))
            total_duration += item.duration or 0
            work_dir = Path("work_dir") / audio_path.stem
            shutil.rmtree(work_dir, ignore_errors=True)  # only reached on success; failures keep it for resuming
        if not texts:
            return
        if len(texts) == 1:
            record.sections["transcript"] = texts[0]
        else:
            record.sections["transcript"] = "\n\n".join(f"### {i}\n\n{t}" for i, t in enumerate(texts, 1))
        record.frontmatter["transcribed"] = True
        record.frontmatter["transcription_model"] = settings.llm.model


# New steps (summarize, translate, tag, ...) are registered here and listed in the pipeline by name.
STEPS: Dict[str, Callable[[], PostStep]] = {
    "media": MediaStep,
    "transcribe": TranscribeStep,
}
DEFAULT_STEPS = ["media", "transcribe"]
