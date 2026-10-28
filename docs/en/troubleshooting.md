# Troubleshooting

[Index](index.md) · **English** · [فارسی](../fa/troubleshooting.md)

## General

- **`versline` not found after install**: open a *new* terminal. On macOS/Linux run `uv tool update-shell`.
- **No API key / wrong provider**: run `versline init`, then `versline config` to inspect (secrets are masked).
- **Network blocked or API unreachable**: set `VERSLINE_LLM_PROXY` or pass `--proxy socks5://127.0.0.1:10808`.
- **Persian text looks broken on Windows**: it is a console font limitation; open the output file in an editor.
- **ffmpeg errors**: ffmpeg is bundled/auto-downloaded; to use your own, set `VERSLINE_FFMPEG_FFMPEG_PATH` and `VERSLINE_FFMPEG_FFPROBE_PATH`.
- **Interrupted long transcription**: re-run the same command; finished chunks are cached. Use `--force` to start over.
- **Provider blocks a chunk (content policy)**: use `--skip-blocked`.
- **See what is happening**: `versline -v <command> ...`.
- **`versline download` does not exist**: pass the URL straight to `versline transcribe`.
- **Resource limits ignored**: they are library-only; see [Configuration](configuration.md#resource-limits-library-only).
- **Slides `--build` fails**: needs Node.js/npm; behind a filter use `--npm-registry` (e.g. `https://registry.npmmirror.com`).

## Telegram

- **"Not logged in to Telegram"**: run `versline telegram login` (env variables alone don't log you in) or use `--web` for a public channel.
- **"api_id/api_hash are not set"**: add them to the env file or run `versline telegram login` to be asked.
- **Web mode says "not found or its web preview is disabled"**: the channel is private, nonexistent, or has the preview disabled; use logged-in mode.
- **`audio not downloadable` in `skipped_media`**: a web-preview limit; use logged-in mode.
- **Nothing for a date range**: check with `--dry-run`; dates use local time, Shamsi years (< 1700) are converted.
- **Titles/tags look old after an update**: re-run with `--reuse-transcripts` (or `--force`).
- **Telegram rate limiting in web mode**: Versline backs off automatically; re-run later to resume.
