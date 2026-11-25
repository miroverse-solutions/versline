"""Questions about a recorded talk: its taqrir, or finding the passages a listener remembers.

Both work on a cached timestamped transcript (services.transcript_cache), so asking again about the same file
costs one text-model call, not another transcription.
"""
from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from loguru import logger

from versline.core.prompts import load_prompt
from versline.services.transcript_cache import Transcript

# Longer inputs are split into overlapping windows (~45 minutes of Persian speech per window).
FIND_WINDOW_CHARS = 60_000
FIND_WINDOW_OVERLAP = 3_000
TAQRIR_PART_CHARS = 80_000
MATCH_THRESHOLD = 0.6
REFINE_PAD = 10.0

REFINE_NOTE = (
    "This clip is one passage of a longer talk. Transcribe it with the greatest possible accuracy. "
    "Write Arabic (Quranic verses, narrations, supplications, quoted sayings) exactly as spoken, in Arabic script, "
    "with diacritics wherever they are clearly pronounced. Do not add anything that is not spoken."
)


# -- time --

def clock(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def parse_clock(value) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    match = re.fullmatch(r"\s*(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)\s*", str(value or ""))
    if not match:
        return None
    h, m, s = match.groups()
    return int(h or 0) * 3600 + int(m) * 60 + float(s)


# -- text normalisation and quote matching --

_DIACRITICS = re.compile(r"[ً-ٰٟۖ-ۭـ]")
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ؤ": "و", "ئ": "ی",
                          "‌": " "})


def normalize(text: str) -> str:
    text = _DIACRITICS.sub("", text.translate(_LETTERS)).lower()
    return " ".join(_NON_WORD.sub(" ", text).split())


def _tokens(segments: Sequence[dict]) -> Tuple[List[str], List[int]]:
    words: List[str] = []
    owner: List[int] = []
    for index, seg in enumerate(segments):
        for word in normalize(seg.get("text", "")).split():
            words.append(word)
            owner.append(index)
    return words, owner


def locate_quote(quote: str, segments: Sequence[dict], hint: Optional[float] = None) -> Optional[Tuple[int, int, float]]:
    """(first segment, last segment, score) of the stretch of transcript that best contains `quote`, or None.

    Score is the share of the quote's words found (as a multiset) in a window of the same length, so small
    differences (a misspelt word, diacritics, punctuation) still match while an invented quote does not.
    Among equally good windows, the one nearest `hint` (seconds) wins."""
    q = normalize(quote).split()
    words, owner = _tokens(segments)
    if not q or not words:
        return None
    size = min(len(q), len(words))
    need = Counter(q)
    window: Counter = Counter()
    overlap = 0
    best: Optional[Tuple[float, float, int]] = None  # (score, -distance, start)
    for i, word in enumerate(words):
        if window[word] < need[word]:
            overlap += 1
        window[word] += 1
        if i >= size:
            old = words[i - size]
            window[old] -= 1
            if window[old] < need[old]:
                overlap -= 1
        if i >= size - 1:
            start = i - size + 1
            score = overlap / len(q)
            distance = abs(segments[owner[start]]["start"] - hint) if hint is not None else 0.0
            candidate = (round(score, 3), -distance, start)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
    if best is None or best[0] < MATCH_THRESHOLD:
        return None
    start = best[2]
    end = min(start + size - 1, len(words) - 1)
    return owner[start], owner[end], best[0]


# -- LLM output --

