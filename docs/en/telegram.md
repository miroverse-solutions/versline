# Telegram channel archive

[Index](index.md) · **English** · [فارسی](../fa/telegram.md)

Archive a Telegram channel into an Obsidian vault, or write a [taqrir of a chat's discussions](#discussion-taqrir-telegram-taqrir): **one Markdown note per post** (caption, transcript of audio/video, optional summary and *taqrir*, rich frontmatter) plus a channel index note. Works for audio/video, text-only and mixed channels.

## Quick start

```sh
# 1. Log in once (skip this and use --web for public channels)
versline telegram login

# 2. Preview a date range (nothing is downloaded or written)
versline telegram archive @channel --since 2026-03-01 --until 2026-03-31 --dry-run

# 3. Archive into your vault
versline telegram archive @channel --since 2026-03-01 --until 2026-03-31 -o ~/Vault/Telegram/channel
```

LLM settings come from `VERSLINE_LLM_*` / `versline init`, or the overrides below. Transcription needs an LLM provider; ffmpeg is bundled.

## Two ways to connect

| | Logged-in account (default) | Web preview (`--web`) |
| :--- | :--- | :--- |
| Needs `api_id`/`api_hash` + `telegram login` | Yes | **No** |
| Channels | Public, private, joined via invite link | **Public only** (`@name`, `t.me/name`) |
| Audio files, documents, large videos | Downloaded and transcribed | **Not downloadable**: the post still gets a note; the item is listed in `skipped_media` as "<kind> not downloadable" |
| Voice messages, round videos, small videos | Yes | Yes |
| Speed | Fast | Slower (polite 0.4 s delay, backoff on HTTP 429); date ranges are located by binary search |

**Logged-in mode.** Get `api_id`/`api_hash` at <https://my.telegram.org> → *API development tools*. Put them in your env (`VERSLINE_TELEGRAM_API_ID`, `VERSLINE_TELEGRAM_API_HASH`) or let `versline telegram login` ask and save them. Login asks for phone number, code and (if enabled) 2FA password. Setting the variables alone is **not** a login. The session file (in the config folder, or `VERSLINE_TELEGRAM_SESSION_PATH`) grants access to your account: keep it private. `versline telegram logout` ends the session and deletes the file.

**Web mode.** `--web` reads `https://t.me/s/<channel>`; private channels, invite links and `t.me/c/...` are rejected. A missing channel or disabled preview gives a "not found" error.

**Proxy.** For Telegram the order is `--telegram-proxy` → `VERSLINE_TELEGRAM_PROXY` → `--proxy`/`VERSLINE_LLM_PROXY`. Schemes: `socks5`, `socks5h`, `socks4`, `http`, `https`. On `archive`, `--proxy` is for the LLM provider.

## `telegram login` / `logout`

```sh
versline telegram login [--proxy URL]
versline telegram logout
```

## `telegram archive`

```sh
versline telegram archive [OPTIONS] CHANNEL
```

`CHANNEL`: `@name`, `name`, `https://t.me/name`, `t.me/s/name`, `https://t.me/c/<id>` (private) an invite link of a channel you already joined, or a **numeric id** such as `-1001234567890` or `1234567890` (any form `telegram chats` or a bot shows; no `--` needed). Links to `t.me/c`, invite links and ids need logged-in mode.

### Selecting posts

| Option | Description | Default |
| :--- | :--- | :--- |
| `--since`, `--until` | `YYYY-MM-DD[ HH:MM]`, Gregorian or Shamsi (`1404-07-01`; years < 1700 are Shamsi; Persian digits and `/` accepted). A date without time covers the whole day; `--until` is inclusive. | whole channel |
| `--limit N` | At most N matching posts | no limit |
| `--types` | Comma list of `audio,voice,video,video_note,photo,document,text` | all |
| `--dry-run` | Table of matching posts (ID, date, type, duration, title, plus the matching files when a file filter is used); writes nothing | off |

A post's type is the type of its **first** media item (album starting with a photo = `photo`); without media = `text`. Only voice, audio, video and video_note are transcribed; other types get caption and metadata.

### Filtering files

Pick documents by extension and by name (or caption). Works in the normal archive (with `--keep-media`, only matching files are downloaded) and in `--files-only` mode.

| Option | Description | Default |
| :--- | :--- | :--- |
| `--ext` | Comma list of extensions, e.g. `pdf,docx`; `word` = `doc,docx`. Taken from the file name, else the mime type | any |
| `--match REGEX` | Keep files matching **at least one** pattern (repeatable) | any |
| `--exclude REGEX` | Drop files matching **any** pattern (repeatable); wins over `--match` | none |
| `--match-in` | What the patterns test: `name` (file name), `caption` (post text) or `any` (either) | `name` |
| `--files-only` | Save the matching files under their original names in the output folder: no notes, no transcription, no LLM (unless `--ocr`). Cannot be combined with `--summary`, `--taqrir`, `--reuse-transcripts`; add `--to-markdown` for a note next to each document | off |

Patterns are Python regexes, case-insensitive; a plain word works as is. Persian text is normalized on both sides first: `ي/ك` → `ی/ک`, tatweel and diacritics dropped, ZWNJ and `_` count as spaces, so `--match "جزوه فقه"` finds `جزوه_فقه.pdf`. The filter works per file: in an album with a PDF and a photo, only the PDF is kept. Combine freely with `--since/--until`, `--limit`, `--types`, `--max-size`; use `--dry-run` to preview (a *Files* column lists the matches).

`--files-only` keeps its own manifest (`.versline-files.json`), so reruns skip finished posts and don't interfere with a normal archive in the same folder. A file whose name and size match one already in the folder is a duplicate and is not downloaded again; the same name with a different size is saved as `name (post <id>).ext`. Documents need logged-in mode: with `--web` they are reported as skipped.

### Documents to Markdown (Obsidian)

With `--to-markdown` every document of a post becomes a **Markdown note** you can read, search and link in Obsidian: PDF, Word (`docx`; `doc`, `rtf`, `odt` through LibreOffice), PowerPoint (`pptx`; `ppt`, `odp` through LibreOffice), Excel (`xlsx`, `xls`), EPUB, HTML, and text files (`txt`, `md`, `csv`, `json`, `srt`…). Other files (zip, apk…) are left alone. Combine it with `--ext`/`--match` to convert only some files.

```sh
# PDFs and Word files of a channel, as notes in the vault
versline telegram archive @chan --types document --ext pdf,word --to-markdown -o ~/Vault/Telegram/chan

# Scanned booklets too: pages without a text layer are read by the AI model
versline telegram archive @chan --types document --to-markdown --ocr -o ~/Vault/Telegram/chan
```

- **Where:** `documents/<file name>.md` (another post's document with the same name: `<name> (post <id>).md`). The post note gets an **اسناد** section linking each document note, and every document note links back to its post.
- **Frontmatter:** `type: telegram-document`, `title`, `post` (link to the post note), `file_name`, `source_file` (link to the original, with `--keep-media`), `channel`, `post_id`, `url`, `date`, `date_shamsi`, `file_size`, `mime`, `pages`, `converter`, `ocr_model`, `ocr_pages`, `conversion_warnings`, `tags` (the post's hashtags + `telegram`, `document`), `aliases` (the file name).
- **Body:** Word headings, lists and tables stay Markdown; slides and sheets become sections and tables. PDF text is taken page by page in reading order (Persian and Arabic included), with a hidden `%% صفحه ۳ %%` marker before each page. Characters that would break Obsidian (`[[`, `%%`, Arabic presentation forms, control characters, inline base64 images) are cleaned.
- **Without `--keep-media`** the original file is deleted after conversion and only the note stays; with it, the file is in `attachments/`, embedded in the post note and linked from the document note.
- **Old archives:** run the same command with `--to-markdown` on an existing archive and the documents of posts archived earlier are converted and an **اسناد** section is added to their notes; nothing else in those notes changes (transcripts, summaries and your edits stay) and nothing is transcribed again. A file already in `attachments/` is not downloaded again.
- **With `--files-only`:** a note named `<file name>.md` is written next to each saved file (`<name>.pdf.md` when the plain name is taken), with `source_file` linking the file. `.md` files are saved as they are. Rerunning with `--to-markdown` adds notes to files saved earlier without downloading them again.
- A document that can't be converted doesn't fail the post: it is listed at the end of the run and in the post's `skipped_media`, and retried on the next run.

**Scans (OCR).** A scanned PDF has no text layer, so without OCR its note only carries a warning. `--ocr` (implies `--to-markdown`) renders each page without text as an image and has the **multimodal LLM** read it (any Gemini model, gpt-4o-class models), and also converts image files sent as documents (`jpg`, `png`, `webp`, `tif`). Pages with text are taken as they are. `--ocr-all` reads every page with the model, for PDFs whose text comes out garbled (old Persian fonts, letters out of order). Each page read is cached in `.versline-ocr.json` in the output folder, so an interrupted run or a rerun never pays for a page twice (`--force` reads again). `--ocr-max-pages N` (default 200) caps the pages sent to the model per document; the rest are marked as unread. OCR costs tokens and shows in the cost report: try `--limit 1` on a big booklet first. Documents converted earlier without `--ocr` whose scanned pages were left unread are completed when you rerun with `--ocr`. The prompt is `telegram_document_ocr_prompt.md`.

| Option | Description | Default |
| :--- | :--- | :--- |
| `--to-markdown` | Convert documents to Markdown notes | off |
| `--ocr` | Read scanned PDF pages and image files with the multimodal LLM (implies `--to-markdown`) | off |
| `--ocr-all` | Read every PDF page with OCR, not only scans (implies `--ocr`) | off |
| `--ocr-max-pages N` | Pages sent to the model per document | 200 |

### Output

| Option | Description | Default |
| :--- | :--- | :--- |
| `-o, --output` | Output folder (point at your vault) | `output/<channel>` |
| `--keep-media` | Save media in `attachments/` and embed it | off |
| `--max-size MB` | Skip larger media (recorded in `skipped_media`) | no limit |
| `--no-transcribe` | Captions and metadata only | off |

### Multi-part posts

Long items are often split across consecutive posts. With `--merge-parts` such a chain becomes **one note**.

| Option | Description | Default |
| :--- | :--- | :--- |
| `--merge-parts` | Merge a post into the previous one when they were sent within the gap and the previous ends with a continuation marker (`⬇️`, `👇`, `ادامه دارد`, `ادامه در پست بعد`) **or** the next starts with one (`⬆️`, `👆`, `ادامه`, `ادامه‌ی پست قبل`) | off |
| `--merge-gap MIN` | Max minutes between parts | 15 |

The marker lines are removed and the texts joined; media of all parts is kept (and transcribed) in order. The note is named after the first part, its frontmatter has `post_ids` and `part_urls`, and the footer links every part. In `.versline-channel.json` the first post gets `parts: [...]` and the others `merged_into`. Parts archived earlier as separate notes are merged on the next run with the flag: their old notes are deleted and their transcripts reused, so nothing is transcribed again. A chain cut by `--until` is merged on a later run that covers the whole chain. Ignored with `--files-only`.

### Extra sections (LLM)

| Option | Description |
| :--- | :--- |
| `--summary` | Adds **خلاصه** (summary) at the top, from transcript or caption; skipped for content under ~300 characters |
| `--taqrir` | Adds **تقریر و صورت‌بندی** after the transcript: the talk rewritten as a structured written exposition (issue, claims, arguments, objections, conclusion), faithful to the speaker. For text posts, built from captions of ≥ ~300 characters with a prompt for written text |
| `--output-lang` | Language of summary/taqrir (default: same as content) |

Prompts live in `src/versline/resources/prompts/` (`channel_summary_prompt.md`, `channel_taqrir_prompt.md`, `channel_taqrir_text_prompt.md`). Costs appear in the final cost report; try `--limit 3` first on big channels.

### Resuming and redoing

- Re-running skips posts already archived (manifest `.versline-channel.json`). A failing post is recorded as failed and retried next run without stopping the others. Ctrl+C is safe (exit code 130); run the same command to resume.
- `-f, --force`: redo posts from scratch including transcription.
- `--reuse-transcripts`: redo captions, titles, tags, `--summary`, `--taqrir` but keep the transcript already stored in each note (no download, no new transcription cost). Posts without a stored transcript are transcribed. Wins over `--force`. Edits to a note's transcript are preserved; edits elsewhere in the note are overwritten.

### LLM and transcription overrides

`--model`, `--provider`, `--api-key`, `--api-endpoint`, `--proxy` (LLM), `--telegram-proxy`, `--extra-body`, `--note`/`--note-file` (appended to the transcription prompt), `--chunk-size 900`, `--overlap 180`, `--skip-blocked`.

## What gets written

```text
<out>/
├── <Channel title>.md                 # index: table of archived posts
├── .versline-channel.json             # manifest for resuming
├── .versline-ocr.json                 # pages read with --ocr (cache)
├── posts/
│   └── 2026-03-14 - 223 - <title>.md  # one note per post
├── documents/                         # only with --to-markdown
│   └── <file name>.md                 # one note per document
└── attachments/                       # only with --keep-media
```

Each note: frontmatter, `# title` (first meaningful caption line without hashtags/links/Markdown, max 80 chars; fallback `پست <id>`), **خلاصه**, **توضیحات** (caption), **متن پیاده‌شده** (transcript; albums become `### 1`, `### 2`), **تقریر و صورت‌بندی**, **اسناد** (links to the document notes, with `--to-markdown`), **پیوست‌ها** (`![[...]]` embeds), then a link to the original post.

Frontmatter always has `title, source, channel, channel_title, post_id, url, date, date_shamsi, media_type, tags, aliases, archived_at`; when applicable `duration, file_name, views, forwards, forwarded_from, album_size, transcribed, transcription_model, summary_model, taqrir_model, skipped_media`. Hashtags become `tags` (ZWNJ/space inside a hashtag becomes `_`; `telegram` is always added). The index note has `type: channel-index`, `post_count`, `range_from`, `range_to`, `updated` and a table of wikilinks. Model chatter such as an opening «بله، حتماً…» or closing «[---پایان فایل صوتی---]» is stripped from transcripts.

## Pack: a complete, tidy package

`versline telegram pack ARCHIVE_DIR` turns a finished archive into a shareable package, offline (nothing is downloaded again). Needs `versline[export]`.

```text
<output>/<channel>_pack/<channel>_<from>_<to>/
├── README.md, README.pdf            channel, date range, post count, total audio length, what is where
├── <Channel title>.docx / .pdf      the "book": cover, table of contents, chapters by Shamsi month, each post on a new page
├── posts/docx/…  posts/pdf/…        one Word and one PDF file per post
├── notes/                           the Markdown notes + index (open as an Obsidian vault), with attachments
├── catalog.csv, catalog.xlsx        one row per post: dates, title, type, length, views, link, note/Word/PDF paths, attachments
<output>/<channel>_pack/<channel>_<from>_<to>.zip   everything above in one file
```

| Option | Meaning |
| :--- | :--- |
| `--output`, `-o` | Folder to create the pack in |
| `--to docx,pdf` | Formats of the book and per-post files |
| `--front-matter` / `--no-front-matter` | Metadata table under the cover and each post title |
| `--per-post` / `--no-per-post` | One file per post (default on) |
| `--media` / `--no-media` | Copy attachments into `notes/` (default on) |
| `--toc` / `--no-toc` | Table of contents in the book: clickable links, grouped by Shamsi month (default on) |
| `--zip` / `--no-zip` | Create the ZIP (default on) |
| `--since`, `--until` | Limit to a date range (Gregorian or Shamsi) |
| `--force`, `-f` | Rebuild per-post files that are up to date |

Merged multi-part posts appear once. Rerunning is cheap: up-to-date per-post files are skipped; the book, catalog, README and ZIP are rebuilt.

With `archive` you can do it in one go: `--pack` builds the full pack after archiving, and `--export docx,pdf` only writes per-post files to `<output>/exports/`.

## Discussion taqrir: `telegram taqrir`

`versline telegram taqrir CHAT --since … --until …` reads every message of a chat (private chat, group, supergroup or channel) in a date range and writes **one taqrir note for the whole range**. Useful for study groups and scholarly debates held in voice messages, texts, PDFs and photos of book pages.

- **Voice, audio and video** are transcribed (same engine and cache as `archive`).
- **Documents** (pdf, docx, pptx, xlsx, html, txt, md…) are read as text; at most `--doc-chars` characters per document (default 30000).
- **Photos** are read by the vision model (book pages, handwriting, screenshots, tables); turn off with `--no-images`.
- Replies (`in reply to #id`) and forwards are kept, so the model can follow who answered whom.

```sh
# Find the chat (private chats and basic groups have no username)
versline telegram chats --search "مباحثه"

# Preview the range: messages, senders, media (nothing downloaded, no LLM)
versline telegram taqrir @study_group --since 1404-07-01 --until 1404-07-15 --dry-run

# Taqrir + claims with evidence in one note, into the vault
versline telegram taqrir @study_group --since 1404-07-01 --until 1404-07-15 -o ~/Vault/Taqrir

# A chat by numeric id, as `telegram chats` prints it (-100…, -…) or the bare id; works in `archive` too
versline telegram taqrir -1001234567890 --since 1404-07-01 --style claims
```

### Styles

| `--style` | Section | What it is |
| :--- | :--- | :--- |
| `descriptive` | **تقریر** | Scholarly prose, one `###` per topic: the question, positions with their formulated arguments, evidence, objections and replies, outcome |
| `claims` | **ادعاها و ادله** | Each point in dispute (`محل بحث`) with its propositions as precise, atomic bullets (`گزاره ۱.۱`) and, under each, its evidence (`دلیل`), objections (`اشکال`) and replies (`پاسخ`); a proposition with no evidence is marked as such |
| `both` (default) | both | Both sections in one note |

Every point cites its messages: `[#123]` becomes a link to the message on t.me (channels and supergroups) or to the message in the log note (private chats and basic groups).

### Participants

By default participants are **anonymous**: the log the model sees labels them «شرکت‌کننده ۱», «شرکت‌کننده ۲»… (stable per person), and the taqrir uses those labels or impersonal phrasing. `--attribute` uses real names instead and lists them in the frontmatter (`participants`).

### Output

In `output/<chat>/taqrir/` (or `-o`):

- `<from> تا <to> - تقریر.md`: frontmatter (`type: chat-taqrir`, chat, dates in Gregorian and Shamsi, number of messages, participants, voices, documents and images read, style, model), the sections, **منابع** (the documents shared) and a link to the log.
- `<from> تا <to> - متن کامل گفتگو.md`: the full message log by day: each message is a `### id · time · participant` heading under its `##` day, then a line with the date, the message it replies to (linked) and its t.me link, then the text, transcripts, and document/image text in collapsed callouts. That line carries a block id (`^m123`), so citations jump straight to the message. `--no-log` skips this file.
- `-X docx,pdf` also exports the taqrir note to Word/PDF.

### Long chats, cache and resume

Transcripts, document text and image text are cached in `.versline-taqrir.json` in the output folder after each message: an interrupted run continues where it stopped, and a rerun (for example with another `--style`) reads nothing again. A failed file is reported and retried on the next run; it doesn't stop the taqrir.

A log longer than `--max-chars` (default 150000) is cut into parts at day (or message) boundaries. The model first takes structured notes on each part (cached too), then writes each style from all the notes, so a rerun with another style costs one call per style. `--force` ignores the cache.

### Options

| Option | Meaning |
| :--- | :--- |
| `--since`, `--until` | Date range (Gregorian or Shamsi, optional `HH:MM`) |
| `--style` | `descriptive`, `claims` or `both` |
| `--attribute` | Name the participants |
| `--no-transcribe`, `--no-documents`, `--no-images` | Don't read that kind of media (it still appears as a marker) |
| `--types`, `--limit` | Only some message types / at most N messages |
| `--output-lang` | Language of the taqrir (default: that of the discussion) |
| `--instruction`, `--instruction-file` | Extra guidance for the taqrir, e.g. «فقط بحث دلالت امر بر وجوب» |
| `--note`, `--note-file` | Extra instruction for the transcription prompt (as in `archive`) |
| `--doc-chars`, `--max-chars`, `--max-size` | Per-document limit, part size for long logs, skip media over N MB |
| `--no-log`, `--dry-run`, `--force` | See above |
| `-X`, `--export-frontmatter` | Word/PDF export |

The LLM overrides (`--model`, `--provider`, `--api-key`, `--api-endpoint`, `--proxy`, `--telegram-proxy`, `--extra-body`, `--chunk-size`, `--overlap`, `--skip-blocked`) work as in `archive`. Photos need a multimodal model (any Gemini model, gpt-4o-class models). A logged-in account is required (`telegram login`); `--web` is not available here.

## Requests from a chat: taqrir or passages of a talk (Obsidian)

Keep the talks you listen to in a chat of your own — Saved Messages, or a private group or channel — and reply to one of them with a text or voice message:

* "تقریر کن" (or any request for the whole talk, with a focus if you like): a **taqrir** of the talk.
* A description of what you remember, e.g. "the narration he read from Imam Sadiq about patience" or "the two points about raising children": the **passages** where it was said — verbatim text, start and end time, and a short audio clip of each.

Then run **Telegram: answer my requests** in Obsidian (bridge tool `telegram.requests`). It reads the chat from where the last run stopped (the first run looks back 3 days), answers each new request as a reply in Telegram, and writes the same answer to a note under `<Telegram folder>/Requests`: `<talk> - taqrir.md`, or `<talk> - points.md`, which collects every search in that talk.

* Only your own replies to a voice/audio/video message count, so other members of a group are ignored. Versline's replies start with 🤖 and are never taken as requests.
* Times come only from the STT model's own (native) timestamps — word by word with `elevenlabs/scribe-v2`, the default on OpenRouter. If the timestamp model gives none, times are estimated from the text and the note says so.
* Each talk is transcribed once (with timestamps) and remembered, so later requests about it cost one short text-model call. Transcripts are kept in `~/.cache/versline/transcripts` (`VERSLINE_CACHE_DIR` moves it).
* Times come from the transcript itself, not from the model's guess: a passage the model "finds" but the transcript does not contain is dropped. Each passage is transcribed again on its own, for an exact text of Arabic narrations and quotations (turn off with `refine`).
* A request that fails is retried on the next two runs; the reply says so.
* The same is available for a file in the vault: **Find a passage with Versline…** and **Taqrir with Versline** in the file menu (bridge tools `audio.find` and `audio.taqrir`).

## Lists: `contacts`, `chats`, `members`

```sh
# Contacts with name, phone, username and id (a table, or a file)
versline telegram contacts
versline telegram contacts --search "رضا" --mutual -o contacts.csv

# Private chats only, unread ones, archived ones…
versline telegram chats --type user --limit 500 -o private.csv
versline telegram chats --type user,bot --unread
versline telegram chats --type group,supergroup --archived

# Chats whose last message falls in a date range (Gregorian or Shamsi), or from/until one date
versline telegram chats --since 1404-07-01 --until 1404-07-30 -o mehr.csv
versline telegram chats --type user --since 2026-01-01

# Members of a group you belong to
versline telegram members @group -o members.csv
```

`-o FILE` writes `.csv` (UTF-8 with BOM, opens correctly in Excel), `.md` (a table) or `.json`; without it a table is printed. Columns: `id, name, username, phone, type` (`contacts` adds `mutual`, `chats` adds `last_message, unread, archived`). `--limit N` caps the list; by default it is 50 when printing, and **no limit** when you give `--since`/`--until` or `-o FILE` (all matching chats). `--search` matches name, username or phone. `--since`/`--until` keep chats by the date of their **last message** (a date without time covers the whole day; `--until` is inclusive). Chat types: `user`, `bot`, `group`, `supergroup`, `channel`.

How much is read from Telegram: `contacts` is a single request. `chats` reads newest first and stops at `--limit`, or at the first chat older than `--since`; `--until` and `--archived/--no-archived` are passed to Telegram so newer or other-folder chats are never downloaded. `--search`, `--type` and `--unread` can only be checked locally, so with them the scan continues until `--limit` chats match (keep `--limit` modest). `telegram send` reads your contacts once, and reads the chat list only for recipients your contacts can't resolve.

Phone numbers are shown only for contacts and for people who share their number with you; members lists are limited by Telegram (in channels only admins can list members). A `.csv` or `.md` list written here is exactly what `telegram send` reads. In Obsidian the same lists are the `telegram.contacts`, `telegram.chats` and `telegram.members` tools.

## Bulk send: `telegram send`

```sh
versline telegram send RECIPIENTS (-m TEXT | --message-file FILE | --forward LINK…) [options]
```

Sends one message to everyone in a list **slowly and with pauses**, so the account is not rate-limited or banned and the session survives.

```sh
# Check the text first: it goes to your Saved Messages, formatted as the first recipient would see it
versline telegram send contacts.csv -m "سلام {name} 🌷" --test

# See who would get it and how long it takes; nothing is sent
versline telegram send contacts.csv --message-file invite.md --dry-run

# Send (asks to confirm; -y skips that)
versline telegram send contacts.csv --message-file invite.md --attach poster.jpg

# Forward a channel post to a list, as if you sent it yourself
versline telegram send friends.md --forward https://t.me/channel/123 --hide-source -m "این را ببین {first_name}"
```

### The recipient list

`.csv`, `.md` or `.txt`. A header row is recognised in English or Persian: `id`, `username` / `آیدی` / `یوزرنیم`, `phone` / `شماره` / `موبایل` / `تلفن`, `name` / `نام`. If several exist the order is id, username, phone, name; `--column NAME` picks the column yourself. Other columns are kept and usable as placeholders. In Markdown use a pipe table or one entry per line (`- @ali`, `09121234567`, `علی رضایی`). Entries are recognised by shape: `@name` or t.me link = username, a number starting with `+`, `00` or `0` = phone, another integer = id, anything else = name.

How people are found:

- **Phone**: only among your Telegram contacts (any spelling matches: `0912…`, `+98912…`, Persian digits). A number that is not a contact is **skipped and reported**; the tool never imports contacts in bulk, which is itself a spam signal.
- **Name**: the exact name of one contact or private chat; several matches are skipped as ambiguous.
- **Username / id**: your contacts and chats first, then Telegram (these lookups are throttled).
- The same person twice is sent to once.

### The message

`-m TEXT` or `--message-file FILE` (.md/.txt), up to any length (split at paragraphs into parts of 4096 characters). `{name}`, `{first_name}`, `{last_name}`, `{username}`, `{phone}`, `{id}` and every CSV column (`{city}`) are filled per person; unknown `{…}` stay as typed. `--attach FILE` sends a photo, video, document or voice with the text as its caption (uploaded once, reused). `--no-preview` turns link previews off.

Formatting uses Markdown (`--format markdown`, the default; `html` takes Telegram HTML, `plain` sends the text untouched):

| Write | Result |
| :--- | :--- |
| `**bold**`, `*italic*`, `__underline__`, `~~strike~~` | bold, italic, underlined, struck through |
| `\|\|spoiler\|\|` | spoiler |
| `` `code` `` and ```` ```py … ``` ```` | inline code, code block |
| `[text](https://…)`, plain URLs, `@username` | links and mentions |
| `[name](tg://user?id=123)` | mention by id |
| `> quote`, `>! long quote` | quote, collapsible quote |
| `![🙂](emoji:5368324170671202286)` | premium custom emoji (the sending account needs Premium) |
| `# Heading`, `- item` | bold line, `•` line (Telegram has no headings or lists) |
| pipe tables | `--tables pre` (default): aligned monospace block; `--tables list`: `Header: value` lines, nicer for Persian |
| Unicode emoji | as they are |

For anything Telegram's own editor can do, compose the message in **Saved Messages** and send it with `--forward me:last --hide-source`: it is copied exactly.

### Forwarding

`--forward` (repeatable) takes `https://t.me/<channel>/<id>`, `https://t.me/c/<id>/<id>`, `<chat>:<id>` (any chat reference, e.g. `-1001234567890:42`) or `me:last`. An album is forwarded whole; add `?single` to take one message. `--hide-source` sends it without «Forwarded from», `--hide-caption` drops media captions. `-m` becomes a personal note sent just before the forward. Chats with forwarding disabled are refused before anything is sent.

### Pacing

| Option | Default | Meaning |
| :--- | :--- | :--- |
| `--delay MIN-MAX` | `20-45` | random seconds between messages |
| `--batch-size N` / `--batch-pause S` | `10` / `300` | a longer pause (±20 %) after every N messages |
| `--daily-limit N` | `100` | at most N messages in 24 hours, counted across runs and lists (`0` = off) |
| `--ignore-daily-limit` | off | this run only: do not apply the 24-hour cap (sends are still recorded; risky for the account) |
| `--max-flood-wait S` | `3600` | if Telegram asks for a longer wait, stop and resume later |

The program waits out Telegram's own `FloodWait` requests and retries. If Telegram reports that the account is spam-limited (PeerFlood) it **stops at once**; check [@SpamBot](https://t.me/SpamBot). A person who blocked you or restricts messages is marked failed and the run continues. These defaults are conservative; shorter delays and bigger batches raise the risk.

### Resume and report

Progress is saved after every message in `<list>.send-state.json`. After Ctrl+C, a stop (limit, flood) or a crash, run **the same command** again: people already sent to are skipped. Changing the message starts a fresh send; `--restart` forces it. At the end `<list>.send-report.csv` lists every recipient with status (`sent`, `failed`, `skipped`) and the reason.

### Use it responsibly

Send only to people who expect to hear from you. Many identical messages to people who did not ask for them get accounts limited or banned regardless of pacing; personalising with `{name}` and keeping lists small helps, but does not make unsolicited messages safe. Try the options first with a list of two or three of your own accounts.

## Recipes

```sh
# Audio channel: transcripts + summary + taqrir, media kept
versline telegram archive @lectures --since 1404-07-01 --summary --taqrir --keep-media -o ~/Vault/Telegram/lectures

# Text-only public channel, no login
versline telegram archive @news --web --types text --summary --taqrir

# Add summary/taqrir to already archived posts without re-transcribing
versline telegram archive @lectures --since 1404-07-01 --summary --taqrir --reuse-transcripts -o ~/Vault/Telegram/lectures

# Only PDF/Word files whose name contains "جزوه" but not "پیش‌نویس" or "draft"
versline telegram archive @chan --files-only --ext pdf,word --match "جزوه" --exclude "پیش‌نویس|draft" -o ~/Downloads/chan

# The same files as Obsidian notes, scanned booklets read with OCR
versline telegram archive @chan --types document --ext pdf,word --match "جزوه" --to-markdown --ocr -o ~/Vault/Telegram/chan

# Preview PDFs whose caption or name says "جلسه <number>"
versline telegram archive @chan --files-only --ext pdf --match 'جلسه\s*\d+' --match-in any --dry-run

# Only spoken content, skip files over 200 MB, English summaries
versline telegram archive @lectures --types audio,voice,video --max-size 200 --summary --output-lang English
```

See also [Troubleshooting](troubleshooting.md#telegram).
