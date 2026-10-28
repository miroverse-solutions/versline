# Architecture and development

[Index](index.md) · **English** · [فارسی](../fa/architecture.md)

## Layout (`src/versline/`)

| Path | Role |
| :--- | :--- |
| `cli.py` | Typer app, global options, update notice. Heavy modules are imported lazily so `init/config/update/--version` start fast |
| `commands/` | Thin CLI wrappers (`transcribe`, `translate`, `summarize`, `qude`, `qualcode`, `research`, `slides`, `telegram`, `setup`) |
| `config.py`, `userconfig.py` | pydantic-settings groups (llm, transcription, ffmpeg, resource, slides, telegram), env loading, per-user config folder |
| `services/` | Business logic: `transcription`, `translation`, `summarizer`, `question_generator`, `qualitative_coding`, `research_writing`, `slides`, `document_processor`, `export`, `media`, `network`, `ai` (provider clients, retries), `pricing` (token/cost tracking) |
| `services/channel_archive/` | Telegram archive: `sources/` (`telegram` via Telethon, `telegram_web` via httpx + BeautifulSoup), `steps.py` (media, transcribe, summary, taqrir), `pipeline.py`, `obsidian.py`, `state.py` (manifest), `llm.py` (single-prompt text generator), `models.py` |
| `core/` | Constants, types, prompt loading, resource limits |
| `mcp/server.py` | MCP tools |
| `resources/prompts`, `resources/assets` | Bundled prompts, Vazirmatn font, slide assets |

Providers: Google (google-genai with context caching), OpenAI, OpenRouter, AvalAI (exact cost lookup), OpenAI-compatible. API calls retry automatically; token usage and cost are tracked and printed at the end of a run.

## Telegram pipeline

For each selected post `ChannelArchiver` runs steps in order: **media** (download only what is needed; temp files deleted unless `--keep-media`) → **transcribe** (video converted to mp3 by ffmpeg, chunked transcription, cache in `work_dir/<stem>/progress.json`) → **summary** → **taqrir**. The note is written atomically and the manifest updated; failures are isolated per post.

## Reliability

Writes are atomic (temp file then replace); failed posts are retried on the next run; transcription is resumable per chunk. Commands exit with status 1 on failure.

## Tests

```sh
make test      # python -m pytest tests -q
```

21 test files cover config, resource limits, transcription (provider resolution, STT fallback, word alignment), summarizer, slides, qude, qualcode, research, pricing, and the Telegram archive (`test_channel_obsidian.py`, `test_channel_pipeline.py`, `test_channel_web.py`). CI runs on Ubuntu, Windows and macOS with Python 3.12.

## Releasing

See [Installation](installation.md#releasing-maintainers). Windows builds are produced by `packaging/build.py` (PyInstaller `--onedir`, ffmpeg pre-fetched, smoke-tested with `versline.exe --version`).
