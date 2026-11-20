from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator, List, Optional
from urllib.parse import urlparse

from loguru import logger

from versline.config import settings
from versline.services.channel_archive.models import ChannelInfo, ChannelPost, MediaItem
from versline.userconfig import user_config_dir


def default_session_path() -> str:
    """Telethon appends '.session' itself."""
    return settings.telegram.session_path or str(user_config_dir() / "telegram")


def parse_proxy(url: Optional[str]) -> Optional[tuple]:
    """socks5://user:pass@host:port or http://host:port -> Telethon proxy tuple."""
    if not url:
        return None
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    kind = {"socks5": "socks5", "socks5h": "socks5", "socks4": "socks4", "http": "http", "https": "http"}.get(scheme)
    if not kind or not parsed.hostname or not parsed.port:
        raise ValueError(f"Unsupported Telegram proxy '{url}'. Use socks5://host:port or http://host:port")
    return (kind, parsed.hostname, parsed.port, True, parsed.username, parsed.password)


def normalize_ref(ref: str) -> Any:
    """Turn the user's channel reference into something Telethon's get_entity accepts."""
    ref = ref.strip()
    private = re.match(r"^(?:https?://)?t\.me/c/(\d+)", ref)
    if private:
        from telethon.tl.types import PeerChannel

        return PeerChannel(int(private.group(1)))
    if re.match(r"^(?:https?://)?t\.me/(\+|joinchat/)", ref):
        return ref  # invite link: Telethon resolves it when the account already joined
    public = re.match(r"^(?:https?://)?t\.me/(?:s/)?([A-Za-z0-9_]+)", ref)
    if public:
        return public.group(1)
    if re.fullmatch(r"-?\d+", ref):
        return int(ref)  # a chat id as `telegram chats` prints it (users, basic groups -123, channels -100…)
    return ref.lstrip("@")  # @name, name, or "me" (Saved Messages)


def chat_kind(entity: Any) -> Optional[str]:
    """channel | supergroup | group | user for a Telethon entity."""
    from telethon.tl.types import Channel, Chat, User

    if isinstance(entity, User):
        return "user"
    if isinstance(entity, Chat):
        return "group"
    if isinstance(entity, Channel):
        return "channel" if getattr(entity, "broadcast", False) else "supergroup"
    return None


def display_name(entity: Any) -> Optional[str]:
    if entity is None:
        return None
    name = " ".join(filter(None, [getattr(entity, "first_name", None), getattr(entity, "last_name", None)]))
    return name or getattr(entity, "title", None) or getattr(entity, "username", None)


def row_kind(entity: Any) -> Optional[str]:
    """Like chat_kind, but bots are their own kind (for lists; ChannelInfo keeps treating them as users)."""
    kind = chat_kind(entity)
    return "bot" if kind == "user" and getattr(entity, "bot", False) else kind


def user_row(user: Any) -> dict:
    phone = getattr(user, "phone", None)
    return {
        "id": user.id,
        "name": display_name(user) or "",
        "first_name": getattr(user, "first_name", None) or "",
        "last_name": getattr(user, "last_name", None) or "",
        "username": getattr(user, "username", None) or "",
        "phone": f"+{phone}" if phone else "",
        "type": row_kind(user) or "user",
        "contact": bool(getattr(user, "contact", False)),
        "mutual": bool(getattr(user, "mutual_contact", False)),
        "bot": bool(getattr(user, "bot", False)),
    }


class SendError(Exception):
    """A failed send, in terms the sender understands. kind: flood (wait `seconds`, retry) | peer_flood (account limited,
    stop) | failed (this recipient only)."""

    def __init__(self, kind: str, message: str = "", seconds: int = 0):
        super().__init__(message or kind)
        self.kind = kind
        self.seconds = seconds


