"""Turn Markdown (as written in Obsidian) into Telegram text + entities.

Markdown -> Telegram HTML -> Telethon's HTML parser. Telethon has no spoiler tag, so spoilers go through a marker
link that is swapped for a MessageEntitySpoiler afterwards. Telegram has no lists, headings or tables: lists become
bullet lines, headings bold lines, tables a monospace block or `Header: value` lines.
"""
from __future__ import annotations

import html
import re
from typing import List, Tuple

FORMATS = ("markdown", "html", "plain")
TABLES = ("pre", "list")
MAX_LEN = 4096
SPOILER_MARK = "versline-spoiler:"

_PH = "\x00{}\x00"


def _inline(text: str, stash: List[str]) -> str:
    def keep(markup: str) -> str:
        stash.append(markup)
        return _PH.format(len(stash) - 1)

    text = re.sub(r"`([^`\n]+)`", lambda m: keep(f"<code>{html.escape(m.group(1), quote=False)}</code>"), text)

    def emoji(m):
        return keep(f'<tg-emoji emoji-id="{m.group(2)}">{html.escape(m.group(1), quote=False)}</tg-emoji>')

    text = re.sub(r"!\[([^\]]*)\]\(emoji:(\d+)\)", emoji, text)

    def link(m):
        label = _inline(m.group(1), stash)
        return keep(f'<a href="{html.escape(m.group(2).strip(), quote=True)}">{_restore(label, stash)}</a>')

    text = re.sub(r"\[([^\]\n]+)\]\(([^)\s]+)\)", link, text)
    text = re.sub(r"(?<![\"'>=(])\b(https?://[^\s<>()\[\]]+[^\s<>()\[\].,;:!?،؛؟])",
                  lambda m: keep(f'<a href="{html.escape(m.group(1), quote=True)}">{html.escape(m.group(1), quote=False)}</a>'), text)
    text = html.escape(text, quote=False)

    spoilers = [0]

    def spoiler(m):
        spoilers[0] += 1
        return f'<a href="{SPOILER_MARK}{spoilers[0]}">{m.group(1)}</a>'

    text = re.sub(r"\|\|(.+?)\|\|", spoiler, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<u>\1</u>", text)
    text = re.sub(r"~~(.+?)~~", r"<del>\1</del>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<i>\1</i>", text)
    return text


def _restore(text: str, stash: List[str]) -> str:
    for _ in range(3):  # placeholders may nest (a code span inside a link label)
        text = re.sub("\x00(\\d+)\x00", lambda m: stash[int(m.group(1))], text)
    return text


def _cells(line: str) -> List[str]:
    line = line.strip()
    line = line[1:] if line.startswith("|") else line
    line = line[:-1] if line.endswith("|") and not line.endswith("\\|") else line
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line)]


def _is_sep(line: str) -> bool:
    return bool(re.fullmatch(r"\s*\|?[\s:\-|]+\|?\s*", line)) and "-" in line


def _table(rows: List[List[str]], style: str, stash: List[str]) -> str:
    header, body = rows[0], rows[1:]
    if style == "list":
        blocks = []
        for row in body:
            lines = [f"<b>{_restore(_inline(h, stash), stash)}</b>: {_restore(_inline(v, stash), stash)}"
                     for h, v in zip(header, row) if v]
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)
    width = [max(len(r[i]) if i < len(r) else 0 for r in rows) for i in range(len(header))]
    fmt = lambda r: " │ ".join((r[i] if i < len(r) else "").ljust(width[i]) for i in range(len(header))).rstrip()
    sep = "─┼─".join("─" * w for w in width)
    return "<pre>" + html.escape("\n".join([fmt(header), sep] + [fmt(r) for r in body]), quote=False) + "</pre>"