def parse_json(text: str) -> dict:
    """The first JSON object in a model reply (code fences and chatter around it are ignored)."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except ValueError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        return json.loads(cleaned[start:end + 1])
    raise ValueError("No JSON object in the model's reply")


# -- finding passages --

@dataclass
class Passage:
    quote: str
    start: float
    end: float
    attribution: str = ""
    context: str = ""
    relevance: str = "medium"
    score: float = 0.0
    refined: str = ""  # the passage re-transcribed on its own, when refining
    clip: Optional[Path] = None

    @property
    def span(self) -> str:
        return f"{clock(self.start)}–{clock(self.end)}"


_RANK = {"high": 0, "medium": 1, "low": 2}


def render_timed(segments: Sequence[dict]) -> str:
    return "\n".join(f"[{clock(s['start'])}] {s['text'].strip()}" for s in segments if s.get("text", "").strip())


def windows(segments: Sequence[dict], max_chars: int = FIND_WINDOW_CHARS, overlap_chars: int = FIND_WINDOW_OVERLAP) -> List[List[dict]]:
    result: List[List[dict]] = []
    current: List[dict] = []
    size = 0
    for seg in segments:
        length = len(seg.get("text", "")) + 12
        if current and size + length > max_chars:
            result.append(current)
            tail: List[dict] = []
            tail_size = 0
            for prev in reversed(current):
                tail_size += len(prev.get("text", "")) + 12
                if tail_size > overlap_chars:
                    break
                tail.insert(0, prev)
            current, size = list(tail), tail_size if tail else 0
        current.append(seg)
        size += length
    if current:
        result.append(current)
    return result


def _language_instruction(output_lang: str) -> str:
    return f"written in {output_lang}" if output_lang else "written in the language of the request"


def find_passages(
    llm,
    transcript: Transcript,
    query: str,
    output_lang: str = "",
    progress: Callable[[str], None] = lambda message: None,
) -> List[Passage]:
    """Passages of the transcript matching the listener's description, with times taken from the transcript itself."""
    segments = transcript.segments
    parts = windows(segments)
    found: List[Passage] = []
    for number, part in enumerate(parts, 1):
        if len(parts) > 1:
            progress(f"Searching part {number}/{len(parts)}…")
        prompt = load_prompt("audio_find_prompt.md").format(
            query=query.strip(), transcript=render_timed(part), language_instruction=_language_instruction(output_lang),
        )
        reply = llm.generate(prompt)
        try:
            items = parse_json(reply).get("passages") or []
        except ValueError as exc:
            logger.warning(f"Could not read the model's answer for part {number}: {exc}")
            continue
        for item in items:
            passage = _verified(item, segments, transcript.words)
            if passage is not None:
                found.append(passage)
    return _dedupe(found)


WORD_SEARCH_PAD = 20.0


def word_bounds(quote: str, words: Sequence[dict], start: float, end: float) -> Optional[Tuple[float, float]]:
    """Exact start/end of the quote from the STT model's word times, searched near the segments it was found in.

    The words are what the STT model heard, so they may differ a little from the transcript; when they differ
    too much, None is returned and the segment times are kept."""
    near = [{"start": float(w["start"]), "end": float(w["end"]), "text": str(w.get("word", ""))}
            for w in words if start - WORD_SEARCH_PAD <= float(w["start"]) <= end + WORD_SEARCH_PAD]
    located = locate_quote(quote, near, hint=start) if near else None
    if located is None:
        return None
    first, last, _ = located
    return near[first]["start"], near[last]["end"]


def _verified(item: dict, segments: Sequence[dict], words: Sequence[dict] = ()) -> Optional[Passage]:
    quote = str(item.get("quote") or "").strip()
    if not quote:
        return None
    hint = parse_clock(item.get("start"))
    located = locate_quote(quote, segments, hint)
    if located is None:
        logger.warning(f"Dropped a passage the transcript does not contain: {quote[:80]}…")
        return None
    first, last, score = located
    start, end = float(segments[first]["start"]), float(segments[last]["end"])
    exact = word_bounds(quote, words, start, end) if words else None
    if exact is not None:
        start, end = exact
    relevance = str(item.get("relevance") or "medium").lower()
    return Passage(
        quote=quote,
        start=start,
        end=end,
        attribution=str(item.get("attribution") or "").strip(),
        context=str(item.get("context") or "").strip(),
        relevance=relevance if relevance in _RANK else "medium",
        score=score,
    )


