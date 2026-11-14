from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, List, Optional, Set

from loguru import logger

from versline.config import settings

from versline.services.ai import MissingAPIKeyError
from versline.services.channel_archive import obsidian
from versline.services.channel_archive.filters import FileFilter
from versline.services.channel_archive.merge import DEFAULT_MAX_GAP, group_parts
from versline.services.channel_archive.models import ChannelInfo, ChannelPost, MediaItem, PostRecord
from versline.services.channel_archive.sources.base import ChannelSource
from versline.services.channel_archive.state import FILES_MANIFEST_NAME, ChannelState
from versline.services.channel_archive.steps import DEFAULT_STEPS, STEPS, PostStep, StepContext, clean_transcript
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
    reuse_transcripts: bool = False  # re-process archived posts, but keep the transcripts already in their notes
    file_filter: Optional[FileFilter] = None  # keep only posts with a media item that passes (and only those items)
    merge_parts: bool = False  # merge posts split across several messages (⬇️ … ⬆️, «ادامه دارد») into one note
    merge_gap: timedelta = DEFAULT_MAX_GAP  # max time between parts of one item
    files_only: bool = False  # save the matching files under their own names: no notes, no index, no LLM


@dataclass
class PostPlan:
    id: int
    date: datetime
    media_type: str
    duration: Optional[float]
    title: str
    files: List[str] = field(default_factory=list)
    parts: List[int] = field(default_factory=list)


