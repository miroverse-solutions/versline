# Command reference

[Index](index.md) · **English** · [فارسی](../fa/commands.md)

Global options (`-v`, `--env-file`, `--extra-body`, `--version`) go **before** the command; see [Configuration](configuration.md#global-cli-options). Run `versline <command> --help` for the authoritative list.

**Common LLM options** (available on most commands, override the configured values): `--model`, `--provider` (Google, OpenAI, OpenRouter, AvalAI, OpenAICompatible), `--api-key`, `--api-endpoint`, `--proxy`, `--extra-body`.
**Prompt notes** (most commands): `--note TEXT` appends an instruction to the prompt; `--note-file FILE` does the same from a `.md`/`.txt` file.

## Setup commands

| Command | Description |
| :--- | :--- |
| `versline init` | Interactive first-time setup; writes the per-user `config.env` |
| `versline config [--show] [--path]` | Show saved settings (secrets masked) or just the file path |
| `versline update` | Update to the latest GitHub release |

## `transcribe`

```sh
versline transcribe FILE_OR_URL [OPTIONS]
```

Audio/video is split with ffmpeg into overlapping chunks (default 900 s, 180 s overlap), each chunk is transcribed by the LLM with context from earlier chunks, then merged. URLs (`http(s)://`) are downloaded to `temp/downloads` first. Progress is cached in `work_dir/<name>/progress.json`, so interrupted runs resume. A cost report is printed at the end.

| Option | Description | Default |
| :--- | :--- | :--- |
| `-o, --output PATH` | Output file | `output/<name>.md` (`.json` with `--json`) |
| `--chunk-size N`, `--overlap N` | Chunk length / overlap in seconds | `900` / `180` |
| `--prompt-file FILE` | Custom system prompt | built-in Persian prompt |
| `-j, --json` | Structured JSON output | off |
| `-f, --force` | Ignore the cache | off |
| `--skip-blocked` | Skip chunks blocked by the provider (leaves a `[⚠️ chunk N/M skipped: ...]` placeholder) instead of aborting | off |
| `--timestamped` | Also produce time-aligned segments. Tries the native STT endpoint (`verbose_json`) and falls back to chunk-based timestamping. Writes a JSON result plus the full text in a sibling `.md`. | off |
| `--timestamp-model` | STT model | `gpt-4o-mini-transcribe` |
| `--chunk-minutes N` | Minutes per chunk for chunk-based phases | config |
| `--native-timestamps-only` | Fail instead of falling back to chunk-based timestamps | off |
| `--reuse-transcript` | Skip transcription, reuse the cached transcript, redo only timestamping (`--force` then resets only the timestamp caches) | off |
| `--timestamp-provider/-api-key/-api-endpoint/-proxy/-language/-timeout` | STT connection overrides (default to LLM settings; language `fa`) | |

Plus the common LLM and prompt-note options.

## `translate`

```sh
versline translate FILE [-l LANGUAGE] [-o BASE_PATH] [-f]
```

`-l/--lang` default `Persian`. `-o` is a base path: **both** a `.md` and a Markdown-stripped `.txt` are written. `-f` ignores the cache. Plus the common options.

## `summarize`

```sh
versline summarize FILE [OPTIONS]
```

| Option | Description | Default |
| :--- | :--- | :--- |
| `-m, --mode` | `outline`, `detailed`, `slides` | `detailed` |
| `-c, --compression 1-100` | Target length as % of the original | LLM decides |
| `-l, --output-lang` | Language of the summary; `auto` keeps the source language | `auto` |
| `--preserve-terms / --no-preserve-terms` | Put the original term in parentheses when output language differs | on |
| `-d, --didactic` | Two-phase pedagogical restructuring (teaching blueprint, then reordered output; uses prompt caching) | off |
| `-o, --output` | Output `.md` | `output/...` |

Input can be any file supported by the document processor (Markdown, text, PDF, DOCX, PPTX, ...).

## `qude`

Generate questions and export them.

```sh
versline qude INPUT_PATH [OPTIONS]    # file or directory
```

| Option | Description | Default |
| :--- | :--- | :--- |
| `-o, --output` | Output directory | `output` |
| `-p, --provider` | `openai`, `avalai`, `gemini`, `openrouter`, `custom` | config |
| `-m, --model`, `-k, --api-key`, `-b, --base-url`, `--proxy`, `--extra-body` | Provider settings | |
| `-t, --type` | `mcq` or `open` | `mcq` |
| `-l, --lang` | Language code | `en` |
| `-c, --count` | Questions per chunk/slide | as many as possible |
| `--formats` | `csv`, `anki`, `html`, `all` (comma-separated) | `all` |
| `--style FILE` | Custom CSS for Anki/HTML | |
| `--prompt FILE` | Custom prompt | |
| `--slides-per-batch / --pages-per-batch / --words-per-batch` | Batch sizes for PPTX / PDF,DOCX / Markdown,text | `5` / `5` / `2000` |
| `--answer-length` | For `open`: word count (`200`), `short`/`medium`/`long`, or `mixed` | |
| `-f, --force` / `--no-cache` / `-r, --regenerate` / `--debug` | Ignore cache / disable cache / rebuild outputs from cache only / debug | |
| `--note`, `--note-file` | Extra instructions | |

## `qualcode`

Qualitative coding of an interview/text file.

```sh
versline qualcode INPUT_PATH [OPTIONS]
```

| Option | Description | Default |
| :--- | :--- | :--- |
| `-m, --method` (repeatable) | `thematic`, `grounded`, `content`, `framework`, `colaizzi` | `thematic` |
| `--format` (repeatable) | `json`, `markdown`, `csv`, `segments-csv`, `detailed-csv` | json, markdown |
| `--code TEXT` (repeatable), `--codebook FILE` | Seed codes / codebook (`.txt .md .csv .json`) | |
| `--central-concepts FILE` | Central concepts file | |
| `--code-mode` | `guided` or `strict` | `guided` |
| `--analysis-language` | `auto`, `fa`, `en` | `auto` |
| `--words-per-batch` | Word budget per batch | `1200` |
| `--citation / --no-citation` | Include evidence quotes | off |
| `--csv-fill-quotes-from-segments / --no-...` | Fill empty CSV quotes from segment text | on |
| `--excel / --no-excel` | Also write `.xlsx` next to each CSV | on |
| `--fail-on-parse-error` | Fail if any batch JSON cannot be parsed | off |
| `-o`, `-f`, `-p/--provider`, `--model`, `--api-key`, `--api-endpoint`, `--proxy`, `--extra-body`, `--note`, `--note-file` | As elsewhere | `-o output` |

## `research`

Staged academic writing, currently the **findings** section (chapter 4) with the `thematic-colaizzi` method profile.

1. `--stage outline` produces the chapter outline.
2. You review/edit the outline.
3. `--stage full` writes the final text. It is **blocked** unless you pass both `--approved-outline-file` and `--approve-outline`.

| Option | Description | Default |
| :--- | :--- | :--- |
| `-i, --input-json FILE` | Study metadata/materials (template below) | |
| `-s, --stage` | `outline` or `full` | `outline` |
| `--section`, `-m, --method` | Section key / method profile | `findings` / `thematic-colaizzi` |
| `-l, --output-lang` | `auto` keeps source language | `auto` |
| `--approved-outline-file`, `--approve-outline` | Required for `full` | |
| `--demographics-file`, `--themes-table-file`, `--central-concepts-file` | Material files (csv/xlsx/md/txt/docx/pdf) | |
| `--coded-segments-file` (repeatable), `--coded-segments-dir` | Analysis exports (codes, MAXQDA, theme matrices) | |
| `--interview-file` (repeatable), `--interviews-dir` | Raw interview transcripts only | |
| `--writing-guide-file` | Required chapter structure/style | |
| `--sample-output-file` | Style exemplar | |
| `--revision-file` | Correction brief for a re-run | |
| `--revision-history-file` | Cumulative revision history JSON | auto sidecar `<outline_stem>.revision-history.json` |
| `-o, --output` | Output `.md` | `output/<stem>_<section>_<stage>.md` |

Plus the common LLM and prompt-note options. Notes: the profile writes descriptive chapter-4 text only (no discussion/conclusion); missing data becomes `[NEEDS DATA: ...]` placeholders; quotes and frequencies must come from supplied materials. All revision briefs accumulate in the history file and are re-applied in later runs. `.docx` inputs work through MarkItDown.

```json
{
  "study": {
    "title": "Thesis title", "domain": "Psychology",
    "section_goal": "Chapter 4 findings", "method": "thematic-colaizzi",
    "research_questions": ["Question 1", "Question 2"]
  },
  "materials": {
    "demographics_table": "optional inline table",
    "themes_table": "optional", "central_concepts": "optional", "coded_segments": "optional",
    "interviews": [{ "name": "interview_01.md", "content": "optional inline text" }]
  }
}
```

```sh
versline research -i study.json --stage outline --demographics-file demo.xlsx \
  --coded-segments-dir ./coded --writing-guide-file guide.md -o output/ch4_outline.md
versline research -i study.json --stage full --approved-outline-file output/ch4_outline_approved.md \
  --approve-outline --revision-file revisions.md -o output/ch4_full.md
```

## `slides`

Generate an HTML/CSS/TypeScript slide deck from a Markdown file.

| Option | Description | Default |
| :--- | :--- | :--- |
| `-o, --output` | Output directory | `output` |
| `--prompt-file`, `--font-file`, `--font-family` | Custom prompt / local font (`.ttf .otf .woff .woff2`) / CSS family | `Vazirmatn` (bundled) |
| `--build`, `--single-file`, `--install-deps / --no-install-deps` | Build with Vite (needs Node/npm); one-file output; install npm deps first | off, off, on |
| `--npm-registry URL` | Registry for `--build` | `VERSLINE_SLIDES_NPM_REGISTRY` |
| `--include-all-content` / `--verbatim-text` | Don't omit content / use exact source text only | off |
| `--no-scroll / --allow-scroll` | Fit all content without scrolling | no-scroll |
| `--uniform-size / --no-uniform-size`, `--slide-size` | Equal slide size; `small` 720×480, `medium` 960×640, `large` 1280×800 | on, `medium` |
| `--chunk-size N` | Generate incrementally from chunks of ~N characters (0 = whole file) | `0` |
| `--impress` | Impress.js 3D deck (standalone HTML) | off |
| `--revealjs` | Reveal.js deck | off |

Plus the common LLM and prompt-note options.

## `telegram`

`telegram login`, `telegram logout`, `telegram archive CHANNEL`. Fully documented in [Telegram channel archive](telegram.md).

## Not available

`download` exists in the source (`commands/download.py`) but is **not registered** in the CLI. To download a URL, pass it directly to `versline transcribe`.
