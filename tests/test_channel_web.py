import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from versline.services.channel_archive.models import ChannelInfo
from versline.services.channel_archive.sources.telegram_web import (
    TelegramWebSource,
    html_to_markdown,
    parse_clock,
    parse_count,
)

BASE = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def message(pid, day, inner=""):
    date = (BASE + timedelta(days=day)).isoformat()
    return (
        f'<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="chan/{pid}" '
        f'data-view="eyJjIjotMTAwMjc5NzE3NSwicCI6MX0">{inner}'
        f'<div class="tgme_widget_message_info"><span class="tgme_widget_message_views">3.24K</span>'
        f'<a class="tgme_widget_message_date" href="https://t.me/chan/{pid}"><time datetime="{date}" class="time"></time></a>'
        f"</div></div></div>"
    )


def text(body):
    return f'<div class="tgme_widget_message_text js-message_text" dir="auto">{body}</div>'


def page(ids, nxt=True):
    msgs = "".join(message(i, i, text(f"post {i}")) for i in ids)
    link = '<link rel="next" href="/s/chan?after=1">' if nxt else ""
    return f'<html><head>{link}</head><body><div class="tgme_channel_info"><div class="tgme_channel_info_header_title">Chan</div></div>{msgs}</body></html>'


class FakeWeb:
    """Serves ids 1..N like t.me/s: 20 per page, ?before / ?after."""

    def __init__(self, total=100):
        self.total = total
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        q = request.url.params
        if request.url.path == "/s/chan":
            if "before" in q:
                hi = int(q["before"])
                ids = list(range(max(1, hi - 20), hi))
            elif "after" in q:
                lo = int(q["after"])
                ids = list(range(lo + 1, min(self.total, lo + 20) + 1))
            else:
                ids = list(range(self.total - 19, self.total + 1))
            if not ids:
                return httpx.Response(200, text=page([], nxt=False))
            return httpx.Response(200, text=page(ids, nxt=ids[-1] < self.total))
        if request.url.path == "/s/gone":
            return httpx.Response(302, headers={"Location": "https://t.me/gone"})
        return httpx.Response(404)


def make_source(handler):
    return TelegramWebSource(client=httpx.Client(transport=httpx.MockTransport(handler)), delay=0)


class TestParsing(unittest.TestCase):
    def test_counts_and_clock(self):
        self.assertEqual(parse_count("3.24K"), 3240)
        self.assertEqual(parse_count("1.2M"), 1_200_000)
        self.assertEqual(parse_count("57"), 57)
        self.assertEqual(parse_clock("2:04"), 124)
        self.assertEqual(parse_clock("1:02:04"), 3724)

    def test_markdown(self):
        from bs4 import BeautifulSoup

        node = BeautifulSoup(
            '<div><b>عنوان</b><br/>خط <i class="emoji"><b>🔉</b></i> <a href="https://x.ir/a">لینک</a></div>', "html.parser"
        ).div
        self.assertEqual(html_to_markdown(node), "**عنوان**\nخط 🔉 [لینک](https://x.ir/a)")

    def test_media_kinds(self):
        src = make_source(lambda r: httpx.Response(404))
        ch = ChannelInfo(ref="chan", title="Chan", username="chan")
        html = message(
            5, 0,
            '<a class="tgme_widget_message_video_player" href="u"><div class="tgme_widget_message_video_wrap">'
            '<video src="https://cdn/x.mp4"></video></div><time class="message_video_duration">2:04</time></a>'
            '<a class="tgme_widget_message_video_player not_supported" href="u"><time class="message_video_duration">3:00</time></a>'
            '<a class="tgme_widget_message_document_wrap" href="u"><div class="tgme_widget_message_document_icon accent_bg audio"></div>'
            '<div class="tgme_widget_message_document_title">درس</div></a>',
        )
        from bs4 import BeautifulSoup

        msg = BeautifulSoup(html, "html.parser").select_one("div.tgme_widget_message")
        post = src._parse_message(ch, msg)
        self.assertEqual([m.kind for m in post.media], ["video", "video", "audio"])
        self.assertEqual([m.downloadable for m in post.media], [True, False, False])
        self.assertEqual(post.media[0].duration, 124)
        self.assertEqual(post.views, 3240)
        self.assertEqual(post.url, "https://t.me/chan/5")
        self.assertEqual(post.date, BASE)


class TestSource(unittest.TestCase):
    def test_resolve_errors(self):
        src = make_source(FakeWeb())
        for ref in ("https://t.me/c/123", "https://t.me/+AbCdEf", "https://t.me/joinchat/xyz"):
            with self.assertRaisesRegex(RuntimeError, "public channel"):
                src.resolve(ref)
        with self.assertRaisesRegex(RuntimeError, "not found"):
            make_source(FakeWeb()).resolve("@gone")

    def test_resolve_info(self):
        info = make_source(FakeWeb()).resolve("https://t.me/chan")
        self.assertEqual((info.title, info.username, info.channel_id), ("Chan", "chan", 2797175))

    def test_iter_posts_range_uses_few_requests(self):
        web = FakeWeb(total=100)
        src = make_source(web)
        ch = src.resolve("@chan")
        since, until = BASE + timedelta(days=41), BASE + timedelta(days=45, hours=12)
        ids = [p.id for p in src.iter_posts(ch, since, until)]
        self.assertEqual(ids, [41, 42, 43, 44, 45])
        self.assertLess(len(web.requests), 10)

    def test_iter_posts_pages_forward(self):
        src = make_source(FakeWeb(total=45))
        ch = src.resolve("@chan")
        self.assertEqual([p.id for p in src.iter_posts(ch)], list(range(1, 46)))

    def test_download_retries_with_fresh_url(self):
        tmp = Path(tempfile.mkdtemp())
        calls = []

        def handler(request):
            calls.append(str(request.url))
            if request.url.host == "cdn":
                return httpx.Response(200 if "fresh" in request.url.path else 403, content=b"data")
            video = '<a class="tgme_widget_message_video_player"><video src="https://cdn/fresh.mp4"></video></a>'
            return httpx.Response(200, text=f"<html>{message(7, 0, video)}</html>")

        src = make_source(handler)
        src._name = "chan"
        from versline.services.channel_archive.models import ChannelPost, MediaItem

        item = MediaItem(kind="video", source_ref="https://cdn/old.mp4")
        post = ChannelPost(id=7, date=BASE, media=[item])
        path = src.download(post, item, tmp, "chan_7")
        self.assertEqual(path.name, "chan_7.mp4")
        self.assertEqual(path.read_bytes(), b"data")


if __name__ == "__main__":
    unittest.main()
