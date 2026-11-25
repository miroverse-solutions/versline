"""Requests left in a Telegram chat as replies to recorded talks, answered on demand.

The listener keeps talks in a chat of their own (Saved Messages, or a private group/channel) and replies to one
with a text or voice message: "تقریر کن", or "the narration he read from Imam Sadiq about patience". A run reads
the chat from where the last run stopped, answers each new request (a taqrir, or the passages found with their
times and audio clips) as a reply, and writes the same answer to a note in the vault.

Only the account's own messages count as requests, so other members of a shared group are ignored. Replies sent
by Versline start with MARK, which keeps them from being read as requests later.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from versline.core.prompts import load_prompt
from versline.services import transcript_cache
from versline.services.audio_points import (
    append_section,
    parse_json,
    render_find_section,
    render_find_telegram,
    run_find,
    skipped_warnings,
    write_taqrir,
)
from versline.utils.common import sanitize_filename

MARK = "🤖"
MAX_ATTEMPTS = 3
STATE_FILE = "telegram_requests.json"
_TAQRIR_WORDS = ("تقریر", "taqrir", "کل سخنرانی", "کل جلسه", "کلش", "همه‌اش", "همش")


# -- state --

class RequestState:
    """Per chat: the newest message already read, and requests that failed (retried up to MAX_ATTEMPTS)."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self.data: Dict[str, dict] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def chat(self, chat_id: int) -> dict:
        entry = self.data.setdefault(str(chat_id), {})
        entry.setdefault("last_id", 0)
        entry.setdefault("failed", {})
        return entry

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)


def default_state_path() -> Path:
    from versline.userconfig import user_config_dir

    return user_config_dir() / STATE_FILE


# -- what a request asks for --

def classify(llm, text: str) -> dict:
    """{'mode': 'taqrir'|'find', 'query', 'instruction'} for the listener's request."""
    try:
        data = parse_json(llm.generate(load_prompt("telegram_request_prompt.md").format(request=text.strip())))
        mode = str(data.get("mode") or "").strip().lower()
        if mode in ("taqrir", "find"):
            query = str(data.get("query") or "").strip() or text.strip()
            return {"mode": mode, "query": query, "instruction": str(data.get("instruction") or "").strip()}
    except Exception as exc:
        logger.warning(f"Could not classify the request, guessing from its words: {exc}")
    lowered = text.lower()
    if any(word in lowered for word in _TAQRIR_WORDS) and len(text) < 200:
        return {"mode": "taqrir", "query": "", "instruction": text.strip()}
    return {"mode": "find", "query": text.strip(), "instruction": ""}


def _text_of(msg: Any) -> str:
    return (getattr(msg, "message", None) or "").strip()


def _is_spoken(msg: Any) -> bool:
    return bool(getattr(msg, "voice", None) or getattr(msg, "video_note", None) or getattr(msg, "audio", None))


def is_request(msg: Any) -> bool:
    """The account's own reply (text or voice) that Versline did not write itself."""
    if not getattr(msg, "out", False) or not getattr(msg, "reply_to_msg_id", None):
        return False
    if getattr(msg, "action", None) is not None or _text_of(msg).startswith(MARK):
        return False
    return bool(_text_of(msg)) or _is_spoken(msg)


# -- processing --

@dataclass
class RequestOptions:
    output_dir: Path
    temp_dir: Path
    lookback_days: int = 3
    limit: Optional[int] = None
    clip: bool = True
    refine: bool = True
    reply: bool = True
    output_lang: str = ""
    skip_blocked: bool = False
    dry_run: bool = False


