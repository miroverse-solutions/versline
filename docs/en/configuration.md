# Configuration

[Index](index.md) · **English** · [فارسی](../fa/configuration.md)

## Where settings live

The easiest way is `versline init`. It asks for the provider (Google, OpenAI, OpenRouter, AvalAI, OpenAICompatible), API key (hidden), model, endpoint (OpenAICompatible only) and an optional proxy, and saves them as `VERSLINE_LLM_*` variables in a per-user file `config.env` (permissions 600).

| Item | Location |
| :--- | :--- |
| Per-user config folder | `$VERSLINE_CONFIG_DIR`, else `%APPDATA%\versline` (Windows), else `$XDG_CONFIG_HOME/versline` or `~/.config/versline` |
| Settings file | `<config folder>/config.env` |
| Update-check cache | `<config folder>/last_update_check.json` |
| Telegram session | `<config folder>/telegram.session` |

Default models chosen by `init`: Google `gemini-2.0-flash`, OpenAI `gpt-4o-mini`, OpenRouter `~google/gemini-flash-latest`, AvalAI `gemini-2.0-flash`.

```sh
versline config          # show saved settings (keys/tokens/secrets masked)
versline config --path   # print the config.env path only
```

## Precedence (highest first)

1. Command-line options (`--api-key`, `--model`, `--proxy`, ...)
2. `versline --env-file /path/.env <command>` (global option, must come before the command)
3. Real process environment variables (`VERSLINE_*`)
4. File named by `VERSLINE_ENV_FILE`
5. `.env` in the current directory
6. Per-user `config.env`

In library mode use `reload_settings("/path/.env")` for a guaranteed override from a specific file.

## Global CLI options

Placed before the command name: `versline [OPTIONS] COMMAND ...`

| Option | Description |
| :--- | :--- |
| `--version` | Print the version and exit |
| `-v`, `--verbose` | Debug logging (default level is INFO) |
| `--env-file PATH` | Load this env file before running (must exist) |
| `--extra-body JSON` | JSON object merged into every OpenAI-compatible request body, e.g. `'{"reasoning": {"max_tokens": 1500}}'`. Not applied to native Gemini. |
| `--install-completion`, `--show-completion` | Shell completion |

## Environment variables

### LLM

| Variable | Default | Description |
| :--- | :--- | :--- |
| `VERSLINE_LLM_PROVIDER` | `Google` | `Google`, `OpenAI`, `OpenRouter`, `AvalAI`, `OpenAICompatible` |
| `VERSLINE_LLM_API_KEY` | | API key |
| `VERSLINE_LLM_MODEL` | `gemini-2.0-flash` | Model id |
| `VERSLINE_LLM_API_ENDPOINT` | | Custom base URL (required for `OpenAICompatible`; AvalAI defaults to `https://api.avalai.ir/v1`, OpenRouter to `https://openrouter.ai/api/v1`) |
| `VERSLINE_LLM_PROXY` | | `socks5://host:port` or `http://host:port` |
| `VERSLINE_LLM_AVALAI_PROVIDER` | | Upstream hint for AvalAI routing (`google`, `openai`, `anthropic`) |
| `VERSLINE_LLM_EXTRA_BODY` | | JSON merged into OpenAI-compatible request bodies |

### Transcription timestamps

Used by `transcribe --timestamped`. Empty connection values fall back to the matching `VERSLINE_LLM_*` setting.

| Variable | Default | Description |
| :--- | :--- | :--- |
| `VERSLINE_TRANSCRIPTION_TIMESTAMP_MODEL` | `gpt-4o-mini-transcribe` | STT model |
| `VERSLINE_TRANSCRIPTION_TIMESTAMP_CHUNK_MINUTES` | `3` | Chunk length for the chunk-based fallback |
| `VERSLINE_TRANSCRIPTION_TIMESTAMP_PROVIDER` | | `OpenAI`, `AvalAI`, `OpenRouter`, `OpenAICompatible` |
| `VERSLINE_TRANSCRIPTION_TIMESTAMP_API_KEY` | | STT API key |
| `VERSLINE_TRANSCRIPTION_TIMESTAMP_API_ENDPOINT` | | Base URL without `/audio/transcriptions` |
| `VERSLINE_TRANSCRIPTION_TIMESTAMP_PROXY` | | STT proxy |
| `VERSLINE_TRANSCRIPTION_TIMESTAMP_LANGUAGE` | `fa` | Language code (empty = auto-detect) |
| `VERSLINE_TRANSCRIPTION_TIMESTAMP_TIMEOUT_SECONDS` | `120` | HTTP timeout (legacy alias `VERSLINE_TRANSCRIPTION_STT_TIMEOUT_SECONDS`) |

### Media

| Variable | Description |
| :--- | :--- |
| `VERSLINE_FFMPEG_FFMPEG_PATH`, `VERSLINE_FFMPEG_FFPROBE_PATH` | Explicit binaries. Otherwise ffmpeg is taken from `PATH`, then from the bundled/`static-ffmpeg` copy. |

### General

| Variable | Default | Description |
| :--- | :--- | :--- |
| `VERSLINE_OUTPUT_DIRECTORY` | `output` | Default output folder |
| `VERSLINE_TEMP_DIRECTORY` | `temp` | Downloads and temporary media |
| `VERSLINE_SLIDES_NPM_REGISTRY` | | npm registry used by `slides --build` |
| `VERSLINE_ENV_FILE` | | Fallback env file |
| `VERSLINE_CONFIG_DIR` | | Override the per-user config folder |

### Telegram

| Variable | Description |
| :--- | :--- |
| `VERSLINE_TELEGRAM_API_ID`, `VERSLINE_TELEGRAM_API_HASH` | From <https://my.telegram.org> (only for logged-in mode) |
| `VERSLINE_TELEGRAM_PROXY` | Telegram proxy (falls back to `VERSLINE_LLM_PROXY`) |
| `VERSLINE_TELEGRAM_SESSION_PATH` | Custom session file path |

### Resource limits (library only)

`VERSLINE_RESOURCE_MAX_RAM_MB`, `VERSLINE_RESOURCE_MAX_CPU_CORES`, `VERSLINE_RESOURCE_MAX_GPU_VRAM_FRACTION` (default `0` = unlimited), `VERSLINE_RESOURCE_RAM_SOFT_TRIGGER_PCT` (50-100, default 85) and `VERSLINE_RESOURCE_RUN_WATCHDOG_WITH_CGROUP`.

> The CLI does **not** apply these limits automatically. They take effect only when your code calls `versline.core.resources.apply_resource_limits(...)`:
> RAM via cgroup v2 `memory.max` (Linux, with an RSS watchdog fallback), CPU via `os.sched_setaffinity` (Linux/POSIX), GPU via `torch.cuda.set_per_process_memory_fraction`.

## Example `.env`

See [`.env.example`](../../.env.example) in the repository for a fully commented template.

```dotenv
VERSLINE_LLM_PROVIDER=OpenRouter
VERSLINE_LLM_API_KEY=sk-or-...
VERSLINE_LLM_MODEL=~google/gemini-flash-latest
VERSLINE_LLM_PROXY=socks5://127.0.0.1:10808
```

## AvalAI notes

- Gemini model ids (e.g. `gemini-3-flash-preview`) automatically send provider hint `google`, unless you set `VERSLINE_LLM_AVALAI_PROVIDER`.
- Exact request cost is looked up via `/user/v1/transactions/lookup` using the `x-request-id`; the `avalapis.ir` domain is mirrored.
- In restricted networks a proxy may be required for AvalAI and for the cost lookup.
