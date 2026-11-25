"""Timestamped transcripts kept per audio file, so later questions about the same file skip transcription.

A transcript is stored under the sha256 of the audio bytes. Other names for the same audio (e.g. a Telegram
message, ``tg:<chat>:<msg>``) are aliases that point at that key, so a file can be found again before it is
downloaded.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from loguru import logger

CACHE_VERSION = 1
_ALIASES = "aliases.json"


def cache_dir() -> Path:
    override = os.getenv("VERSLINE_CACHE_DIR")
    if override:
        base = Path(override).expanduser()
    elif os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "versline"
    else:
        base = Path(os.getenv("XDG_CACHE_HOME") or Path.home() / ".cache") / "versline"
    path = base / "transcripts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def file_key(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()[:32]


@dataclass
class Transcript:
    text: str
    segments: List[dict] = field(default_factory=list)  # [{start, end, text}] in seconds
    words: List[dict] = field(default_factory=list)  # [{start, end, word}] from the STT model, when it gives them
    duration: Optional[float] = None
    model: str = ""
    timestamp_method: str = ""
    skipped_ranges: List[dict] = field(default_factory=list)
    approximate: bool = False  # segment times estimated from text position, not aligned to the audio
    source: str = ""
    created: float = 0.0
    version: int = CACHE_VERSION

    @classmethod
    def from_dict(cls, data: dict) -> "Transcript":
        known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        return cls(**known)


def _path(key: str) -> Path:
    return cache_dir() / f"{key}.json"


def load(key: str) -> Optional[Transcript]:
    path = _path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != CACHE_VERSION or not data.get("text"):
            return None
        return Transcript.from_dict(data)
    except (OSError, ValueError, TypeError) as exc:
        logger.warning(f"Ignoring unreadable cached transcript {path}: {exc}")
        return None


def save(key: str, transcript: Transcript) -> None:
    path = _path(key)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(transcript), ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _aliases() -> Dict[str, str]:
    path = cache_dir() / _ALIASES
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def key_for_alias(alias: str) -> Optional[str]:
    key = _aliases().get(alias)
    return key if key and _path(key).exists() else None


def remember_alias(alias: str, key: str) -> None:
    aliases = _aliases()
    aliases[alias] = key
    path = cache_dir() / _ALIASES
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(aliases, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


_SENTENCE_END = re.compile(r"(?<=[.!?؟。])\s+|\n+")


def approximate_segments(text: str, duration: Optional[float], target_chars: int = 300) -> List[dict]:
    """Segments with times estimated from each piece's position in the text (used when alignment gave none)."""
    pieces: List[str] = []
    buf = ""
    for part in _SENTENCE_END.split(text):
        part = part.strip()
        if not part:
            continue
        buf = f"{buf} {part}".strip()
        if len(buf) >= target_chars:
            pieces.append(buf)
            buf = ""
    if buf:
        pieces.append(buf)
    total = sum(len(p) for p in pieces) or 1
    seconds = duration or total / 15  # ~15 characters of Persian speech per second
    segments, offset = [], 0
    for piece in pieces:
        start = seconds * offset / total
        offset += len(piece)
        segments.append({"start": round(start, 2), "end": round(seconds * offset / total, 2), "text": piece})
    return segments


def native_segments(audio: Path, transcriber, chunk_size: int, overlap: int, force: bool,
                    progress: Callable[[str], None]) -> tuple[List[dict], List[dict], str]:
    """(segments, words, method) from the STT model's own timestamps, aligned to the transcript already made.

    Only native timestamps are used (Versline's native_timestamps_only): the transcript comes from the cache the
    main pass just wrote, so this costs only the STT call. When the model gives none, ([], [], "") is returned and
    the caller estimates times instead of paying for the slower, coarser chunk-based alignment."""
    progress("Timestamping…")
    try:
        result = transcriber.process_file(
            str(audio), chunk_length=chunk_size, overlap=overlap, timestamped=True, reuse_transcript=True,
            native_timestamps_only=True, force_timestamps=force,
        )
    except Exception as exc:
        logger.warning(f"No native timestamps ({exc}); times will be estimated from the text. "
                       "Set VERSLINE_TRANSCRIPTION_TIMESTAMP_MODEL to an STT model with timestamps "
                       "(e.g. elevenlabs/scribe-v2 on OpenRouter, whisper-1 or gpt-4o-transcribe on OpenAI).")
        return [], [], ""
    if not isinstance(result, dict):
        return [], [], ""
    segments = [{"start": float(s["start"]), "end": float(s["end"]), "text": str(s["text"])}
                for s in result.get("segments") or [] if str(s.get("text", "")).strip()]
    words = [{"start": float(w["start"]), "end": float(w["end"]), "word": str(w.get("word") or w.get("text") or "")}
             for w in result.get("words") or [] if "start" in w and "end" in w]
    return segments, words, str(result.get("timestamp_method") or "")


def get_or_transcribe(
    audio: Path,
    transcriber,
    *,
    key: Optional[str] = None,
    force: bool = False,
    chunk_size: int = 900,
    overlap: int = 180,
    skip_blocked: bool = False,
    progress: Callable[[str], None] = lambda message: None,
) -> tuple[str, Transcript]:
    """(key, transcript) for an audio file: the cached one, or a fresh timestamped transcription that is then cached."""
    from versline.config import settings
    from versline.services import media
    from versline.services.channel_archive.steps import clean_transcript

    key = key or file_key(audio)
    if not force:
        cached = load(key)
        if cached is not None:
            progress("Using the saved transcript")
            return key, cached
    progress("Transcribing…")
    text = transcriber.process_file(
        str(audio), chunk_length=chunk_size, overlap=overlap, force=force, skip_blocked=skip_blocked,
    )
    text = clean_transcript(text if isinstance(text, str) else str(text))
    skipped = list(getattr(transcriber, "skipped_ranges", []) or [])
    segments, words, method = native_segments(audio, transcriber, chunk_size, overlap, force, progress)
    duration = media.get_audio_duration(str(audio))
    approximate = not segments
    if approximate:
        segments = approximate_segments(text, duration)
    transcript = Transcript(
        text=text,
        segments=[{"start": float(s["start"]), "end": float(s["end"]), "text": str(s["text"])} for s in segments],
        duration=duration,
        words=words,
        model=settings.llm.model,
        timestamp_method=method,
        skipped_ranges=skipped,
        approximate=approximate,
        source=Path(audio).name,
        created=time.time(),
    )
    save(key, transcript)
    return key, transcript
