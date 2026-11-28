from __future__ import annotations

import glob
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

from loguru import logger

from versline.config import settings
from versline.core.prompts import load_prompt
from versline.services import media as media_utils
from versline.services.channel_archive.filters import FileFilter
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
    text_llm: Any = None  # object with generate(prompt); needed by the summary/taqrir steps
    output_lang: str = ""  # language for summary/taqrir; empty = same as the content
    file_filter: Optional[FileFilter] = None  # when set, only matching media items are downloaded
    to_markdown: bool = False  # convert documents to notes under documents/ (the "documents" step)
    ocr: Any = None  # documents.OcrReader: read scanned PDF pages and image files with the multimodal model
    progress: Callable[[str], None] = lambda message: None


class PostStep(Protocol):
    """One unit of per-post processing. Steps only add to the PostRecord (frontmatter / sections / attachments)."""

    name: str

    def run(self, post: ChannelPost, record: PostRecord, ctx: StepContext) -> None: ...


_PREAMBLE_RE = re.compile(r"^\s*(بله|حتماً|حتما|البته|باشه|چشم|مطمئناً)[\s،,.!]*.{0,160}(پیاده|ویراستار|متن)[^\n]{0,120}:\s*$")
_END_MARKER_RE = re.compile(r"^\s*\[?\s*-{2,}[^\n\]]*پایان[^\n\]]*-{2,}\s*\]?\s*$")


