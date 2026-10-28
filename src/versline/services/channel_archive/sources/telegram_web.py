from __future__ import annotations

import base64
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator, List, Optional
from urllib.parse import urlparse

import httpx
from loguru import logger

from versline.config import settings
from versline.services.channel_archive.models import ChannelInfo, ChannelPost, MediaItem
from versline.services.channel_archive.sources.telegram import normalize_ref, parse_proxy  # noqa: F401

BASE_URL = "https://t.me"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
REQUEST_DELAY = 0.4
PAGE_SIZE = 20


def parse_count(text: str) -> Optional[int]:
    """'3.24K' -> 3240, '1.2M' -> 1200000, '57' -> 57."""
    match = re.match(r"^\s*([\d.]+)\s*([KkMm]?)\s*$", text or "")
    if not match:
        return None
    factor = {"": 1, "k": 1_000, "m": 1_000_000}[match.group(2).lower()]
    return int(round(float(match.group(1)) * factor))


def parse_clock(text: str) -> Optional[float]:
    """'2:04' / '1:02:04' -> seconds."""
    if not text or not re.match(r"^\d+(:\d{1,2}){1,2}$", text.strip()):
        return None
    total = 0
    for part in text.strip().split(":"):
        total = total * 60 + int(part)
    return float(total)


def html_to_markdown(node) -> str:
    """Convert a message text element to the small Markdown subset Obsidian notes use."""
    from bs4 import NavigableString, Tag

    def walk(el) -> str:
        if isinstance(el, NavigableString):
            return str(el)
        if not isinstance(el, Tag):
            return ""
        inner = "".join(walk(child) for child in el.children)
        name = el.name
        if name == "br":
            return "\n"
        if "emoji" in (el.get("class") or []):
            return el.get_text()
        if not inner.strip():
            return inner
        if name in ("b", "strong"):
            return f"**{inner.strip()}**"
        if name in ("i", "em"):
            return f"*{inner.strip()}*"
        if name in ("code", "pre"):
            return f"`{inner}`"
        if name == "a":
            href = el.get("href") or ""
            if href.startswith("//"):
                href = "https:" + href
            return inner if inner.strip() == href or not href else f"[{inner}]({href})"
        return inner

    return walk(node).strip()


def _style_url(style: str) -> Optional[str]:
    match = re.search(r"url\(['\"]?([^'\")]+)", style or "")
    return match.group(1) if match else None