def markdown_to_html(text: str, tables: str = "pre") -> str:
    stash: List[str] = []
    lines = text.replace("\r\n", "\n").split("\n")
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        fence = re.match(r"^\s*```\s*([\w+#-]*)\s*$", line)
        if fence:
            j = i + 1
            code: List[str] = []
            while j < len(lines) and not re.match(r"^\s*```\s*$", lines[j]):
                code.append(lines[j])
                j += 1
            body = html.escape("\n".join(code), quote=False)
            lang = fence.group(1)
            out.append(f'<pre><code class="language-{lang}">{body}</code></pre>' if lang else f"<pre>{body}</pre>")
            i = j + 1
            continue
        if line.lstrip().startswith("|") and i + 1 < len(lines) and _is_sep(lines[i + 1]):
            rows = [_cells(line)]
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                rows.append(_cells(lines[j]))
                j += 1
            out.append(_table(rows, tables, stash))
            i = j
            continue
        if line.startswith(">"):
            quote: List[str] = [line]
            i += 1
            while i < len(lines) and lines[i].startswith(">") and not re.match(r"^>\s*(!|\[!collapse\])", lines[i]):
                quote.append(lines[i])
                i += 1
            expandable = bool(re.match(r"^>\s*(!|\[!collapse\])", quote[0]))
            quote[0] = re.sub(r"^>\s*(!|\[!collapse\])\s*", "> ", quote[0])
            inner = "\n".join(_inline(re.sub(r"^>\s?", "", q), stash) for q in quote)
            out.append(f"<blockquote{' expandable' if expandable else ''}>{inner}</blockquote>")
            continue
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$", line)
        if heading:
            out.append(f"<b>{_inline(heading.group(1), stash)}</b>")
        else:
            bullet = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
            out.append((bullet.group(1) + "• " + _inline(bullet.group(2), stash)) if bullet else _inline(line, stash))
        i += 1
    return _restore("\n".join(out), stash)


def to_html(text: str, fmt: str = "markdown", tables: str = "pre") -> str:
    if fmt == "markdown":
        return markdown_to_html(text, tables)
    if fmt == "html":
        return text
    return html.escape(text, quote=False)


def parse(text: str, fmt: str = "markdown", tables: str = "pre") -> Tuple[str, list]:
    """(plain text, Telethon entities) for the message as Telegram will show it."""
    if fmt not in FORMATS:
        raise ValueError(f"Unknown format '{fmt}'. Choose from: {', '.join(FORMATS)}")
    if fmt == "plain":
        return text, []
    from telethon.extensions import html as tl_html
    from telethon.tl.types import MessageEntitySpoiler, MessageEntityTextUrl

    plain, entities = tl_html.parse(to_html(text, fmt, tables))
    fixed = []
    for e in entities:
        if isinstance(e, MessageEntityTextUrl) and e.url.startswith(SPOILER_MARK):
            fixed.append(MessageEntitySpoiler(e.offset, e.length))
        else:
            fixed.append(e)
    return plain, fixed


class TelegramParseMode:
    """A Telethon parse_mode object: send_message(..., parse_mode=TelegramParseMode(...)) also resolves tg://user mentions."""

    def __init__(self, fmt: str = "markdown", tables: str = "pre"):
        self.fmt, self.tables = fmt, tables

    def parse(self, text: str):
        return parse(text, self.fmt, self.tables)

    def unparse(self, text, entities):
        from telethon.extensions import html as tl_html

        return tl_html.unparse(text, entities)


def split_message(text: str, limit: int = MAX_LEN) -> List[str]:
    """Split at blank lines (then line breaks), never inside a ``` block, so every part parses on its own."""
    if len(text) <= limit:
        return [text]
    blocks: List[str] = []
    current: List[str] = []
    in_code = False
    for line in text.split("\n"):
        if re.match(r"^\s*```", line):
            in_code = not in_code
        current.append(line)
        if not in_code and not line.strip():
            blocks.append("\n".join(current))
            current = []
    if current:
        blocks.append("\n".join(current))
    parts: List[str] = []
    buf = ""
    for block in blocks:
        while len(block) > limit:  # one huge block: cut at a line break, else hard
            cut = block.rfind("\n", 0, limit)
            cut = cut if cut > 0 else limit
            if buf.strip():
                parts.append(buf.strip("\n"))
                buf = ""
            parts.append(block[:cut].strip("\n"))
            block = block[cut:].lstrip("\n")
        if len(buf) + len(block) + 1 > limit and buf.strip():
            parts.append(buf.strip("\n"))
            buf = ""
        buf = f"{buf}\n{block}" if buf else block
    if buf.strip():
        parts.append(buf.strip("\n"))
    return parts