def _send_error(exc: Exception) -> SendError:
    from telethon import errors

    if isinstance(exc, errors.PeerFloodError):
        return SendError("peer_flood", "Telegram limited this account for spam (PeerFlood). Check @SpamBot")
    if isinstance(exc, (errors.FloodWaitError, errors.SlowModeWaitError)):
        return SendError("flood", f"flood wait {exc.seconds}s", seconds=int(exc.seconds))
    return SendError("failed", f"{type(exc).__name__}: {exc}".rstrip(": "))


def _markdown(text: str) -> str:
    # Telethon marks italics with __x__, which Obsidian renders as bold.
    return re.sub(r"__(.+?)__", r"*\1*", text or "", flags=re.DOTALL)


class TelegramSource:
    """Telethon-backed ChannelSource. Telethon's async API is driven from a private event loop."""

    def __init__(
        self,
        api_id: Optional[int] = None,
        api_hash: Optional[str] = None,
        session_path: Optional[str] = None,
        proxy: Optional[str] = None,
    ):
        self.api_id = api_id or settings.telegram.api_id
        self.api_hash = api_hash or settings.telegram.api_hash
        if not self.api_id or not self.api_hash:
            raise RuntimeError(
                "Telegram api_id/api_hash are not set. Run `versline telegram login` "
                "(get them at https://my.telegram.org)."
            )
        self.session_path = session_path or default_session_path()
        self.proxy = parse_proxy(proxy or settings.telegram.proxy or settings.llm.proxy)
        self._loop = asyncio.new_event_loop()
        self._client = self._run(self._make_client())

    # -- plumbing --

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    async def _make_client(self):
        from telethon import TelegramClient

        Path(self.session_path).parent.mkdir(parents=True, exist_ok=True)
        return TelegramClient(self.session_path, int(self.api_id), self.api_hash, proxy=self.proxy)

    def _secure_session(self) -> None:
        try:
            os.chmod(self.session_path + ".session", 0o600)
        except OSError:
            pass

    def login(self) -> str:
        """Interactive phone/code/2FA login. Returns the account's display name."""
        async def _login():
            await self._client.start()
            me = await self._client.get_me()
            return " ".join(filter(None, [me.first_name, me.last_name])) or str(me.id)

        name = self._run(_login())
        self._secure_session()
        return name

    def logout(self) -> None:
        async def _logout():
            await self._client.connect()
            if await self._client.is_user_authorized():
                await self._client.log_out()

        self._run(_logout())
        try:
            Path(self.session_path + ".session").unlink()
        except OSError:
            pass

    def account_name(self) -> Optional[str]:
        """Display name of the logged-in account, or None when the session is not authorized (no prompts)."""
        async def _who():
            await self._client.connect()
            if not await self._client.is_user_authorized():
                return None
            me = await self._client.get_me()
            return " ".join(filter(None, [me.first_name, me.last_name])) or str(me.id)

        return self._run(_who())

    def _connect(self) -> None:
        async def _c():
            await self._client.connect()
            if not await self._client.is_user_authorized():
                raise RuntimeError("Not logged in to Telegram. Run `versline telegram login` first.")

        self._run(_c())

    def close(self) -> None:
        async def _disconnect():
            # Telethon's disconnect() runs itself (returning None) when the loop isn't running, so await it from inside one.
            await self._client.disconnect()

        try:
            self._run(_disconnect())
        finally:
            self._loop.close()

    # -- ChannelSource --

    def resolve(self, ref: str) -> ChannelInfo:
        self._connect()
        target = normalize_ref(ref)
        if isinstance(target, int):
            entity = self._run(self._entity_by_id(target))
        else:
            entity = self._run(self._client.get_entity(target))
        self._entity = entity
        return ChannelInfo(
            ref=ref,
            title=display_name(entity) or str(entity.id),
            username=getattr(entity, "username", None),
            channel_id=entity.id,
            kind=chat_kind(entity),
        )

    async def _entity_by_id(self, chat_id: int):
        """A chat by numeric id, in any form: marked (-100… channel/supergroup, -… basic group) as `telegram chats`
        and most bots print it, or the bare id (positive) of a user, group or channel. Looked up in your chats, so
        the account must be a member."""
        from telethon import utils

        bare = {abs(chat_id)}
        if chat_id < 0:
            try:
                bare.add(utils.resolve_id(chat_id)[0])  # -1001234 -> 1234
            except Exception:
                pass
        loose = None
        async for dialog in self._client.iter_dialogs():
            if dialog.id == chat_id:
                return dialog.entity
            if loose is None and getattr(dialog.entity, "id", None) in bare:
                loose = dialog.entity
        if loose is not None:
            return loose
        try:
            return await self._client.get_entity(chat_id)  # e.g. a user you share no chat with but have cached
        except (ValueError, TypeError) as exc:
            raise ValueError(f"No chat with id {chat_id} among your chats. Run `versline telegram chats` to see the ids.") from exc

    def iter_dialogs(
        self,
        search: Optional[str] = None,
        limit: Optional[int] = None,
        kinds: Optional[set] = None,
        unread_only: bool = False,
        archived: Optional[bool] = None,
        with_entity: bool = False,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[dict]:
        """The account's chats (newest first) as {id, kind, title, username, phone, ...}; `search` matches title,
        username or phone; `kinds` filters user/bot/group/supergroup/channel; `since`/`until` keep chats whose last
        message falls in that range. Kept cheap: `until` and archived/non-archived are sent to Telegram as offset and
        folder, reading stops at the first non-pinned chat older than `since` (chats come newest first) or at `limit`;
        search, type and unread can only be checked locally, so they read on until `limit` is filled."""
        from versline.services.channel_archive.filters import normalize_fa
        from versline.services.telegram_people import phone_key

        self._connect()
        needle = normalize_fa(search) if search else None
        digits = phone_key(search) if search and any(c.isdigit() for c in search) else ""

        async def _list():
            rows = []
            folder = None if archived is None else (1 if archived else 0)
            offset = (until + timedelta(seconds=1)) if until else None
            async for dialog in self._client.iter_dialogs(offset_date=offset, folder=folder):
                if since and dialog.date and dialog.date < since and not getattr(dialog, "pinned", False):
                    break  # newest first: everything after this is older still
                entity = dialog.entity
                kind = row_kind(entity)
                if kinds and kind not in kinds:
                    continue
                if unread_only and not (dialog.unread_count or dialog.unread_mentions_count):
                    continue
                if (since or until) and (dialog.date is None or (since and dialog.date < since) or (until and dialog.date > until)):
                    continue
                is_archived = bool(getattr(dialog, "archived", False))
                if archived is not None and is_archived != archived:
                    continue
                title = display_name(entity) or str(dialog.id)
                username = getattr(entity, "username", None)
                phone = getattr(entity, "phone", None)
                phone = f"+{phone}" if phone else ""
                if needle and needle not in normalize_fa(title) and needle not in normalize_fa(username or "") \
                        and not (digits and digits in phone_key(phone)):
                    continue
                row = {
                    "id": dialog.id, "kind": kind, "type": kind, "title": title, "name": title, "username": username,
                    "phone": phone, "unread": dialog.unread_count or 0, "archived": is_archived,
                    "contact": bool(getattr(entity, "contact", False)), "last_date": dialog.date,
                    "last_message": dialog.date.astimezone().strftime("%Y-%m-%d %H:%M") if dialog.date else "",
                }
                if with_entity:
                    row["entity"] = entity
                rows.append(row)
                if limit and len(rows) >= limit:
                    break
            return rows

        return self._run(_list())

    def list_contacts(self, search: Optional[str] = None, mutual_only: bool = False, with_entity: bool = False) -> List[dict]:
        """Your Telegram contacts: {id, name, username, phone, mutual, ...}, sorted by name."""
        from telethon.tl import functions

        from versline.services.channel_archive.filters import normalize_fa
        from versline.services.telegram_people import phone_key

        self._connect()
        needle = normalize_fa(search) if search else None
        digits = phone_key(search) if search and any(c.isdigit() for c in search) else ""

        async def _contacts():
            return (await self._client(functions.contacts.GetContactsRequest(hash=0))).users

        rows = []
        for user in self._run(_contacts()):
            row = user_row(user)
            row["contact"] = True
            if mutual_only and not row["mutual"]:
                continue
            if needle and needle not in normalize_fa(row["name"]) and needle not in normalize_fa(row["username"]) \
                    and not (digits and digits in phone_key(row["phone"])):
                continue
            if with_entity:
                row["entity"] = user
            rows.append(row)
        rows.sort(key=lambda r: normalize_fa(r["name"]))
        return rows

    def list_members(self, ref: str, search: Optional[str] = None, limit: Optional[int] = None) -> List[dict]:
        """Members of a group or supergroup you belong to (channels: admins only; Telegram refuses the rest)."""
        info = self.resolve(ref)
        if info.kind == "user":
            raise ValueError("Members can only be listed for groups and channels")

        async def _members():
            rows = []
            async for user in self._client.iter_participants(self._entity, search=search or "", limit=limit):
                rows.append(user_row(user))
            return rows

        try:
            return self._run(_members())
        except Exception as exc:
            raise RuntimeError(f"Telegram would not list the members of {info.title}: {exc}") from exc

    # -- sending --

    def entity_of(self, ref: Any) -> Any:
        """Any chat reference (id, @name, link, 'me') as a Telethon entity."""
        self._connect()
        target = normalize_ref(ref) if isinstance(ref, str) else ref
        if isinstance(target, int):
            return self._run(self._entity_by_id(target))
        return self._run(self._client.get_entity(target))

    def set_flood_sleep_threshold(self, seconds: int) -> None:
        """0 = never sleep inside Telethon on FloodWait; the sender's pacer handles every wait itself."""
        self._client.flood_sleep_threshold = seconds

    def get_messages(self, chat: Any, ids: List[int]) -> List[Any]:
        """Messages by id (missing ones dropped), albums completed unless a single message is wanted."""
        entity = chat if not isinstance(chat, (str, int)) else self.entity_of(chat)
        found = [m for m in self._run(self._client.get_messages(entity, ids=ids)) if m]
        if getattr(entity, "noforwards", False) or any(getattr(m, "noforwards", False) for m in found):
            raise ValueError("This chat or message has forwarding disabled by Telegram")
        return found

    def album_of(self, chat_entity: Any, message: Any) -> List[Any]:
        if not getattr(message, "grouped_id", None):
            return [message]
        near = self._run(self._client.get_messages(chat_entity, ids=list(range(message.id - 10, message.id + 11))))
        return sorted((m for m in near if m and m.grouped_id == message.grouped_id), key=lambda m: m.id)

    def last_saved_message(self) -> Any:
        msgs = self._run(self._client.get_messages("me", limit=1))
        return msgs[0] if msgs else None

    def send(self, entity: Any, text: str, parse_mode: Any = None, file: Any = None, link_preview: bool = True) -> dict:
        """Send text (or a file with `text` as caption). `file` is a path or a media object returned earlier as
        ['media']. Returns {'id', 'media'}; raises SendError."""
        from telethon.errors import RPCError

        async def _send():
            if file is not None:
                msg = await self._client.send_file(entity, file, caption=text or None, parse_mode=parse_mode)
            else:
                msg = await self._client.send_message(entity, text, parse_mode=parse_mode, link_preview=link_preview)
            return {"id": msg.id, "media": getattr(msg, "media", None)}

        try:
            return self._run(_send())
        except RPCError as exc:
            raise _send_error(exc) from exc

    def forward(self, entity: Any, from_entity: Any, ids: List[int], drop_author: bool = False, drop_captions: bool = False) -> List[int]:
        from telethon.errors import RPCError

        async def _fwd():
            sent = await self._client.forward_messages(
                entity, ids, from_entity, drop_author=drop_author, drop_media_captions=drop_captions)
            return [m.id for m in (sent if isinstance(sent, list) else [sent])]

        try:
            return self._run(_fwd())
        except RPCError as exc:
            raise _send_error(exc) from exc

    def iter_posts(
        self,
        channel: ChannelInfo,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterator[ChannelPost]:
        kwargs: dict = {"reverse": True}
        if since is not None:
            kwargs["offset_date"] = since - timedelta(seconds=1)
        agen = self._client.iter_messages(self._entity, **kwargs).__aiter__()

        emitted = 0
        group: List[Any] = []

        def flush() -> Optional[ChannelPost]:
            nonlocal group
            if not group:
                return None
            post = self._to_post(channel, group)
            group = []
            return post

        while True:
            try:
                msg = self._run(agen.__anext__())
            except StopAsyncIteration:
                break
            if until is not None and msg.date > until:
                break
            if since is not None and msg.date < since:
                continue
            if getattr(msg, "action", None) is not None or not (msg.message or self._media_item(msg)):
                continue  # service message / empty
            if group and msg.grouped_id and msg.grouped_id == group[0].grouped_id:
                group.append(msg)
                continue
            post = flush()
            group = [msg]
            if post is not None:
                yield post
                emitted += 1
                if limit and emitted >= limit:
                    return
        post = flush()
        if post is not None and not (limit and emitted >= limit):
            yield post

    def download(
        self,
        post: ChannelPost,
        item: MediaItem,
        dest_dir: Path,
        stem: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = self._run(
            self._client.download_media(item.source_ref, file=str(dest_dir / stem), progress_callback=progress_callback)
        )
        if not path:
            raise RuntimeError(f"Telegram returned no file for post {post.id}")
        return Path(path)

    # -- message conversion --

    @staticmethod
    def _media_item(msg: Any) -> Optional[MediaItem]:
        from telethon.tl.types import MessageMediaWebPage

        # Link previews expose the page's photo/document through msg.photo; they are not post media.
        if not msg.media or isinstance(msg.media, MessageMediaWebPage):
            return None
        if msg.voice:
            kind = "voice"
        elif msg.video_note:
            kind = "video_note"
        elif msg.audio:
            kind = "audio"
        elif msg.video:
            kind = "video"
        elif msg.photo:
            kind = "photo"
        elif msg.document:
            mime = (msg.file.mime_type or "") if msg.file else ""
            kind = "audio" if mime.startswith("audio/") else "video" if mime.startswith("video/") else "document"
        else:
            return None
        f = msg.file
        return MediaItem(
            kind=kind,
            file_name=getattr(f, "name", None),
            mime=getattr(f, "mime_type", None),
            size=getattr(f, "size", None),
            duration=getattr(f, "duration", None),
            source_ref=msg,
        )

    def _to_post(self, channel: ChannelInfo, msgs: List[Any]) -> ChannelPost:
        first = min(msgs, key=lambda m: m.id)
        text = next((m.text for m in msgs if m.message), "") or ""
        media = [item for item in (self._media_item(m) for m in msgs) if item]
        if not channel.linkable:
            url = None  # private chats and basic groups have no per-message links
        elif channel.username:
            url = f"https://t.me/{channel.username}/{first.id}"
        elif channel.channel_id:
            url = f"https://t.me/c/{channel.channel_id}/{first.id}"
        else:
            url = None
        forwarded = None
        fwd = getattr(first, "forward", None)
        if fwd is not None:
            chat = getattr(fwd, "chat", None)
            forwarded = getattr(chat, "title", None) or getattr(fwd, "from_name", None)
        return ChannelPost(
            id=first.id,
            date=first.date,
            text=_markdown(text),
            media=media,
            url=url,
            views=max((m.views or 0 for m in msgs), default=None) or None,
            forwards=max((m.forwards or 0 for m in msgs), default=None) or None,
            grouped_id=first.grouped_id,
            forwarded_from=forwarded,
            edit_date=first.edit_date,
            sender_id=getattr(first, "sender_id", None),
            sender_name=getattr(first, "post_author", None) or display_name(getattr(first, "sender", None)),
            reply_to=getattr(first, "reply_to_msg_id", None),
        )