def _dedupe(passages: List[Passage]) -> List[Passage]:
    """Drop passages that overlap a better one (windows overlap, so one passage can be found twice)."""
    kept: List[Passage] = []
    for p in sorted(passages, key=lambda p: (_RANK[p.relevance], -p.score, p.start)):
        if any(p.start < k.end and k.start < p.end for k in kept):
            continue
        kept.append(p)
    return sorted(kept, key=lambda p: p.start)


def refine_passage(transcriber_factory: Callable[[str], object], audio: Path, passage: Passage, work: Path,
                   query: str = "") -> str:
    """Re-transcribe just the passage (with some padding) for a more exact text, e.g. of an Arabic narration."""
    from versline.services.media import clip_audio

    start = max(0.0, passage.start - REFINE_PAD)
    end = passage.end + REFINE_PAD
    clip = work / f"refine_{int(start)}_{int(end)}.mp3"
    clip_audio(audio, start, end, clip)
    note = REFINE_NOTE + (f"\nThe listener is looking for: {query.strip()}" if query.strip() else "")
    transcriber = transcriber_factory(note)
    try:
        text = transcriber.process_file(str(clip), chunk_length=max(60, int(end - start) + 30), overlap=0, force=True)
    finally:
        shutil.rmtree(Path("work_dir") / clip.stem, ignore_errors=True)
    from versline.services.channel_archive.steps import clean_transcript

    return clean_transcript(text if isinstance(text, str) else str(text))


# -- taqrir --

def write_taqrir(llm, text: str, instruction: Optional[str] = None, output_lang: str = "",
                 progress: Callable[[str], None] = lambda message: None) -> str:
    """The taqrir of a whole talk; very long transcripts are written part by part."""
    from versline.services.channel_archive.steps import taqrir_prompt

    language = f"Write the entire output in {output_lang}." if output_lang else "Write in the same language as the content."
    parts = _split_text(text, TAQRIR_PART_CHARS)
    if len(parts) == 1:
        progress("Writing the taqrir…")
        return llm.generate(taqrir_prompt(text, language, instruction))
    sections = []
    for number, part in enumerate(parts, 1):
        progress(f"Writing the taqrir, part {number}/{len(parts)}…")
        note = f"This is part {number} of {len(parts)} of one talk; write the taqrir of this part only."
        guidance = f"{instruction.strip()}\n{note}" if instruction and instruction.strip() else note
        sections.append(llm.generate(taqrir_prompt(part, language, guidance)))
    return "\n\n".join(sections)


