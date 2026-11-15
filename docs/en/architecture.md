# Architecture and development

[Index](index.md) · **English** · [فارسی](../fa/architecture.md)

## Layout (`src/versline/`)

| Path | Role |
| :--- | :--- |
| `cli.py` | Typer app, global options, update notice. Heavy modules are imported lazily so `init/config/update/--version` start fast |
| `commands/` | Thin CLI wrappers (`transcribe`, `translate`, `summarize`, `qude`, `qualcode`, `research`, `slides`, `telegram`, `organize`, `setup`, `bridge`, `obsidian`) |
| `config.py`, `userconfig.py` | pydantic-settings groups (llm, transcription, ffmpeg, resource, slides, telegram), env loading, per-user config folder |
| `services/` | Business logic: `transcription`, `translation`, `summarizer`, `question_generator`, `qualitative_coding`, `research_writing`, `slides`, `document_processor`, `export`, `media`, `network`, `ai` (provider clients, retries), `pricing` (token/cost tracking) |
| `services/channel_archive/` | Telegram archive: `sources/` (`telegram` via Telethon, `telegram_web` via httpx + BeautifulSoup), `steps.py` (media, transcribe, summary, taqrir), `pipeline.py`, `obsidian.py`, `state.py` (manifest), `llm.py` (single-prompt text and image generator), `models.py`, `discussion.py` (`telegram taqrir`: message log, media to text, map/reduce taqrir, `.versline-taqrir.json` cache) |
| `services/docexport/` | Shared Word/PDF export over MdPersia (optional): `frontmatter.py` (front-matter parser, metadata table), `normalize.py` (Obsidian to standard Markdown), `engine.py` (MdPersia adapter, lazy import), `service.py` (`export_items`, `ExportItem`, `ExportOptions`). Commands share `commands/_export.py` (`--export` options, `run_exports`). The Telegram pack is `channel_archive/pack.py` |
| `services/organize/` | Archive organizer (standard library only): `catalog.py` (SQLite, root paths relative to the drive root), `scanner.py` (incremental walk), `hashing.py` (SHA-256), `dupes.py` (duplicates, redundant folders), `reports.py` (Markdown/CSV), `rules.py` (rules.txt/taxonomy.txt), `planner.py` (plan, dedupe, name collisions), `applier.py` (journaled apply/verify/revert-moves), `kinds.py`, `normalize.py`. Design: [organize-design.md](../fa/organize-design.md) |
| `core/` | Constants, types, prompt loading, resource limits |
| `mcp/server.py` | MCP tools |
| `bridge/` | JSON interface (`versline bridge`): `protocol.py` (NDJSON events, `JobContext`, prompts/cancel over stdin), `registry.py` (`@tool`, `F(...)` fields with en/fa labels and UI hints, manifest), `adapter.py` (runs the CLI command functions in-process with Rich progress, cost report and prompts turned into events), `runner.py`, `tools/` (one module per area) |
| `services/obsidian_plugin.py`, `services/releases.py` | Versobs plugin installer (`versline obsidian`), GitHub release lookup/download shared with `versline update` |
| `resources/prompts`, `resources/assets` | Bundled prompts, Vazirmatn font, slide assets |

Providers: Google (google-genai with context caching), OpenAI, OpenRouter, AvalAI (exact cost lookup), OpenAI-compatible. API calls retry automatically; token usage and cost are tracked and printed at the end of a run.

## Telegram pipeline

For each selected post `ChannelArchiver` runs steps in order: **media** (download only what is needed; temp files deleted unless `--keep-media`) → **transcribe** (video converted to mp3 by ffmpeg, chunked transcription, cache in `work_dir/<stem>/progress.json`) → **summary** → **taqrir**. The note is written atomically and the manifest updated; failures are isolated per post.

`telegram taqrir` (`DiscussionBuilder`) reuses the source, `transcribe_media` and `TextLLM`: messages → text per message (transcripts, document text via MarkItDown, image text via the vision model; cached) → one log with anonymous or named participants → one LLM call per style, or notes per part (cached) then one call per style for long logs → taqrir note + log note with `^m<id>` blocks for citations.

## Reliability

Writes are atomic (temp file then replace); failed posts are retried on the next run; transcription is resumable per chunk. Commands exit with status 1 on failure.

## Tests

```sh
make test      # python -m pytest tests -q
```

21 test files cover config, resource limits, transcription (provider resolution, STT fallback, word alignment), summarizer, slides, qude, qualcode, research, pricing, and the Telegram archive (`test_channel_obsidian.py`, `test_channel_pipeline.py`, `test_channel_web.py`). CI runs on Ubuntu, Windows and macOS with Python 3.12.

## Releasing

See [Installation](installation.md#releasing-maintainers). Windows builds are produced by `packaging/build.py` (PyInstaller `--onedir`, ffmpeg pre-fetched, smoke-tested with `versline.exe --version`).