class TelegramWebSource:
    """ChannelSource reading the public web preview (t.me/s/<channel>); no account or api_id needed."""

    def __init__(self, proxy: Optional[str] = None, client: Optional[httpx.Client] = None, delay: float = REQUEST_DELAY):
        self.delay = delay
        if client is not None:
            self._client = client
        else:
            proxy_url = proxy or settings.telegram.proxy or settings.llm.proxy
            if proxy_url:
                parse_proxy(proxy_url)  # same validation/error message as the login-based source
            self._client = httpx.Client(
                proxy=proxy_url or None,
                timeout=30.0,
                follow_redirects=False,
                headers={"User-Agent": USER_AGENT},
            )
        self._name: Optional[str] = None
        self._last_request = 0.0

    # -- plumbing --

    def _get(self, url: str, params: Optional[dict] = None) -> httpx.Response:
        for attempt in range(4):
            wait = self.delay - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
            response = self._client.get(url, params=params)
            if response.status_code != 429:
                return response
            time.sleep(2 ** attempt * 2)
        raise RuntimeError("Telegram rate-limited the web preview (HTTP 429); try again later.")

    def _page(self, **params) -> tuple:
        """Fetch one preview page -> (soup, [message divs])."""
        from bs4 import BeautifulSoup

        response = self._get(f"{BASE_URL}/s/{self._name}", params=params or None)
        if response.status_code != 200:
            raise RuntimeError(f"Telegram web preview returned HTTP {response.status_code} for {self._name}")
        soup = BeautifulSoup(response.text, "html.parser")
        return soup, soup.select("div.tgme_widget_message[data-post]")

    @staticmethod
    def _id(msg) -> int:
        return int(msg["data-post"].rsplit("/", 1)[1])

    @staticmethod
    def _date(msg) -> datetime:
        time_tag = msg.select_one("a.tgme_widget_message_date time[datetime]")
        return datetime.fromisoformat(time_tag["datetime"])

    def close(self) -> None:
        self._client.close()

    # -- ChannelSource --

    def resolve(self, ref: str) -> ChannelInfo:
        name = normalize_ref(ref)
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_]{3,}", name):
            raise RuntimeError(
                "--web needs a public channel (@name or https://t.me/name). "
                "Private channels and invite links need `versline telegram login`."
            )
        self._name = name
        response = self._get(f"{BASE_URL}/s/{name}")
        if response.status_code != 200:
            raise RuntimeError(f"Channel '{name}' was not found or its web preview is disabled. Use `versline telegram login` instead.")
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(response.text, "html.parser")
        if soup.select_one(".tgme_channel_info") is None and not soup.select("div.tgme_widget_message[data-post]"):
            raise RuntimeError(f"Channel '{name}' was not found or its web preview is disabled. Use `versline telegram login` instead.")
        self._first_page = soup

        title_tag = soup.select_one(".tgme_channel_info_header_title") or soup.select_one(".tgme_header_title")
        username, channel_id = name, None
        first = soup.select_one("div.tgme_widget_message[data-post]")
        if first is not None:
            username = first["data-post"].split("/", 1)[0]
            try:
                padded = first.get("data-view", "") + "=" * (-len(first.get("data-view", "")) % 4)
                raw = str(abs(int(json.loads(base64.urlsafe_b64decode(padded))["c"])))
                # Bot-API style ids carry a -100 prefix that Telethon's entity.id drops
                channel_id = int(raw[3:] if raw.startswith("100") and len(raw) > 9 else raw)
            except (ValueError, KeyError, TypeError):
                channel_id = None
        self._name = username
        return ChannelInfo(
            ref=ref,
            title=title_tag.get_text(strip=True) if title_tag else username,
            username=username,
            channel_id=channel_id,
        )

    def _newest_id(self) -> int:
        msgs = self._first_page.select("div.tgme_widget_message[data-post]")
        return self._id(msgs[-1]) if msgs else 0

    def _start_after(self, since: datetime) -> int:
        """Binary-search for an id shortly before the first post at/after `since`."""
        lo, hi = 0, self._newest_id() + 1
        while hi - lo > PAGE_SIZE:
            mid = (lo + hi) // 2
            _, msgs = self._page(before=mid)
            if not msgs:
                lo = mid  # deleted range: nothing older here, move forward
                continue
            if self._date(msgs[-1]) < since:
                lo = self._id(msgs[-1])
            else:
                hi = self._id(msgs[0])
        return lo

    def iter_posts(
        self,
        channel: ChannelInfo,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterator[ChannelPost]:
        cursor = self._start_after(since) if since is not None else 0
        emitted = 0
        while True:
            soup, msgs = self._page(after=cursor)
            if not msgs:
                return
            for msg in msgs:
                date = self._date(msg)
                if until is not None and date > until:
                    return
                if since is not None and date < since:
                    continue
                post = self._parse_message(channel, msg)
                if post is None:
                    continue
                yield post
                emitted += 1
                if limit and emitted >= limit:
                    return
            new_cursor = self._id(msgs[-1])
            if new_cursor <= cursor or soup.select_one('link[rel="next"]') is None:
                return
            cursor = new_cursor

    # -- message conversion --

    def _parse_message(self, channel: ChannelInfo, msg) -> Optional[ChannelPost]:
        post_id = self._id(msg)
        text_el = msg.select_one(".tgme_widget_message_text")
        text = html_to_markdown(text_el) if text_el else ""
        media = self._media_items(msg)
        if msg.select_one(".message_media_not_supported_label") and not media:
            media = []
        if not text and not media:
            return None
        views_el = msg.select_one(".tgme_widget_message_views")
        fwd_el = msg.select_one(".tgme_widget_message_forwarded_from_name")
        return ChannelPost(
            id=post_id,
            date=self._date(msg),
            text=text,
            media=media,
            url=f"{BASE_URL}/{channel.username or self._name}/{post_id}",
            views=parse_count(views_el.get_text()) if views_el else None,
            forwarded_from=fwd_el.get_text(strip=True) if fwd_el else None,
        )

    @staticmethod
    def _media_items(msg) -> List[MediaItem]:
        items: List[MediaItem] = []
        for voice in msg.select("audio.tgme_widget_message_voice, .tgme_widget_message_voice[src]"):
            wrap = voice.find_parent(class_="tgme_widget_message_voice_player") or voice.parent
            dur = wrap.select_one(".tgme_widget_message_voice_duration") if wrap else None
            items.append(MediaItem(kind="voice", duration=parse_clock(dur.get_text()) if dur else None,
                                   source_ref=voice.get("src"), downloadable=bool(voice.get("src"))))
        for rv in msg.select(".tgme_widget_message_roundvideo_player"):
            video = rv.select_one("video[src]")
            dur = rv.select_one(".tgme_widget_message_roundvideo_duration, .message_video_duration")
            items.append(MediaItem(kind="video_note", duration=parse_clock(dur.get_text()) if dur else None,
                                   source_ref=video.get("src") if video else None, downloadable=video is not None))
        for player in msg.select("a.tgme_widget_message_video_player"):
            video = player.select_one("video[src]")
            dur = player.select_one(".message_video_duration")
            items.append(MediaItem(kind="video", duration=parse_clock(dur.get_text()) if dur else None,
                                   source_ref=video.get("src") if video else None, downloadable=video is not None))
        for photo in msg.select("a.tgme_widget_message_photo_wrap"):
            url = _style_url(photo.get("style", ""))
            items.append(MediaItem(kind="photo", source_ref=url, downloadable=bool(url)))
        for doc in msg.select("a.tgme_widget_message_document_wrap"):
            icon = doc.select_one(".tgme_widget_message_document_icon")
            title = doc.select_one(".tgme_widget_message_document_title")
            is_audio = icon is not None and "audio" in (icon.get("class") or [])
            items.append(MediaItem(kind="audio" if is_audio else "document",
                                   file_name=title.get_text(strip=True) if title else None, downloadable=False))
        return items

    # -- download --

    def _fresh_url(self, post: ChannelPost, item: MediaItem) -> Optional[str]:
        """Re-read the post to get a new tokenised URL for the same media slot."""
        channel = ChannelInfo(ref=self._name, title=self._name, username=self._name)
        _, msgs = self._page(before=post.id + 1)
        for msg in msgs:
            if self._id(msg) == post.id:
                same_kind = [m for m in self._media_items(msg) if m.kind == item.kind]
                index = [m for m in post.media if m.kind == item.kind].index(item)
                return same_kind[index].source_ref if index < len(same_kind) else None
        return None

    def download(
        self,
        post: ChannelPost,
        item: MediaItem,
        dest_dir: Path,
        stem: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Path:
        if not item.source_ref:
            raise RuntimeError(f"Post {post.id}: no download URL on the web preview")
        dest_dir.mkdir(parents=True, exist_ok=True)
        url = item.source_ref
        for attempt in range(2):
            suffix = Path(urlparse(url).path).suffix or {"photo": ".jpg", "voice": ".ogg"}.get(item.kind, ".mp4")
            path = dest_dir / f"{stem}{suffix}"
            with self._client.stream("GET", url if url.startswith("http") else "https:" + url) as response:
                if response.status_code in (403, 404, 410) and attempt == 0:
                    fresh = self._fresh_url(post, item)
                    if fresh and fresh != url:
                        logger.debug(f"Post {post.id}: media URL expired, retrying with a fresh one")
                        url = fresh
                        continue
                if response.status_code != 200:
                    raise RuntimeError(f"Download failed for post {post.id}: HTTP {response.status_code}")
                total = int(response.headers.get("content-length") or 0)
                received = 0
                with path.open("wb") as fh:
                    for chunk in response.iter_bytes(65536):
                        fh.write(chunk)
                        received += len(chunk)
                        if progress_callback:
                            progress_callback(received, total)
            return path
        raise RuntimeError(f"Download failed for post {post.id}")