@dataclass
class RequestSummary:
    processed: int = 0
    failed: int = 0
    outputs: List[Path] = field(default_factory=list)
    warnings: List[dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    pending: List[dict] = field(default_factory=list)  # dry run: what would be answered


class RequestProcessor:
    def __init__(self, source, llm, transcriber, transcriber_factory: Callable[[str], Any], options: RequestOptions,
                 state: RequestState, progress: Callable[[str], None] = lambda message: None):
        self.source = source
        self.llm = llm
        self.transcriber = transcriber
        self.factory = transcriber_factory
        self.opts = options
        self.state = state
        self.progress = progress

    # -- the chat --

    def run(self, chat_ref: str) -> RequestSummary:
        from versline.services.channel_archive.sources.telegram import chat_kind, display_name

        summary = RequestSummary()
        entity = self.source.entity_of(chat_ref)
        self.entity = entity
        self.chat_id = self.source.peer_id(entity)
        self.kind = chat_kind(entity)
        self.username = getattr(entity, "username", None)
        self.title = display_name(entity) or str(self.chat_id)
        entry = self.state.chat(self.chat_id)
        since = None if entry["last_id"] else datetime.now(timezone.utc) - timedelta(days=self.opts.lookback_days)
        self.progress("Reading new messages…")
        new = self.source.messages_after(entity, entry["last_id"], since, self.opts.limit)
        retry_ids = [int(i) for i, n in entry["failed"].items() if n < MAX_ATTEMPTS]
        retry = self.source.get_messages(entity, retry_ids) if retry_ids and not self.opts.dry_run else []
        queue = {m.id: m for m in [*retry, *new]}
        requests = [queue[i] for i in sorted(queue) if is_request(queue[i])]
        newest = max([entry["last_id"], *(m.id for m in new)])

        for number, msg in enumerate(requests, 1):
            self.progress(f"Request {number}/{len(requests)} (message {msg.id})…")
            if self.opts.dry_run:
                summary.pending.append({"id": msg.id, "reply_to": msg.reply_to_msg_id,
                                        "text": _text_of(msg) or "(voice)"})
                continue
            try:
                outputs = self.handle(msg, summary)
            except Exception as exc:
                attempts = entry["failed"].get(str(msg.id), 0) + 1
                entry["failed"][str(msg.id)] = attempts
                summary.failed += 1
                summary.errors.append(f"message {msg.id}: {exc}")
                logger.error(f"Request in message {msg.id} failed ({attempts}/{MAX_ATTEMPTS}): {exc}")
                again = "؛ دفعه‌ی بعد دوباره امتحان می‌شود" if attempts < MAX_ATTEMPTS else ""
                self._reply(msg.id, f"⚠️ انجام نشد{again}: {exc}")
            else:
                entry["failed"].pop(str(msg.id), None)
                if outputs is not None:
                    summary.processed += 1
                    summary.outputs.extend(outputs)
            entry["last_id"] = max(entry["last_id"], msg.id if msg.id in {m.id for m in new} else 0)
            self.state.save()
        if not self.opts.dry_run:
            entry["last_id"] = newest
            self.state.save()
        return summary

    # -- one request --

    def handle(self, msg: Any, summary: RequestSummary) -> Optional[List[Path]]:
        found = self.source.get_messages(self.entity, [msg.reply_to_msg_id])
        target = found[0] if found else None
        item = self.source._media_item(target) if target is not None else None
        if item is None or not item.transcribable:
            return None  # an ordinary reply, not to a talk
        work = Path(self.opts.temp_dir) / f"{abs(self.chat_id)}_{msg.id}"
        work.mkdir(parents=True, exist_ok=True)
        try:
            request = self._request_text(msg, work)
            if not request:
                return None
            intent = classify(self.llm, request)
            logger.info(f"Message {msg.id}: {intent['mode']} — {intent['query'] or intent['instruction'] or '(whole talk)'}")
            stem = self._stem(target, item)
            alias = f"tg:{self.chat_id}:{target.id}"
            key = transcript_cache.key_for_alias(alias)
            transcript = transcript_cache.load(key) if key else None
            audio = None
            if transcript is None or (intent["mode"] == "find" and (self.opts.clip or self.opts.refine)):
                audio = self._download(target, item, work)
            if transcript is None:
                key, transcript = transcript_cache.get_or_transcribe(
                    audio, self.transcriber, skip_blocked=self.opts.skip_blocked, progress=self.progress)
                transcript_cache.remember_alias(alias, key)
            if intent["mode"] == "taqrir":
                outputs = self._taqrir(msg, target, stem, transcript, intent)
            else:
                outputs = self._find(msg, target, stem, transcript, intent, audio, work)
            if transcript.skipped_ranges:
                summary.warnings.extend(skipped_warnings(Path(item.file_name or stem), outputs[0], transcript.skipped_ranges))
            return outputs
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _request_text(self, msg: Any, work: Path) -> str:
        text = _text_of(msg)
        if not _is_spoken(msg):
            return text
        self.progress("Transcribing the voice request…")
        path = self.source.download_message(msg, work, f"request_{msg.id}")
        try:
            spoken = self.transcriber.process_file(str(path), chunk_length=900, overlap=0, force=True)
        finally:
            shutil.rmtree(Path("work_dir") / path.stem, ignore_errors=True)
        spoken = spoken if isinstance(spoken, str) else str(spoken)
        return "\n".join(part for part in (text, spoken.strip()) if part)

    def _download(self, target: Any, item: Any, work: Path) -> Path:
        from versline.services import media

        self.progress(f"Downloading the {item.kind}…")
        path = self.source.download_message(target, work, f"talk_{target.id}")
        if item.kind in ("video", "video_note") or (item.mime or "").startswith("video/"):
            audio = work / f"talk_{target.id}.mp3"
            media.extract_audio(str(path), str(audio))
            return audio
        return path

    def _stem(self, target: Any, item: Any) -> str:
        name = Path(item.file_name).stem if item.file_name else ""
        return sanitize_filename(name or f"{self.title} {target.id}")[:120]

    def _link(self, msg_id: int) -> Optional[str]:
        if self.kind in ("user", "group", None):
            return None
        if self.username:
            return f"https://t.me/{self.username}/{msg_id}"
        return f"https://t.me/c/{getattr(self.entity, 'id', abs(self.chat_id))}/{msg_id}"

    def _source_line(self, target: Any) -> str:
        link = self._link(target.id)
        where = f"[{self.title} / {target.id}]({link})" if link else f"{self.title} / {target.id}"
        date = getattr(target, "date", None)
        return f"منبع: {where}" + (f" — {date:%Y-%m-%d}" if date else "")

    def _taqrir(self, msg, target, stem, transcript, intent) -> List[Path]:
        text = write_taqrir(self.llm, transcript.text, intent["instruction"], self.opts.output_lang, progress=self.progress)
        note = Path(self.opts.output_dir) / f"{stem} - تقریر.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# {stem}", "", self._source_line(target)]
        if intent["instruction"]:
            lines += ["", f"> [!question] درخواست\n> {intent['instruction']}"]
        note.write_text("\n".join(lines) + "\n\n" + text.strip() + "\n", encoding="utf-8")
        self._reply(msg.id, f"**تقریر**\n\n{text.strip()}")
        return [note]

    def _find(self, msg, target, stem, transcript, intent, audio, work) -> List[Path]:
        out_dir = Path(self.opts.output_dir)
        note = out_dir / f"{stem} - نکته‌ها.md"
        result = run_find(
            self.llm, transcript, intent["query"], audio=audio,
            clips_dir=out_dir if self.opts.clip else None, clip_prefix=note.stem, refine=self.opts.refine,
            transcriber_factory=self.factory, work=work, output_lang=self.opts.output_lang, progress=self.progress,
        )
        if not note.exists():
            note.parent.mkdir(parents=True, exist_ok=True)
            note.write_text(f"# {stem}\n\n{self._source_line(target)}\n", encoding="utf-8")
        append_section(note, render_find_section(result), stem)
        self._reply(msg.id, render_find_telegram(result))
        clips = [p.clip for p in result.passages if p.clip is not None]
        for number, passage in enumerate(result.passages, 1):
            if passage.clip is not None:
                self._reply(msg.id, f"{number}. {passage.span}", file=passage.clip)
        return [note, *clips]

    def _reply(self, msg_id: int, text: str, file: Optional[Path] = None) -> None:
        if not self.opts.reply:
            return
        from versline.services.telegram_format import TelegramParseMode, split_message

        mode = TelegramParseMode("markdown")
        try:
            if file is not None:
                self.source.send(self.entity, f"{MARK} {text}", parse_mode=mode, file=str(file), reply_to=msg_id)
                return
            for part in split_message(f"{MARK} {text}", limit=4000):
                part = part if part.startswith(MARK) else f"{MARK} {part}"
                self.source.send(self.entity, part, parse_mode=mode, reply_to=msg_id, link_preview=False)
        except Exception as exc:  # the note in the vault is still written
            logger.warning(f"Could not reply in Telegram to message {msg_id}: {exc}")
