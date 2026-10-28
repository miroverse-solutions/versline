# Telegram channel archive

[Index](index.md) · **English** · [فارسی](../fa/telegram.md)

Archive a Telegram channel into an Obsidian vault: **one Markdown note per post** (caption, transcript of audio/video, optional summary and *taqrir*, rich frontmatter) plus a channel index note. Works for audio/video, text-only and mixed channels.

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

`CHANNEL`: `@name`, `name`, `https://t.me/name`, `t.me/s/name`, `https://t.me/c/<id>` (private) or an invite link of a channel you already joined (the last two need logged-in mode).

### Selecting posts

| Option | Description | Default |
| :--- | :--- | :--- |
| `--since`, `--until` | `YYYY-MM-DD[ HH:MM]`, Gregorian or Shamsi (`1404-07-01`; years < 1700 are Shamsi; Persian digits and `/` accepted). A date without time covers the whole day; `--until` is inclusive. | whole channel |
| `--limit N` | At most N matching posts | no limit |
| `--types` | Comma list of `audio,voice,video,video_note,photo,document,text` | all |
| `--dry-run` | Table of matching posts (ID, date, type, duration, title); writes nothing | off |

A post's type is the type of its **first** media item (album starting with a photo = `photo`); without media = `text`. Only voice, audio, video and video_note are transcribed; other types get caption and metadata.

### Output

| Option | Description | Default |
| :--- | :--- | :--- |
| `-o, --output` | Output folder (point at your vault) | `output/<channel>` |
| `--keep-media` | Save media in `attachments/` and embed it | off |
| `--max-size MB` | Skip larger media (recorded in `skipped_media`) | no limit |
| `--no-transcribe` | Captions and metadata only | off |

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
├── posts/
│   └── 2026-03-14 - 223 - <title>.md  # one note per post
└── attachments/                       # only with --keep-media
```

Each note: frontmatter, `# title` (first meaningful caption line without hashtags/links/Markdown, max 80 chars; fallback `پست <id>`), **خلاصه**, **توضیحات** (caption), **متن پیاده‌شده** (transcript; albums become `### 1`, `### 2`), **تقریر و صورت‌بندی**, **پیوست‌ها** (`![[...]]` embeds), then a link to the original post.

Frontmatter always has `title, source, channel, channel_title, post_id, url, date, date_shamsi, media_type, tags, aliases, archived_at`; when applicable `duration, file_name, views, forwards, forwarded_from, album_size, transcribed, transcription_model, summary_model, taqrir_model, skipped_media`. Hashtags become `tags` (ZWNJ/space inside a hashtag becomes `_`; `telegram` is always added). The index note has `type: channel-index`, `post_count`, `range_from`, `range_to`, `updated` and a table of wikilinks. Model chatter such as an opening «بله، حتماً…» or closing «[---پایان فایل صوتی---]» is stripped from transcripts.

## Recipes

```sh
# Audio channel: transcripts + summary + taqrir, media kept
versline telegram archive @lectures --since 1404-07-01 --summary --taqrir --keep-media -o ~/Vault/Telegram/lectures

# Text-only public channel, no login
versline telegram archive @news --web --types text --summary --taqrir

# Add summary/taqrir to already archived posts without re-transcribing
versline telegram archive @lectures --since 1404-07-01 --summary --taqrir --reuse-transcripts -o ~/Vault/Telegram/lectures

# Only spoken content, skip files over 200 MB, English summaries
versline telegram archive @lectures --types audio,voice,video --max-size 200 --summary --output-lang English
```

See also [Troubleshooting](troubleshooting.md#telegram).
