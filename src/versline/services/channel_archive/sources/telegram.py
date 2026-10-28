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
    return ref.lstrip("@")


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

    def _connect(self) -> None:
        async def _c():
            await self._client.connect()
            if not await self._client.is_user_authorized():
                raise RuntimeError("Not logged in to Telegram. Run `versline telegram login` first.")

        self._run(_c())

    def close(self) -> None:
        try:
            self._run(self._client.disconnect())
        finally:
            self._loop.close()

    # -- ChannelSource --

    def resolve(self, ref: str) -> ChannelInfo:
        self._connect()
        entity = self._run(self._client.get_entity(normalize_ref(ref)))
        self._entity = entity
        return ChannelInfo(
            ref=ref,
            title=getattr(entity, "title", None) or getattr(entity, "first_name", None) or str(entity.id),
            username=getattr(entity, "username", None),
            channel_id=entity.id,
        )

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
        if channel.username:
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
        )
