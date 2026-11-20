"""Paced bulk sending of one message (typed or forwarded) to a list of Telegram recipients.

The Telegram side is behind a small source interface (see TelegramSource): list_contacts, iter_dialogs, entity_of,
send, forward, get_messages, album_of, so everything here can be tested with a fake source.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from versline.services import telegram_format
from versline.services.channel_archive.filters import normalize_fa
from versline.services.channel_archive.sources.telegram import SendError, display_name, user_row
from versline.services.telegram_people import Recipient, phone_key

CAPTION_LIMIT = 1024
DAY = 86400


class StopSending(Exception):
    """Sending must stop now (the account is limited, a flood wait is too long, the daily cap is reached)."""


# -- resolution -------------------------------------------------------------


@dataclass
class Resolved:
    recipient: Recipient
    entity: Any
    entity_id: int
    row: dict

    @property
    def key(self) -> str:
        return f"{self.recipient.kind}:{self.recipient.ref}"

    @property
    def label(self) -> str:
        return self.row.get("name") or self.recipient.label


def _row_of(entity: Any) -> dict:
    from versline.services.channel_archive.sources.telegram import chat_kind

    if chat_kind(entity) == "user":
        return user_row(entity)
    return {"id": entity.id, "name": display_name(entity) or str(entity.id), "username": getattr(entity, "username", "") or "",
            "first_name": "", "last_name": "", "phone": "", "type": chat_kind(entity) or ""}


def resolve_recipients(source: Any, recipients: List[Recipient], lookup_delay: float = 1.5,
                       sleep: Callable[[float], None] = time.sleep) -> Tuple[List[Resolved], List[Tuple[Recipient, str]]]:
    """Match every recipient to a chat. Phones and names are only looked up among your contacts (and private chats);
    usernames and ids may also be looked up on Telegram. Returns (resolved, [(recipient, reason skipped)])."""
    contacts = source.list_contacts(with_entity=True)
    by_phone: Dict[str, dict] = {}
    by_id: Dict[int, Any] = {}
    by_username: Dict[str, Any] = {}
    by_name: Dict[str, List[Any]] = {}

    def add(entity: Any, row: dict, name_index: bool) -> None:
        for ident in {row["id"], getattr(entity, "id", row["id"])}:
            by_id.setdefault(ident, entity)
        if row.get("phone"):
            by_phone.setdefault(phone_key(row["phone"]), entity)
        if row.get("username"):
            by_username.setdefault(row["username"].lower(), entity)
        if name_index and row.get("name"):
            bucket = by_name.setdefault(normalize_fa(row["name"]), [])
            if not any(getattr(e, "id", None) == getattr(entity, "id", None) for e in bucket):
                bucket.append(entity)

    for row in contacts:
        add(row["entity"], row, True)
    dialogs_loaded = False

    def load_dialogs() -> None:
        """Read the chat list only when your contacts could not answer (a full scan is slow and noisy)."""
        nonlocal dialogs_loaded
        dialogs_loaded = True
        for row in source.iter_dialogs(with_entity=True):
            add(row["entity"], {**row, "id": row["id"], "name": row.get("title")}, row.get("kind") in ("user", "bot"))

    def find(r: Recipient):
        if r.kind == "phone":
            return by_phone.get(phone_key(r.ref)), "phone number is not among your contacts"
        if r.kind == "name":
            matches = by_name.get(normalize_fa(r.ref), [])
            if len(matches) == 1:
                return matches[0], ""
            return None, "several contacts have this name" if matches else "no contact or private chat with this name"
        found = by_id.get(int(r.ref)) if r.kind == "id" else by_username.get(r.ref.lower())
        return found, ""

    resolved: List[Resolved] = []
    skipped: List[Tuple[Recipient, str]] = []
    seen: Dict[int, str] = {}
    looked_up = False
    for r in recipients:
        entity, reason = find(r)
        if entity is None and r.kind != "phone" and not dialogs_loaded:
            load_dialogs()
            entity, reason = find(r)
        if entity is None and r.kind in ("id", "username"):
            try:
                if looked_up:
                    sleep(lookup_delay)
                looked_up = True
                entity = source.entity_of(int(r.ref) if r.kind == "id" else r.ref)
            except Exception as exc:
                reason = f"not found on Telegram ({type(exc).__name__}: {exc})"[:160]
        if entity is None:
            skipped.append((r, reason))
            continue
        entity_id = getattr(entity, "id", 0)
        if entity_id in seen:
            skipped.append((r, f"duplicate of {seen[entity_id]}"))
            continue
        row = _row_of(entity)
        seen[entity_id] = r.label
        resolved.append(Resolved(recipient=r, entity=entity, entity_id=entity_id, row=row))
    return resolved, skipped


# -- message ------------------------------------------------------------------


PLACEHOLDER = re.compile(r"\{(\w+)\}")


def placeholders(item: Resolved) -> Dict[str, str]:
    row, r = item.row, item.recipient
    name = row.get("name") or r.name or r.ref
    values = {k.lower(): v for k, v in r.fields.items() if v}
    values.update({
        "name": name,
        "first_name": row.get("first_name") or name.split(" ")[0],
        "last_name": row.get("last_name") or "",
        "username": row.get("username") or "",
        "phone": row.get("phone") or "",
        "id": str(item.entity_id),
    })
    return values


def render(text: str, values: Dict[str, str], fmt: str = "markdown") -> str:
    """Fill {placeholders}; unknown ones are left as typed. In HTML mode the values are escaped."""
    def fill(m: "re.Match") -> str:
        key = m.group(1).lower()
        if key not in values:
            return m.group(0)
        return html.escape(values[key], quote=False) if fmt == "html" else values[key]

    return PLACEHOLDER.sub(fill, text)


@dataclass
class ForwardRef:
    chat: Any  # a chat reference for source.entity_of
    msg_id: Optional[int]  # None = the latest message (me:last)
    single: bool = False
    raw: str = ""


def parse_forward_ref(value: str) -> ForwardRef:
    """t.me/<name>/<id>, t.me/c/<id>/<id>, either with ?single, or '<chat>:<id>' / 'me:last' (any chat reference)."""
    raw = value.strip()
    single = bool(re.search(r"[?&]single\b", raw))
    clean = raw.split("?")[0].rstrip("/")
    m = re.match(r"^(?:https?://)?t\.me/c/(\d+)(?:/\d+)?/(\d+)$", clean)
    if m:
        return ForwardRef(int(f"-100{m.group(1)}"), int(m.group(2)), single, raw)
    m = re.match(r"^(?:https?://)?t\.me/(?:s/)?([A-Za-z0-9_]+)(?:/\d+)?/(\d+)$", clean)
    if m:
        return ForwardRef(m.group(1), int(m.group(2)), single, raw)
    m = re.match(r"^(.+):(\d+|last)$", clean)
    if m:
        return ForwardRef(m.group(1).strip(), None if m.group(2) == "last" else int(m.group(2)), single, raw)
    raise ValueError(f"Can't read forward reference '{value}'. Use https://t.me/<channel>/<id>, https://t.me/c/<id>/<id>, <chat>:<id> or me:last")


def prepare_forwards(source: Any, refs: List[ForwardRef]) -> List[Tuple[Any, List[int]]]:
    """Fetch the messages once: [(source chat entity, [message ids])], albums completed, in the order given."""
    batches: List[Tuple[Any, List[int]]] = []
    for ref in refs:
        entity = source.entity_of(ref.chat)
        if ref.msg_id is None:
            message = source.last_saved_message() if str(ref.chat).lower() == "me" else None
            if message is None:
                raise ValueError(f"No latest message in '{ref.raw}'")
        else:
            found = source.get_messages(entity, [ref.msg_id])
            if not found:
                raise ValueError(f"Message {ref.msg_id} not found in '{ref.raw}'")
            message = found[0]
        messages = [message] if ref.single else source.album_of(entity, message)
        ids = [m.id for m in messages]
        if batches and batches[-1][0] is entity:
            batches[-1][1].extend(ids)
        else:
            batches.append((entity, ids))
    return batches


@dataclass
class Payload:
    text: Optional[str] = None
    file: Optional[Path] = None
    fmt: str = "markdown"
    tables: str = "pre"
    link_preview: bool = True
    forwards: List[Tuple[Any, List[int]]] = field(default_factory=list)
    hide_source: bool = False
    hide_caption: bool = False

    def preview(self, values: Dict[str, str]) -> str:
        """The first message as Telegram will show it (text with entity markers)."""
        if not self.text:
            return ""
        plain, entities = telegram_format.parse(render(self.text, values, self.fmt), self.fmt, self.tables)
        if not entities:
            return plain
        names = ", ".join(sorted({type(e).__name__.replace("MessageEntity", "").lower() for e in entities}))
        return f"{plain}\n[formatting: {names}]"


def payload_key(payload: Payload, forward_refs: List[ForwardRef]) -> str:
    h = hashlib.sha256()
    h.update(json.dumps([payload.text, payload.fmt, payload.tables, payload.link_preview, payload.hide_source,
                         payload.hide_caption, [f.raw for f in forward_refs]], ensure_ascii=False).encode())
    if payload.file:
        h.update(str(payload.file.name).encode() + str(payload.file.stat().st_size).encode())
    return h.hexdigest()[:16]


# -- pacing -------------------------------------------------------------------


class Pacer:
    def __init__(self, delay: Tuple[float, float] = (20, 45), batch_size: int = 10, batch_pause: float = 300,
                 daily_limit: int = 100, rng: Optional[random.Random] = None):
        if delay[0] < 0 or delay[1] < delay[0]:
            raise ValueError("--delay must be MIN-MAX seconds, e.g. 20-45")
        self.delay, self.batch_size, self.batch_pause, self.daily_limit = delay, max(0, batch_size), batch_pause, daily_limit
        self.rng = rng or random.Random()

    def next_wait(self, sent_in_run: int) -> Tuple[float, str]:
        """Seconds to wait after the `sent_in_run`-th recipient, and why."""
        if self.batch_size and sent_in_run % self.batch_size == 0:
            return self.batch_pause * self.rng.uniform(0.8, 1.2), "batch pause"
        return self.rng.uniform(*self.delay), "next message"

    def estimate(self, count: int) -> float:
        average = sum(self.delay) / 2
        batches = (count - 1) // self.batch_size if self.batch_size and count else 0
        return max(0, count - 1 - batches) * average + batches * self.batch_pause

    def daily_block(self, times: List[float], now: float) -> Optional[float]:
        """When sending may resume if the 24 h cap is reached, else None."""
        recent = sorted(t for t in times if now - t < DAY)
        if self.daily_limit and len(recent) >= self.daily_limit:
            return recent[len(recent) - self.daily_limit] + DAY
        return None


# -- state ----------------------------------------------------------------------


class SendHistory:
    """Timestamps of every message this tool sent (all lists), for the 24 h cap."""

    def __init__(self, path: Optional[Path]):
        self.path = path
        self.times: List[float] = []
        if path and path.exists():
            try:
                self.times = [float(t) for t in json.loads(path.read_text())]
            except (ValueError, OSError):
                self.times = []

    def add(self, ts: float) -> None:
        self.times = [t for t in self.times if ts - t < 2 * DAY] + [ts]
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.times))


class SendState:
    def __init__(self, path: Path, key: str, restart: bool = False):
        self.path, self.key = path, key
        self.recipients: Dict[str, dict] = {}
        self.reset_reason = ""
        if path.exists() and not restart:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                data = {}
            if data.get("key") == key:
                self.recipients = data.get("recipients", {})
            elif data:
                self.reset_reason = "the message changed since the last run, so this is a fresh send"

    def is_sent(self, rkey: str) -> bool:
        return self.recipients.get(rkey, {}).get("status") == "sent"

    def mark(self, rkey: str, status: str, **info: Any) -> None:
        self.recipients[rkey] = {"status": status, "time": time.time(), **info}
        self.save()

    def save(self) -> None:
        self.path.write_text(json.dumps({"key": self.key, "recipients": self.recipients}, ensure_ascii=False, indent=1), encoding="utf-8")


@dataclass
class SendSummary:
    sent: int = 0
    failed: int = 0
    already_sent: int = 0
    stopped: str = ""
    results: List[dict] = field(default_factory=list)


class BulkSender:
    def __init__(self, source: Any, payload: Payload, pacer: Pacer, state: SendState, history: SendHistory,
                 max_flood_wait: float = 3600, sleep: Callable[[float], None] = time.sleep,
                 now: Callable[[], float] = time.time,
                 on_progress: Optional[Callable[[int, int, str], None]] = None,
                 on_wait: Optional[Callable[[float, str], None]] = None,
                 rng: Optional[random.Random] = None):
        self.source, self.payload, self.pacer, self.state, self.history = source, payload, pacer, state, history
        self.max_flood_wait, self.sleep, self.now = max_flood_wait, sleep, now
        self.on_progress = on_progress or (lambda *a: None)
        self.on_wait = on_wait or (lambda *a: None)
        self.rng = rng or random.Random()
        self._media: Any = None  # uploaded once, reused for the next recipients

    # waits are cut into one-second ticks so the progress line can count down (and Ctrl+C reacts quickly)
    def wait(self, seconds: float, reason: str) -> None:
        end = self.now() + seconds
        while True:
            left = end - self.now()
            if left <= 0:
                break
            self.on_wait(left, reason)
            self.sleep(min(1.0, left))

    def _steps(self, entity: Any, values: Dict[str, str]) -> List[Callable[[], Any]]:
        p, src = self.payload, self.source
        mode = telegram_format.TelegramParseMode(p.fmt, p.tables)
        steps: List[Callable[[], Any]] = []
        parts = telegram_format.split_message(render(p.text, values, p.fmt)) if p.text else []
        if p.forwards:
            steps += [lambda t=t: src.send(entity, t, mode, None, p.link_preview) for t in parts]
            steps += [lambda f=f, ids=ids: src.forward(entity, f, ids, p.hide_source, p.hide_caption) for f, ids in p.forwards]
            return steps
        if p.file:
            def send_file(caption):
                def go():
                    res = src.send(entity, caption, mode, self._media or str(p.file), p.link_preview)
                    self._media = self._media or res.get("media")
                    return res
                return go

            if parts and len(parts[0]) <= CAPTION_LIMIT:
                steps.append(send_file(parts[0]))
                parts = parts[1:]
            else:
                steps.append(send_file(None))
        steps += [lambda t=t: src.send(entity, t, mode, None, p.link_preview) for t in parts]
        return steps

    def deliver(self, entity: Any, values: Dict[str, str]) -> List[Any]:
        """Send to one chat with flood-wait retries (no state, no pacing). Raises SendError / StopSending."""
        results: List[Any] = []
        steps = self._steps(entity, values)
        i = 0
        while i < len(steps):
            try:
                results.append(steps[i]())
                i += 1
            except SendError as exc:
                if exc.kind == "peer_flood":
                    raise StopSending(str(exc))
                if exc.kind != "flood":
                    raise
                if exc.seconds > self.max_flood_wait:
                    raise StopSending(f"Telegram asks to wait {exc.seconds}s (more than --max-flood-wait); run again later")
                self.wait(exc.seconds + self.rng.uniform(1, 5), f"flood wait {exc.seconds}s")
        return results

    def run(self, resolved: List[Resolved]) -> SendSummary:
        summary = SendSummary()
        total = len(resolved)
        sent_in_run = 0
        pending = [item for item in resolved if not self.state.is_sent(item.key)]
        summary.already_sent = total - len(pending)
        for index, item in enumerate(pending, 1):
            block = self.pacer.daily_block(self.history.times, self.now())
            if block:
                summary.stopped = "daily limit reached; can resume at " + time.strftime("%Y-%m-%d %H:%M", time.localtime(block))
                break
            self.on_progress(summary.already_sent + index - 1, total, item.label)
            try:
                results = self.deliver(item.entity, placeholders(item))
            except StopSending as exc:
                summary.stopped = str(exc)
                break
            except SendError as exc:
                self.state.mark(item.key, "failed", reason=str(exc), name=item.label)
                summary.failed += 1
                summary.results.append({"recipient": item.recipient.ref, "name": item.label, "status": "failed", "reason": str(exc)})
                continue
            ids = [x["id"] if isinstance(x, dict) else x for x in results if x]
            self.state.mark(item.key, "sent", name=item.label, message_ids=[i for r in ids for i in (r if isinstance(r, list) else [r])])
            self.history.add(self.now())
            summary.sent += 1
            sent_in_run += 1
            summary.results.append({"recipient": item.recipient.ref, "name": item.label, "status": "sent", "reason": ""})
            if index < len(pending):
                seconds, reason = self.pacer.next_wait(sent_in_run)
                self.wait(seconds, reason)
        self.on_progress(summary.already_sent + summary.sent + summary.failed, total, "")
        return summary


def write_report(path: Path, skipped: List[Tuple[Recipient, str]], state: SendState) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["recipient", "name", "status", "reason", "time"])
        for key, info in state.recipients.items():
            writer.writerow([key.split(":", 1)[1], info.get("name", ""), info["status"], info.get("reason", ""),
                             time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(info["time"]))])
        for r, reason in skipped:
            writer.writerow([r.ref, r.name, "skipped", reason, ""])
    return path
