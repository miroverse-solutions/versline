from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Set

from loguru import logger

from versline.config import settings

from versline.services.channel_archive import obsidian
from versline.services.channel_archive.models import ChannelInfo, ChannelPost, PostRecord
from versline.services.channel_archive.sources.base import ChannelSource
from versline.services.channel_archive.state import ChannelState
from versline.services.channel_archive.steps import DEFAULT_STEPS, STEPS, PostStep, StepContext
from versline.utils.common import sanitize_filename


@dataclass
class ArchiveOptions:
    out_dir: Optional[Path] = None  # default: <output_directory>/<channel>
    temp_dir: Optional[Path] = None
    since: Optional[datetime] = None
    until: Optional[datetime] = None
    limit: Optional[int] = None
    types: Optional[Set[str]] = None  # media types to include; None = all ("text" = text-only posts)
    steps: List[str] = field(default_factory=lambda: list(DEFAULT_STEPS))
    dry_run: bool = False
    force: bool = False


@dataclass
class PostPlan:
    id: int
    date: datetime
    media_type: str
    duration: Optional[float]
    title: str


@dataclass
class ArchiveSummary:
    channel: Optional[ChannelInfo] = None
    done: int = 0
    skipped: int = 0
    failed: int = 0
    plans: List[PostPlan] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class ChannelArchiver:
    def __init__(self, source: ChannelSource, ctx: StepContext, options: ArchiveOptions):
        self.source = source
        self.ctx = ctx
        self.options = options
        self.out_dir = options.out_dir
        unknown = [name for name in options.steps if name not in STEPS]
        if unknown:
            raise ValueError(f"Unknown step(s): {', '.join(unknown)}. Available: {', '.join(STEPS)}")
        self.steps: List[PostStep] = [STEPS[name]() for name in options.steps]

    # -- helpers --

    def _wanted(self, post: ChannelPost) -> bool:
        types = self.options.types
        return types is None or post.media_type in types

    @staticmethod
    def _duration(post: ChannelPost) -> Optional[float]:
        total = sum(item.duration or 0 for item in post.media)
        return total or None

    def _base_record(self, channel: ChannelInfo, post: ChannelPost, title: str) -> PostRecord:
        local = post.date.astimezone()
        first = post.media[0] if post.media else None
        tags = ["telegram"] + [t for t in obsidian.extract_hashtags(post.text) if t != "telegram"]
        record = PostRecord(post=post)
        record.frontmatter.update(
            {
                "title": title,
                "source": "telegram",
                "channel": f"@{channel.username}" if channel.username else channel.ref,
                "channel_title": channel.title,
                "post_id": post.id,
                "url": post.url,
                "date": local,
                "date_shamsi": obsidian.to_shamsi(local),
                "media_type": post.media_type,
                "duration": round(self._duration(post)) if self._duration(post) else None,
                "file_name": first.file_name if first else None,
                "views": post.views,
                "forwards": post.forwards,
                "forwarded_from": post.forwarded_from,
                "album_size": len(post.media) if len(post.media) > 1 else None,
                "tags": tags,
                "aliases": [],
                "archived_at": datetime.now().astimezone(),
            }
        )
        if post.text.strip():
            record.sections["caption"] = post.text
        return record

    def _cleanup(self, record: PostRecord) -> None:
        if self.ctx.keep_media:
            files = record.work.get("temp_files", [])
        else:
            files = list(record.work.get("files", {}).values()) + record.work.get("temp_files", [])
        for path in files:
            try:
                Path(path).unlink()
            except OSError:
                pass

    # -- main --

    def run(self, ref: str, progress: Optional[Callable[[int, str], None]] = None) -> ArchiveSummary:
        opts = self.options
        summary = ArchiveSummary()
        channel = self.source.resolve(ref)
        summary.channel = channel
        self.ctx.channel = channel
        self.out_dir = opts.out_dir or Path(settings.output_directory) / channel.slug
        self.ctx.out_dir = self.out_dir
        state = ChannelState(self.out_dir)
        count = 0

        try:
            for post in self.source.iter_posts(channel, opts.since, opts.until):
                if not self._wanted(post):
                    continue
                title = obsidian.make_title(post)
                if opts.dry_run:
                    summary.plans.append(PostPlan(post.id, post.date, post.media_type, self._duration(post), title))
                elif state.is_done(post.id) and not opts.force:
                    summary.skipped += 1
                else:
                    self._process(channel, post, title, state, summary)
                count += 1
                if progress:
                    progress(count, f"Post {post.id}")
                if opts.limit and count >= opts.limit:
                    break
        finally:
            if not opts.dry_run:
                state.channel = {"title": channel.title, "username": channel.username, "id": channel.channel_id}
                state.save()
                self._write_index(channel, state)
        return summary

    def _process(self, channel: ChannelInfo, post: ChannelPost, title: str, state: ChannelState, summary: ArchiveSummary) -> None:
        opts = self.options
        previous = state.get(post.id)
        rel_note = (
            Path(previous["note"])
            if previous and previous.get("note")
            else Path("posts") / f"{obsidian.note_stem(post, title)}.md"
        )
        record = self._base_record(channel, post, title)
        try:
            for step in self.steps:
                step.run(post, record, self.ctx)
            obsidian.write_text_atomic(self.out_dir / rel_note, obsidian.render_note(record, title))
            state.set(
                post.id,
                status="done",
                note=rel_note.as_posix(),
                title=title,
                media_type=post.media_type,
                date=post.date.astimezone().isoformat(timespec="seconds"),
                duration=round(self._duration(post)) if self._duration(post) else None,
            )
            summary.done += 1
            logger.success(f"Post {post.id} → {rel_note.as_posix()}")
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            logger.error(f"Post {post.id} failed: {exc}")
            state.set(post.id, status="failed", error=str(exc), note=rel_note.as_posix(), title=title,
                      media_type=post.media_type, date=post.date.astimezone().isoformat(timespec="seconds"))
            summary.failed += 1
            summary.errors.append(f"{post.id}: {exc}")
        finally:
            self._cleanup(record)
            state.save()

    def _write_index(self, channel: ChannelInfo, state: ChannelState) -> None:
        entries = list(state.posts.values())
        dates = sorted(e["date"][:10] for e in entries if e.get("status") == "done" and e.get("date"))
        content = obsidian.render_index(channel, entries, dates[0] if dates else None, dates[-1] if dates else None)
        name = sanitize_filename(channel.title) or channel.slug
        obsidian.write_text_atomic(self.out_dir / f"{name}.md", content)