def _split_text(text: str, limit: int) -> List[str]:
    if len(text) <= limit:
        return [text]
    count = -(-len(text) // limit)
    target = len(text) / count
    parts, start = [], 0
    while start < len(text):
        end = int(start + target)
        if end >= len(text) - limit * 0.1:
            parts.append(text[start:])
            break
        cut = text.rfind("\n", start + int(target * 0.7), end)
        if cut <= start:
            cut = text.rfind(" ", start + int(target * 0.7), end)
        cut = cut if cut > start else end
        parts.append(text[start:cut])
        start = cut
    return [p.strip() for p in parts if p.strip()]


# -- notes --

@dataclass
class FindResult:
    query: str
    passages: List[Passage] = field(default_factory=list)
    approximate: bool = False


def run_find(
    llm,
    transcript: Transcript,
    query: str,
    *,
    audio: Optional[Path] = None,
    clips_dir: Optional[Path] = None,
    clip_prefix: str = "clip",
    refine: bool = False,
    transcriber_factory: Optional[Callable[[str], object]] = None,
    work: Optional[Path] = None,
    output_lang: str = "",
    progress: Callable[[str], None] = lambda message: None,
) -> FindResult:
    """Find the passages, then (with the audio at hand) re-transcribe each one and cut it out as a clip."""
    from versline.services.media import clip_audio
    from versline.utils.common import sanitize_filename

    progress("Searching the transcript…")
    result = FindResult(query=query, approximate=transcript.approximate)
    result.passages = find_passages(llm, transcript, query, output_lang=output_lang, progress=progress)
    if audio is None:
        return result
    for number, passage in enumerate(result.passages, 1):
        if refine and transcriber_factory is not None and work is not None and not transcript.approximate:
            progress(f"Re-transcribing passage {number}/{len(result.passages)}…")
            try:
                passage.refined = refine_passage(transcriber_factory, audio, passage, work, query)
            except Exception as exc:  # the passage from the full transcript is still usable
                logger.warning(f"Could not re-transcribe passage {number}: {exc}")
        if clips_dir is not None:
            progress(f"Cutting clip {number}/{len(result.passages)}…")
            pad = 2.0 if not transcript.approximate else 30.0
            name = sanitize_filename(f"{clip_prefix} {clock(passage.start).replace(':', '-')}.mp3")
            try:
                passage.clip = Path(clip_audio(audio, max(0.0, passage.start - pad), passage.end + pad, clips_dir / name))
            except RuntimeError as exc:
                logger.warning(f"Could not cut a clip for passage {number}: {exc}")
    return result


def _blockquote(text: str) -> str:
    return "\n".join(f"> {line}" if line.strip() else ">" for line in text.strip().splitlines())


def render_find_section(result: FindResult, clip_link: Callable[[Path], str] = lambda p: f"![[{p.name}]]") -> str:
    lines = [f"## {result.query.strip().splitlines()[0][:120]}", ""]
    if len(result.query.strip().splitlines()) > 1 or len(result.query.strip()) > 120:
        lines += [_blockquote(result.query), ""]
    if result.approximate:
        lines += ["> [!warning] زمان‌ها تقریبی است؛ این فایل بدون هم‌ترازی زمانی پیاده شده است.", ""]
    if not result.passages:
        lines += ["چیزی مطابق این درخواست در فایل پیدا نشد.", ""]
    for number, p in enumerate(result.passages, 1):
        title = f"### {number}. {p.span}"
        if p.attribution:
            title += f" — {p.attribution}"
        lines += [title, ""]
        if p.context:
            lines += [f"*{p.context}*", ""]
        lines += [_blockquote(p.refined or p.quote), ""]
        if p.refined:
            lines += ["<details><summary>متن در پیاده‌سازی کامل</summary>", "", p.quote, "", "</details>", ""]
        if p.clip is not None:
            lines += [clip_link(p.clip), ""]
    return "\n".join(lines).rstrip() + "\n"


def render_find_telegram(result: FindResult) -> str:
    if not result.passages:
        return f"چیزی مطابق «{result.query.strip()[:200]}» در فایل پیدا نشد."
    blocks = []
    for number, p in enumerate(result.passages, 1):
        head = f"**{number}. {p.span}**" + (f" — {p.attribution}" if p.attribution else "")
        body = [head]
        if p.context:
            body.append(f"_{p.context}_")
        body.append(_blockquote(p.refined or p.quote))
        blocks.append("\n".join(body))
    if result.approximate:
        blocks.append("_زمان‌ها تقریبی است._")
    return "\n\n".join(blocks)


def skipped_warnings(media: Path, output: Path, ranges: List[dict]) -> List[dict]:
    """Bridge warnings (as the transcribe tool reports them) for parts of the audio the transcript is missing."""
    if not ranges:
        return []
    from versline.commands.transcribe import skipped_message

    return [{
        "kind": "skipped_ranges", "input": str(media), "output": str(output),
        "message": skipped_message(Path(media).name, Path(output), ranges), "ranges": ranges,
    }]


def append_section(note: Path, section: str, title: str) -> None:
    """Add a section to a note, creating it (with a title) when it does not exist yet."""
    note.parent.mkdir(parents=True, exist_ok=True)
    if note.exists():
        existing = note.read_text(encoding="utf-8").rstrip()
        note.write_text(f"{existing}\n\n{section}", encoding="utf-8")
    else:
        note.write_text(f"# {title}\n\n{section}", encoding="utf-8")