def clean_transcript(text: str) -> str:
    """Drop the model's chatter around a transcript ("بله، حتماً… تقدیم می‌گردد:", "[---پایان فایل صوتی---]")."""
    lines = [line for line in text.splitlines() if not _PREAMBLE_RE.match(line) and not _END_MARKER_RE.match(line)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _is_video(item: MediaItem) -> bool:
    return item.kind in VIDEO_KINDS or (item.mime or "").startswith("video/")


def previous_documents(record: PostRecord) -> Dict[int, dict]:
    """Manifest entries of the documents converted for this post on an earlier run, by media index."""
    return record.work.get("previous_documents", {})


def _needs_markdown(ctx: StepContext, record: PostRecord, index: int, item: MediaItem) -> bool:
    from versline.services.channel_archive import documents as docs

    if not ctx.to_markdown or not docs.is_convertible(item, ocr=ctx.ocr is not None):
        return False
    return docs.needs_conversion(previous_documents(record).get(index), ctx.out_dir, ctx.ocr is not None, ctx.force)


class MediaStep:
    """Downloads the media a later step (or --keep-media) needs.

    With ``record.work["documents_only"]`` (documents added to a post archived earlier) only the documents to convert
    are fetched: from attachments/ when an earlier --keep-media run saved them there, else downloaded to temp."""

    name = "media"

    def run(self, post: ChannelPost, record: PostRecord, ctx: StepContext) -> None:
        files: Dict[int, Path] = record.work.setdefault("files", {})
        documents_only = bool(record.work.get("documents_only"))
        dest_dir = ctx.out_dir / "attachments" if ctx.keep_media and not documents_only else ctx.temp_dir
        allowed = set(ctx.file_filter.matching_indices(post)) if ctx.file_filter else None
        for index, item in enumerate(post.media):
            if allowed is not None and index not in allowed:
                continue
            needs_markdown = _needs_markdown(ctx, record, index, item)
            if documents_only:
                wanted = needs_markdown
            else:
                needs_transcript = ctx.transcribe and item.transcribable and not record.work.get("reused_transcript")
                wanted = ctx.keep_media or needs_transcript or needs_markdown
            if not wanted:
                continue
            stem = sanitize_filename(f"{ctx.channel.slug}_{post.id}" + (f"_{index + 1}" if len(post.media) > 1 else ""))
            if documents_only:
                kept = next(iter(sorted((ctx.out_dir / "attachments").glob(f"{glob.escape(stem)}.*"))), None)
                if kept is not None:
                    record.work.setdefault("existing_files", {})[index] = kept  # never cleaned up
                    continue
            if not item.downloadable:
                logger.warning(f"Post {post.id}: {item.kind} can't be downloaded from this source; skipping it.")
                record.frontmatter.setdefault("skipped_media", []).append(f"{item.kind} not downloadable")
                continue
            if ctx.max_size_mb and item.size and item.size > ctx.max_size_mb * 1024 * 1024:
                logger.warning(f"Post {post.id}: media is {item.size / 1048576:.0f} MB, over --max-size; skipping it.")
                record.frontmatter.setdefault("skipped_media", []).append(f"{item.kind} too large")
                continue
            ctx.progress(f"Downloading {item.kind} for post {post.id}…")
            path = ctx.source.download(post, item, dest_dir, stem)
            files[index] = path
            if documents_only:
                record.work.setdefault("temp_files", []).append(path)
            elif ctx.keep_media:
                record.attachments.append(path.relative_to(ctx.out_dir).as_posix())


def transcribe_media(ctx: StepContext, post: ChannelPost, item: MediaItem, source_path: Path, temp_files: List[Path]) -> str:
    """Transcribe one downloaded audio/video file (audio is extracted from video first) and clean the result."""
    audio_path = source_path
    if _is_video(item):
        audio_path = ctx.temp_dir / f"{source_path.stem}.mp3"
        ctx.progress(f"Extracting audio for post {post.id}…")
        media_utils.extract_audio(str(source_path), str(audio_path))
        temp_files.append(audio_path)
    ctx.progress(f"Transcribing post {post.id}…")
    text = ctx.transcriber.process_file(
        str(audio_path),
        chunk_length=ctx.chunk_size,
        overlap=ctx.overlap,
        force=ctx.force,
        skip_blocked=ctx.skip_blocked,
    )
    work_dir = Path("work_dir") / audio_path.stem
    shutil.rmtree(work_dir, ignore_errors=True)  # only reached on success; failures keep it for resuming
    return clean_transcript(text if isinstance(text, str) else str(text))


class TranscribeStep:
    """Transcribes audio/video media and stores the text as the `transcript` section."""

    name = "transcribe"

    def run(self, post: ChannelPost, record: PostRecord, ctx: StepContext) -> None:
        if not ctx.transcribe or ctx.transcriber is None or record.work.get("reused_transcript"):
            return
        files: Dict[int, Path] = record.work.get("files", {})
        texts: List[str] = []
        total_duration = 0.0
        for index, item in enumerate(post.media):
            if not item.transcribable or index not in files:
                continue
            texts.append(transcribe_media(ctx, post, item, files[index], record.work.setdefault("temp_files", [])))
            total_duration += item.duration or 0
        if not texts:
            return
        if len(texts) == 1:
            record.sections["transcript"] = texts[0]
        else:
            record.sections["transcript"] = "\n\n".join(f"### {i}\n\n{t}" for i, t in enumerate(texts, 1))
        record.frontmatter["transcribed"] = True
        record.frontmatter["transcription_model"] = settings.llm.model


def _language_instruction(ctx: StepContext) -> str:
    if not ctx.output_lang:
        return "Write in the same language as the content."
    return f"Write the entire output in {ctx.output_lang}."


def _content_for_llm(record: PostRecord) -> str:
    transcript = record.sections.get("transcript", "").strip()
    caption = record.sections.get("caption", "").strip()
    if transcript and caption:
        return f"Caption:\n{caption}\n\nTranscript:\n{transcript}"
    return transcript or caption


class SummaryStep:
    """Adds a short `summary` section at the top of the note (from the transcript, or the caption when there is none)."""

    name = "summary"
    MIN_CHARS = 300

    def run(self, post: ChannelPost, record: PostRecord, ctx: StepContext) -> None:
        if ctx.text_llm is None:
            return
        content = _content_for_llm(record)
        if len(content) < self.MIN_CHARS:
            return
        ctx.progress(f"Summarizing post {post.id}…")
        prompt = load_prompt("channel_summary_prompt.md").format(text=content, language_instruction=_language_instruction(ctx))
        summary = ctx.text_llm.generate(prompt)
        record.sections = {"summary": summary, **record.sections}
        record.frontmatter["summary_model"] = settings.llm.model


def taqrir_prompt(text: str, language_instruction: str, instruction: Optional[str] = None,
                  prompt_file: str = "channel_taqrir_prompt.md") -> str:
    """The taqrir prompt for a transcript (or, with channel_taqrir_text_prompt.md, a written post).

    `instruction` is the user's own guidance (a focus, what to leave out…), added as one more guideline."""
    guidance = language_instruction
    if instruction and instruction.strip():
        guidance += f"\n* Additional guidance from the user (follow it): {instruction.strip()}"
    return load_prompt(prompt_file).format(text=text, language_instruction=guidance)


class TaqrirStep:
    """Adds a `taqrir` section: the transcript (or, for text posts, the caption) restated as a structured, formulated exposition."""

    name = "taqrir"
    MIN_CHARS = 300  # for caption-only posts

    def run(self, post: ChannelPost, record: PostRecord, ctx: StepContext) -> None:
        if ctx.text_llm is None:
            return
        transcript = record.sections.get("transcript", "").strip()
        caption = record.sections.get("caption", "").strip()
        if transcript:
            prompt_file, source = "channel_taqrir_prompt.md", transcript
        elif len(caption) >= self.MIN_CHARS:
            prompt_file, source = "channel_taqrir_text_prompt.md", caption
        else:
            return
        ctx.progress(f"Writing taqrir for post {post.id}…")
        prompt = taqrir_prompt(source, _language_instruction(ctx), prompt_file=prompt_file)
        record.sections["taqrir"] = ctx.text_llm.generate(prompt)
        record.frontmatter["taqrir_model"] = settings.llm.model


class DocumentStep:
    """Turns each document of the post into a Markdown note under documents/ and lists them in the «اسناد» section.

    Notes converted on an earlier run are kept (and linked) unless they need redoing (--force, a missing note, a
    failed conversion, or scanned pages that --ocr can now read). A document that can't be converted doesn't fail
    the post: it is reported and retried on the next run."""

    name = "documents"

    def run(self, post: ChannelPost, record: PostRecord, ctx: StepContext) -> None:
        if not ctx.to_markdown:
            return
        from versline.services.ai import MissingAPIKeyError
        from versline.services.channel_archive import documents as docs

        ocr = ctx.ocr
        files: Dict[int, Path] = {**record.work.get("files", {}), **record.work.get("existing_files", {})}
        previous = previous_documents(record)
        owned = {entry["note"] for entry in previous.values() if entry.get("note")}
        taken: set = set()
        allowed = set(ctx.file_filter.matching_indices(post)) if ctx.file_filter else None
        entries: List[dict] = []
        links: List[str] = []
        errors: List[str] = record.work.setdefault("document_errors", [])
        post_note = record.note_path.as_posix() if record.note_path else None
        for index, item in enumerate(post.media):
            if (allowed is not None and index not in allowed) or not docs.is_convertible(item, ocr=ocr is not None):
                continue
            file_name = item.file_name or (files[index].name if index in files else f"{post.id}_{index + 1}")
            prev = previous.get(index)
            if index not in files:
                if prev and prev.get("note") and (ctx.out_dir / prev["note"]).is_file():
                    entries.append(prev)  # converted on an earlier run and nothing to redo
                    links.append(docs.note_link(prev["note"], prev.get("file") or file_name))
                    taken.add(prev["note"])
                continue
            rel = (prev or {}).get("note") or docs.unique_note_path(
                ctx.out_dir, docs.DOCUMENTS_DIR, file_name, post.id, owned, taken)
            taken.add(rel)
            path = files[index]
            try:
                source_file = path.resolve().relative_to(ctx.out_dir.resolve()).as_posix()
            except ValueError:
                source_file = None  # a temporary download: the note is all that stays
            ctx.progress(f"Converting {file_name} (post {post.id})…")
            try:
                result = docs.write_document_note(
                    ctx.out_dir, rel, path=path, ext=docs.document_extension(item), ocr=ocr, temp_dir=ctx.temp_dir,
                    channel=ctx.channel, post=post, item=item, file_name=file_name, post_note=post_note,
                    post_title=record.frontmatter.get("title"), source_file=source_file,
                )
            except (KeyboardInterrupt, MissingAPIKeyError):
                raise
            except Exception as exc:
                logger.warning(f"Post {post.id}: could not convert {file_name}: {exc}")
                record.frontmatter.setdefault("skipped_media", []).append(f"document not converted: {file_name}")
                errors.append(f"{post.id}: {file_name}: {exc}")
                entries.append({"index": index, "file": file_name, "error": str(exc)})
                continue
            entry = {"index": index, "file": file_name, "note": rel}
            if result.unread_pages:
                entry["unread_pages"] = result.unread_pages
            entries.append(entry)
            links.append(docs.note_link(rel, file_name))
        record.work["document_notes"] = entries
        if links:
            record.sections["documents"] = docs.documents_section(links)


# New steps (translate, tag, ...) are registered here and listed in the pipeline by name.
STEPS: Dict[str, Callable[[], PostStep]] = {
    "media": MediaStep,
    "transcribe": TranscribeStep,
    "summary": SummaryStep,
    "taqrir": TaqrirStep,
    "documents": DocumentStep,
}
DEFAULT_STEPS = ["media", "transcribe"]
