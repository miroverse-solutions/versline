# Python library and MCP server

[Index](index.md) · **English** · [فارسی](../fa/library.md)

## Library

```python
from versline import (AudioTranscriber, TextTranslator, QualitativeCoder,
                      MarkdownSlideDeckGenerator, download_file, settings, reload_settings)

reload_settings("/path/to/.env")          # optional: load a specific env file
settings.llm.provider = "AvalAI"
settings.llm.api_key = "YOUR_API_KEY"
settings.llm.model = "gpt-4o-mini"
settings.llm.proxy = "socks5://127.0.0.1:10808"   # optional
```

Exports are lazy, so `import versline` stays fast.

**Transcribe**

```python
transcriber = AudioTranscriber()
text = transcriber.process_file("interview.mp3")

result = transcriber.process_file("lecture.mp3", timestamped=True,
                                  timestamp_model="gpt-4o-mini-transcribe", chunk_minutes=3)
print(result["text"])
for seg in result["segments"]:
    print(int(seg["start"] // 60), seg["text"][:100])
```

**Translate**

```python
TextTranslator().process_file("document.txt", target_language="German")
```

**Summarize**

```python
from versline.services.summarizer import TextSummarizer
TextSummarizer(mode="detailed").process_file("lecture.pdf")
TextSummarizer(mode="detailed", output_lang="Persian", preserve_terms=True).process_file("paper.md")
TextSummarizer(mode="detailed", didactic=True).process_file("textbook.md")
TextSummarizer(mode="slides", output_lang="English").process_file("report.docx")
```

**Qualitative coding**

```python
coder = QualitativeCoder(output_dir="output", methods=["colaizzi"],
                         output_formats=["json", "csv", "segments-csv"],
                         code_mode="guided", analysis_language="fa", include_citation=True)
outputs = coder.process_file("interview.md")
print(outputs, coder.last_parse_failures)
```

**Slides**

```python
MarkdownSlideDeckGenerator().generate_from_markdown(
    input_path="talk.md", output_dir="output", build=True, single_file=True, install_deps=True)
```

**Resource limits** (never applied automatically)

```python
from versline.core.resources import apply_resource_limits
apply_resource_limits(max_ram_mb=4096, max_cpu_cores=4, max_gpu_vram_fraction=0.7)
```

## MCP server

`src/versline/mcp/server.py` is a FastMCP server (`python -m versline.mcp.server`) exposing tools that shell out to the CLI: `transcribe`, `translate`, `summarize`, `generate_questions`, `generate_slides`, `transcribe_text`, `translate_text`, `summarize_text`. The repository script `versline-mcp.sh` starts it using `venv/bin/python3` of a source checkout. It is not installed as a separate console script.

## Bridge protocol

`versline bridge` is a machine-readable front end for other programs. The [Versobs Obsidian plugin](obsidian.md) uses it, and it works for editors and scripts too. It runs the same code as the CLI commands (batching, resume, skip-if-done, exports), but speaks JSON.

```sh
versline bridge info --pretty                  # versions + every tool with its parameter JSON Schema
echo '{"params": {"inputs": ["lecture.pdf"], "output": "/notes/lecture_summary.md", "mode": "outline"}}' \
  | versline bridge run summarize.file
```

**Request.** One JSON line on stdin (or `--params` / `--params-file`): `{"params": {...}, "llm": {"provider", "model", "api_key", "api_endpoint", "proxy", "extra_body"}, "workdir": "..."}`. Only `params` is needed, and a bare params object also works. The `llm` values override the saved settings for this job; prefer passing the key as the `VERSLINE_LLM_API_KEY` environment variable. Caches and temporary files go to `--workdir`, which defaults to `~/.cache/versline/bridge` or `%LOCALAPPDATA%\versline\bridge`. Pass absolute paths.

**Events.** One JSON object per line on stdout. Nothing else is ever written there: stray prints become `log` events.

| `type` | Fields |
| :--- | :--- |
| `hello` | `versline`, `protocol` (currently 1), `tool` |
| `progress` | `current`, `total` (null = indeterminate), `label` |
| `log` | `level` (debug, info, success, warning, error), `message` |
| `prompt` | `id`, `message`, `secret`, `kind` (phone, code, password, api_id, api_hash, confirm, or null), `default`, `choices` |
| `artifact` | `path`, `kind` (note, folder, media, pdf, docx, ...), `exists`: a file the job created or changed |
| `cost` | `input_tokens`, `output_tokens`, `cached_tokens`, `usd`, `irt`, `error` |
| `result` | `data` (tool-specific, usually `outputs`), `artifacts`: last event of a successful run (exit 0) |
| `error` | `code` (unknown_tool, invalid_params, bad_input, failed, cancelled, exception, internal), `message`: last event of a failed run (exit 1, 2 for invalid requests, 130 when cancelled) |

**While it runs**, send `{"type": "answer", "id": "p1", "value": "..."}` to answer a prompt (a `null` value declines it) or `{"type": "cancel"}` to stop. Closing stdin while a prompt is pending cancels the job. Killing the process is also safe, because finished chunks are cached.

**Tool schemas** carry UI hints, so a client can render a form for any tool: `x-label`/`x-help` (`{"en", "fa"}`), `x-widget` (file, files, folder, textarea, secret, output-file, output-folder, date, tags), `x-accept` (extensions), `x-advanced`, `x-output` (default output pattern such as `{dir}/{stem}_summary_{mode}.md`) and `x-choices` (enum labels). Tools marked `hidden` are internal helpers (settings, Telegram login, updates) and don't belong in a generic tool list.

**Adding a tool:** in `src/versline/bridge/tools/`, define a `Params` model with `F(...)` fields, decorate a function with `@tool(...)`, and call the CLI command through `run_command(ctx, "versline.commands.x", "func", outputs=[...], **options)`. Import the module in `tools/__init__.py`. `tests/test_bridge.py` checks that every option passed exists on the command.