@dataclass
class ArchiveSummary:
    channel: Optional[ChannelInfo] = None
    done: int = 0
    skipped: int = 0
    failed: int = 0
    files_saved: int = 0
    duplicates: int = 0
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
        if types is not None and post.media_type not in types:
            return False
        flt = self.options.file_filter
        return flt is None or bool(flt.matching_indices(post))

    @staticmethod
    def _is_done(state: ChannelState, post: ChannelPost) -> bool:
        if not state.is_done(post.id):
            return False
        entry = state.get(post.id) or {}
        if post.parts:
            return entry.get("parts") == post.part_ids
        return not entry.get("merged_into") and not entry.get("parts")

    def _selected(self, post: ChannelPost) -> List[int]:
        flt = self.options.file_filter
        return flt.matching_indices(post) if flt else list(range(len(post.media)))

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
        if post.parts:
            record.frontmatter["post_ids"] = post.part_ids
            record.frontmatter["part_urls"] = [p.url for p in post.parts if p.url]
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
        state = ChannelState(self.out_dir, FILES_MANIFEST_NAME) if opts.files_only else ChannelState(self.out_dir)
        count = 0
        posts = self.source.iter_posts(channel, opts.since, opts.until)
        if opts.merge_parts and not opts.files_only:
            posts = group_parts(posts, opts.merge_gap)

        try:
            for post in posts:
                if not self._wanted(post):
                    continue
                title = obsidian.make_title(post)
                if opts.dry_run:
                    names = [post.media[i].file_name or post.media[i].kind for i in self._selected(post)]
                    summary.plans.append(PostPlan(post.id, post.date, post.media_type, self._duration(post), title, names,
                                                  post.part_ids if post.parts else []))
                elif self._is_done(state, post) and not (opts.force or opts.reuse_transcripts):
                    summary.skipped += 1
                elif opts.files_only:
                    self._save_files(channel, post, title, state, summary)
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
                if not opts.files_only:
                    self._write_index(channel, state)
        return summary

    def _process(self, channel: ChannelInfo, post: ChannelPost, title: str, state: ChannelState, summary: ArchiveSummary) -> None:
        opts = self.options
        previous = state.get(post.id)
        if previous and previous.get("merged_into"):
            previous = None  # this post's note is the merged one; don't overwrite it
        rel_note = (
            Path(previous["note"])
            if previous and previous.get("note")
            else Path("posts") / f"{obsidian.note_stem(post, title)}.md"
        )
        record = self._base_record(channel, post, title)
        if opts.reuse_transcripts and any(item.transcribable for item in post.media):
            old = obsidian.read_note_transcript(self.out_dir / rel_note)
            if old:
                record.sections["transcript"] = clean_transcript(old[0])
                record.frontmatter["transcribed"] = True
                if old[1]:
                    record.frontmatter["transcription_model"] = old[1]
                record.work["reused_transcript"] = True
                logger.info(f"Post {post.id}: reusing the transcript from its existing note")
        old_notes: List[Path] = []
        if post.parts:
            old_notes = self._old_part_notes(post, state, rel_note)
            if not opts.force and not record.work.get("reused_transcript"):
                self._reuse_part_transcripts(post, state, record)
        try:
            for step in self.steps:
                step.run(post, record, self.ctx)
            obsidian.write_text_atomic(self.out_dir / rel_note, obsidian.render_note(record, title))
            date_iso = post.date.astimezone().isoformat(timespec="seconds")
            extra = {"parts": post.part_ids} if post.parts else {}
            state.set(
                post.id,
                status="done",
                note=rel_note.as_posix(),
                title=title,
                media_type=post.media_type,
                date=date_iso,
                duration=round(self._duration(post)) if self._duration(post) else None,
                **extra,
            )
            for part in post.parts[1:]:
                state.set(part.id, status="done", merged_into=post.id, note=rel_note.as_posix(), title=title,
                          media_type=part.media_type, date=part.date.astimezone().isoformat(timespec="seconds"))
            for old in old_notes:
                try:
                    (self.out_dir / old).unlink()
                except OSError:
                    pass
            summary.done += 1
            logger.success(f"Post {post.id} → {rel_note.as_posix()}")
        except (KeyboardInterrupt, MissingAPIKeyError):
            # a missing key fails every post the same way, so stop the run instead
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

    def _old_part_notes(self, post: ChannelPost, state: ChannelState, rel_note: Path) -> List[Path]:
        """Notes we wrote earlier for the parts as separate posts (to delete once the merged note exists)."""
        found: List[Path] = []
        for part in post.parts:
            entry = state.get(part.id)
            if not entry or not entry.get("note") or entry.get("merged_into") or entry.get("parts"):
                continue
            note = Path(entry["note"])
            if note != rel_note and note not in found and (self.out_dir / note).is_file():
                found.append(note)
        return found

    def _reuse_part_transcripts(self, post: ChannelPost, state: ChannelState, record: PostRecord) -> None:
        """Take transcripts from the parts' existing separate notes so merging doesn't transcribe again."""
        if not self.ctx.transcribe:
            return
        texts: List[str] = []
        model = None
        for part in post.parts:
            if not any(item.transcribable for item in part.media):
                continue
            entry = state.get(part.id)
            if not entry or entry.get("merged_into") or entry.get("parts") or not entry.get("note"):
                return
            old = obsidian.read_note_transcript(self.out_dir / entry["note"])
            if not old:
                return
            texts.append(clean_transcript(old[0]))
            model = model or old[1]
        if not texts:
            return
        record.sections["transcript"] = (
            texts[0] if len(texts) == 1 else "\n\n".join(f"### {i}\n\n{t}" for i, t in enumerate(texts, 1))
        )
        record.frontmatter["transcribed"] = True
        if model:
            record.frontmatter["transcription_model"] = model
        record.work["reused_transcript"] = True
        logger.info(f"Post {post.id}: reusing transcripts from the parts' existing notes")

    def _save_files(self, channel: ChannelInfo, post: ChannelPost, title: str, state: ChannelState, summary: ArchiveSummary) -> None:
        """--files-only: download the selected items to temp, then move them into the output folder under their own names."""
        saved: List[str] = []
        duplicates = 0
        try:
            for index in self._selected(post):
                item = post.media[index]
                if not item.downloadable:
                    logger.warning(f"Post {post.id}: {item.kind} can't be downloaded from this source; skipping it.")
                    continue
                max_mb = self.ctx.max_size_mb
                if max_mb and item.size and item.size > max_mb * 1024 * 1024:
                    logger.warning(f"Post {post.id}: media is {item.size / 1048576:.0f} MB, over --max-size; skipping it.")
                    continue
                stem = sanitize_filename(f"{channel.slug}_{post.id}" + (f"_{index + 1}" if len(post.media) > 1 else ""))
                self.ctx.progress(f"Downloading {item.file_name or item.kind} (post {post.id})…")
                temp_path = self.source.download(post, item, self.ctx.temp_dir, stem)
                final = self._place_file(temp_path, item, post, stem)
                if final is None:
                    duplicates += 1
                else:
                    saved.append(final.name)
                    logger.success(f"Post {post.id} → {final.name}")
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            logger.error(f"Post {post.id} failed: {exc}")
            state.set(post.id, status="failed", error=str(exc), title=title, files=saved,
                      date=post.date.astimezone().isoformat(timespec="seconds"))
            summary.failed += 1
            summary.errors.append(f"{post.id}: {exc}")
            summary.files_saved += len(saved)
            summary.duplicates += duplicates
            state.save()
            return
        summary.files_saved += len(saved)
        summary.duplicates += duplicates
        if not saved and not duplicates:
            summary.skipped += 1  # nothing could be fetched (not downloadable / too large); not recorded, so a later run retries
            return
        state.set(post.id, status="done", title=title, files=saved,
                  date=post.date.astimezone().isoformat(timespec="seconds"))
        summary.done += 1
        state.save()

    def _place_file(self, temp_path: Path, item: MediaItem, post: ChannelPost, stem: str) -> Optional[Path]:
        """Move a downloaded file into out_dir. Returns None when an identical file (same name and size) is already there."""
        name = sanitize_filename(item.file_name) if item.file_name else ""
        if name in ("", ".", ".."):
            name = f"{stem}{temp_path.suffix}"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        size = temp_path.stat().st_size
        base = Path(name)
        dest = self.out_dir / name
        attempt = 0
        while dest.exists():
            if dest.stat().st_size == size:
                temp_path.unlink(missing_ok=True)
                return None
            attempt += 1
            tag = f" (post {post.id})" if attempt == 1 else f" (post {post.id}-{attempt})"
            dest = self.out_dir / f"{base.stem}{tag}{base.suffix}"
        shutil.move(str(temp_path), str(dest))
        return dest

    def _write_index(self, channel: ChannelInfo, state: ChannelState) -> None:
        entries = list(state.posts.values())
        dates = sorted(e["date"][:10] for e in entries if e.get("status") == "done" and e.get("date"))
        content = obsidian.render_index(channel, entries, dates[0] if dates else None, dates[-1] if dates else None)
        name = sanitize_filename(channel.title) or channel.slug
        obsidian.write_text_atomic(self.out_dir / f"{name}.md", content)
