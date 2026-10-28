# Versline
**Advanced Toolkit for Transcription, Translation, and Media Processing**

## نصب (برای کاربران)

**ویندوز (روش پیشنهادی)** — PowerShell را باز کنید و این یک خط را اجرا کنید. این روش نسخه‌ی Self-contained را از GitHub می‌گیرد و به پایتون، uv یا دسترسی به PyPI نیاز ندارد (حدود ۱۵۰ مگابایت دانلود):

```powershell
irm https://raw.githubusercontent.com/miroverse-solutions/versline/main/install.ps1 | iex
```

**مک / لینوکس:**

```sh
curl -LsSf https://raw.githubusercontent.com/miroverse-solutions/versline/main/install.sh | sh
```

سپس ترمینال را ببندید، یک ترمینال **جدید** باز کنید و اجرا کنید:

```sh
versline init              # انتخاب سرویس و ذخیره‌ی کلید API (فقط یک بار)
versline transcribe فایل.mp3
```

- به‌روزرسانی: `versline update`
- نمایش نسخه: `versline --version`
- تنظیمات ذخیره‌شده: `versline config`
- حذف (ویندوز): پوشه‌ی `%LOCALAPPDATA%\Versline` را پاک کنید و همان را از PATH کاربر حذف کنید
- حذف (مک / لینوکس): `uv tool uninstall versline`

ffmpeg به‌صورت خودکار تأمین می‌شود. خروجی‌ها در پوشه‌ی `output` کنار محل اجرا ذخیره می‌شوند. برای نمایش درست متن فارسی، فایل‌های خروجی را در یک ویرایشگر باز کنید (ترمینال ویندوز حروف فارسی را درست نمایش نمی‌دهد).

## 🚀 Installation

### 📦 Install (end users)
No Python or git needed: the installer sets up everything, including ffmpeg.

**Windows** (PowerShell) — recommended. Downloads a self-contained build (Python and all dependencies bundled) from the latest GitHub release into `%LOCALAPPDATA%\Versline` and adds it to your user PATH. It needs neither uv nor PyPI access, so it also works on restricted or slow networks:

```powershell
irm https://raw.githubusercontent.com/miroverse-solutions/versline/main/install.ps1 | iex
```

**macOS / Linux:**

```sh
curl -LsSf https://raw.githubusercontent.com/miroverse-solutions/versline/main/install.sh | sh
```

Then open a **new** terminal and run:

```sh
versline init      # choose a provider and save your API key (once)
versline --help
```

Update with `versline update`. Uninstall on Windows by deleting `%LOCALAPPDATA%\Versline` and removing it from your user PATH; on macOS/Linux use `uv tool uninstall versline`.

### 🧩 Install from source
To install the current checkout into your own Python environment:

```bash
pip install .
```

### 🛠️ Development Setup
To set up the environment for development:

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/miroverse-solutions/versline.git
    cd versline
    ```

2.  **Create a virtual environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

3.  **Install in editable mode:**
    ```bash
    pip install -e .
    ```

### 🏗️ Build
To build the distribution packages (wheel and source):

1.  **Install build tools:**
    ```bash
    pip install build
    ```

2.  **Generate artifacts:**
    ```bash
    python -m build --no-isolation
    ```
    The output files (`.whl` and `.tar.gz`) will be created in the `dist/` directory.

### 📥 Install from Binary
After building, you can install the package directly from the generated wheel:

```bash
pip install dist/versline-*.whl
```

### 🐚 Autocompletion
Enable tab completion for your shell (Bash, Zsh, Fish, PowerShell):

```bash
versline --install-completion
```
*Note: Restart your shell after installation.*

## ⚙️ Configuration

You can configure Versline using any of the following methods (in order of priority):

1.  **CLI Arguments**: Pass directly to commands (e.g., `--api-key`, `--proxy`).
2.  **Environment Variables**: Export variables in your shell.
3.  **`.env` File**: Create a `.env` file in your working directory.

You can also load a custom env file for any CLI command:

```bash
versline --env-file /path/to/.env transcribe audio.mp3
```

Or set a global fallback once (applies automatically when `--env-file` is not provided):

```bash
export VERSLINE_ENV_FILE=/path/to/.env
```

### Configuration Precedence Matrix

| Source | When applied | Overrides existing process env? | Priority |
| :--- | :--- | :--- | :--- |
| CLI arguments (e.g. `--api-key`) | At command execution | Yes (runtime settings override) | Highest |
| `--env-file /path/to/.env` | Global CLI option before subcommand runs | Yes | High |
| Process environment variables (`VERSLINE_*`) | Always (OS/shell exported env) | N/A | Medium |
| Local `.env` (pydantic `env_file='.env'`) | During settings construction | No (does not override existing env) | Low |
| `VERSLINE_ENV_FILE=/path/to/.env` fallback | During bootstrap/reload when `--env-file` is not provided | No | Low (custom fallback) |

For library mode, if you need a guaranteed override from a specific file, use:

```python
from versline import reload_settings

reload_settings("/path/to/.env")
```

### `.env` File Example
Run `cp .env.example .env` to start, or create one manually:

```dotenv
# Versline Configuration Template
# Copy this file to .env and fill in your values

# --- LLM configuration ---
# Options: Google, OpenAI, OpenRouter, AvalAI, OpenAICompatible
VERSLINE_LLM_PROVIDER=Google
VERSLINE_LLM_API_KEY=your_api_key_here
VERSLINE_LLM_MODEL=gemini-2.0-flash
# Optional: Proxy for API requests
VERSLINE_LLM_PROXY=
# Optional: Custom API Endpoint (Required for Custom/OpenAICompatible provider)
VERSLINE_LLM_API_ENDPOINT=
# Optional: AvalAI upstream provider hint (e.g. google/openai/anthropic)
# Useful when model id alone is ambiguous for AvalAI routing.
VERSLINE_LLM_AVALAI_PROVIDER=

# --- Transcription / Timestamps ---
# Model used for timestamp annotation (STT /audio/transcriptions endpoint preferred)
VERSLINE_TRANSCRIPTION_TIMESTAMP_MODEL=gpt-4o-mini-transcribe
# Chunk duration in minutes for chunk-based timestamp fallback
VERSLINE_TRANSCRIPTION_TIMESTAMP_CHUNK_MINUTES=3
# Timestamp (STT) connection. Any empty value falls back to the matching VERSLINE_LLM_* setting.
# Options: OpenAI, AvalAI, OpenRouter, OpenAICompatible
VERSLINE_TRANSCRIPTION_TIMESTAMP_PROVIDER=
VERSLINE_TRANSCRIPTION_TIMESTAMP_API_KEY=
# Base URL without /audio/transcriptions (required for OpenAICompatible)
VERSLINE_TRANSCRIPTION_TIMESTAMP_API_ENDPOINT=
VERSLINE_TRANSCRIPTION_TIMESTAMP_PROXY=
# Language code sent to the timestamp endpoint (e.g. fa, en). Leave empty for auto-detect.
VERSLINE_TRANSCRIPTION_TIMESTAMP_LANGUAGE=fa
VERSLINE_TRANSCRIPTION_TIMESTAMP_TIMEOUT_SECONDS=120

# --- Media configuration ---
# Full path to ffmpeg/ffprobe binaries if not in system PATH
VERSLINE_FFMPEG_FFMPEG_PATH=
VERSLINE_FFMPEG_FFPROBE_PATH=

# --- General System ---
VERSLINE_OUTPUT_DIRECTORY=output
VERSLINE_TEMP_DIRECTORY=temp

# --- Telegram channel archive ---
# Get api_id / api_hash at https://my.telegram.org (API development tools)
VERSLINE_TELEGRAM_API_ID=
VERSLINE_TELEGRAM_API_HASH=
# Optional: socks5://host:port or http://host:port (falls back to VERSLINE_LLM_PROXY)
VERSLINE_TELEGRAM_PROXY=
# Optional: custom Telethon session file path
VERSLINE_TELEGRAM_SESSION_PATH=

# --- Resource Limits ---
# Maximum RAM (virtual address space) in MB. 0 = unlimited.
VERSLINE_RESOURCE_MAX_RAM_MB=0
# Maximum CPU cores. 0 = use all available cores.
VERSLINE_RESOURCE_MAX_CPU_CORES=0
# Maximum GPU VRAM fraction per device (0.0 = unlimited, e.g. 0.8 = 80%).
# Requires PyTorch with CUDA support.
VERSLINE_RESOURCE_MAX_GPU_VRAM_FRACTION=0.0
# Soft watchdog trigger percent for RAM cap (50..100). Default 85.
# Example: 95 means SIGTERM only near the hard cap.
VERSLINE_RESOURCE_RAM_SOFT_TRIGGER_PCT=85
# Run RSS watchdog even when cgroup hard limit is active. Default false.
VERSLINE_RESOURCE_RUN_WATCHDOG_WITH_CGROUP=false
```

### AvalAI Notes

- For `VERSLINE_LLM_PROVIDER=AvalAI` with Gemini model IDs (for example `gemini-3-flash-preview`), Versline auto-sends provider hint `google` to AvalAI. You can override explicitly with `VERSLINE_LLM_AVALAI_PROVIDER`.
- Exact AvalAI cost lookup uses the User API endpoint (`/user/v1/transactions/lookup`) and tracked `x-request-id` values from API responses.
- **Domain mirroring**: if `VERSLINE_LLM_API_ENDPOINT` is set to an `avalapis.ir` URL, the cost-lookup endpoint is automatically derived from that same domain (e.g. `https://api.avalapis.ir/user/v1/transactions/lookup`). No extra configuration is needed; the canonical `api.avalai.ir` endpoint is used when no custom endpoint is set.
- In restricted networks, set `VERSLINE_LLM_PROXY` so cost lookup can reach AvalAI.
- Cost lookup uses the same `VERSLINE_LLM_API_KEY` (there is no separate key variable for User API in Versline config).


## ⚡ Resource Limits

Versline can apply OS-level resource limits at startup to prevent the process from consuming too much RAM, CPU, or GPU VRAM. This is useful when running large transcription or media workloads on shared machines.

### Configuration

Set any combination of the three env vars in your `.env` file:

```dotenv
# Limit process to ~4 GB of addressable memory
VERSLINE_RESOURCE_MAX_RAM_MB=4096

# Use at most 4 CPU cores
VERSLINE_RESOURCE_MAX_CPU_CORES=4

# Use at most 70% of each GPU's VRAM (requires PyTorch + CUDA)
VERSLINE_RESOURCE_MAX_GPU_VRAM_FRACTION=0.7
```

All three default to `0` / `0.0` which means **unlimited** — no limit is applied unless explicitly set.

### How each limit works

| Limit | Mechanism | Platform |
| :--- | :--- | :--- |
| `MAX_RAM_MB` | **Primary:** writes to cgroup v2 `memory.max` (kernel-enforced, fires on allocation). **Fallback:** RSS watchdog thread polls `/proc/self/status` every 0.5 s and sends `SIGTERM` at `VERSLINE_RESOURCE_RAM_SOFT_TRIGGER_PCT` (default 85 %). | Linux only |
| `MAX_CPU_CORES` | `os.sched_setaffinity(0, {0..N-1})` — pins process to first N cores | Linux / most POSIX |
| `MAX_GPU_VRAM_FRACTION` | `torch.cuda.set_per_process_memory_fraction(f, device)` | PyTorch + CUDA only |

> **RAM note:** The primary mechanism writes the limit to the process's own **cgroup v2 `memory.max`** file. This is enforced synchronously by the kernel on every allocation, so even a sudden spike during model loading is caught immediately — unlike a polling watchdog. If the cgroup file is not writable (e.g. in non-systemd or container environments), a fallback RSS watchdog thread is started instead.
> 
> The watchdog trigger can be tuned with `VERSLINE_RESOURCE_RAM_SOFT_TRIGGER_PCT` (range `50..100`, default `85`).
> Example: set `95` to reduce early terminations for model init spikes while still retaining a safety margin.
> 
> When cgroup hard limit is active, watchdog is disabled by default to avoid premature soft-kill during init spikes. Set `VERSLINE_RESOURCE_RUN_WATCHDOG_WITH_CGROUP=true` to enable both layers.

> **GPU note:** This limit only affects local model inference (sentence-transformers, FastEmbed with CUDA, etc.). API-managed providers (OpenAI, Cohere, etc.) are unaffected.

### Library usage

```python
from versline.core.resources import apply_resource_limits

apply_resource_limits(
    max_ram_mb=4096,       # 4 GB RAM cap
    max_cpu_cores=4,       # pin to 4 cores
    max_gpu_vram_fraction=0.7,  # 70% VRAM per GPU
)
```


## 📖 CLI Reference

Run `versline --help` or `versline [COMMAND] --help` for interactive help.

### 🎙️ `transcribe`
Convert audio or video files to text. Downloads URLs automatically if provided.

**Usage:**
```bash
versline transcribe [OPTIONS] FILE_PATH
```

**Arguments:**
- `FILE_PATH`: Path to the local audio/video file OR a direct download URL. [Required]

**Options:**
| Option | Short | Description | Default |
| :--- | :--- | :--- | :--- |
| `--output` | `-o` | Output file path. Defaults to `[filename]_transcription.md`. | `None` |
| `--model` | | LLM Model name (overrides config). | Config |
| `--provider` | | Service provider (`Google`, `OpenAI`, `OpenRouter`, `AvalAI`, `OpenAICompatible`). | Config |
| `--api-key` | | API Key for the selected provider. | Config |
| `--api-endpoint` | | Custom API Endpoint URL (for `OpenAICompatible`). | Config |
| `--proxy` | | HTTP/HTTPS Proxy URL (e.g., `http://127.0.0.1:10809`). | Config |
| `--chunk-size` | | Length of audio chunks in seconds. | `900` (15 min) |
| `--overlap` | | Overlap between chunks in seconds to preserve context. | `180` (3 min) |
| `--prompt-file` | | Path to a custom system prompt file (markdown). | `None` |
| `--json` | `-j` | Output in JSON format (schema-based editor/diarization). | `False` |
| `--force` | `-f` | Force re-transcription (ignore cache/progress). | `False` |
| `--skip-blocked` | | Skip chunks the provider blocks for content-policy reasons (e.g. Gemini `PROHIBITED_CONTENT`) instead of aborting. A `[⚠️ chunk N/M skipped: ...]` placeholder is left in the output, and the chunk is marked done in the progress cache. | `False` |
| `--note` | | Additional instruction appended to the prompt (inline string). | `None` |
| `--note-file` | | Path to a `.md` or `.txt` file whose content is appended to the prompt. | `None` |
| `--timestamped` | | Enable timestamp-aligned segments (dual strategy: native API → chunk-based). | `False` |
| `--timestamp-model` | | Model for timestamp annotation (`gpt-4o-mini-transcribe`, `whisper-1`, etc.). | `gpt-4o-mini-transcribe` |
| `--chunk-minutes` | | Chunk duration in minutes for chunk-based timestamp fallback. | `3` |
| `--native-timestamps-only` | | Use only the native STT API for timestamps; fail instead of falling back to chunk-based. | `False` |
| `--timestamp-provider` | | STT provider (`OpenAI`, `AvalAI`, `OpenRouter`, `OpenAICompatible`). | LLM settings |
| `--timestamp-api-key` | | API key for the STT endpoint. | LLM API key |
| `--timestamp-api-endpoint` | | STT base URL (without `/audio/transcriptions`). | Provider / LLM endpoint |
| `--timestamp-proxy` | | Proxy URL for STT requests. | LLM proxy |
| `--timestamp-language` | | Language code sent to the timestamp endpoint (e.g. `fa`, `en`). | `fa` |
| `--timestamp-timeout` | | HTTP timeout in seconds for STT requests. | `120` |

With `--timestamped`, the result is saved as JSON (`text` + `segments`) and the full text is also saved next to it as a `.md` file.

AvalAI-specific env options (applies to all commands that use LLM settings):
- `VERSLINE_LLM_AVALAI_PROVIDER`: Upstream provider hint for AvalAI routing (for example `google`, `openai`, `anthropic`).
- `VERSLINE_LLM_PROXY`: Proxy used for model calls and AvalAI cost lookup in restricted networks.
- `VERSLINE_LLM_EXTRA_BODY`: Optional JSON object merged into every OpenAI-compatible chat request body (same as the `--extra-body` flag), e.g. `{"reasoning": {"max_tokens": 1500}}`. Not applied to the native Gemini provider.

---

### 📝 `translate`
Translate text files into another language using LLMs.

**Usage:**
```bash
versline translate [OPTIONS] FILE_PATH
```

**Arguments:**
- `FILE_PATH`: Path to the text, markdown, or subtitle file. [Required]

**Options:**
| Option | Short | Description | Default |
| :--- | :--- | :--- | :--- |
| `--lang` | `-l` | Target language name (e.g. "Persian", "French"). | `"Persian"` |
| `--output` | `-o` | Output file path. | `[name]_[lang].[ext]` |
| `--model` | | LLM Model name. | Config |
| `--provider` | | Service provider. | Config |
| `--api-key` | | API Key. | Config |
| `--api-endpoint` | | Custom API Endpoint. | Config |
| `--proxy` | | Proxy URL. | Config |
| `--force` | `-f` | Force re-translation (ignore cache). | `False` |
| `--note` | | Additional instruction appended to the prompt (inline string). | `None` |
| `--note-file` | | Path to a `.md` or `.txt` file whose content is appended to the prompt. | `None` |

---

### 📄 `summarize`
Summarize any document in one of three modes using LLMs. Non-markdown files (DOCX, PDF, PPTX, etc.) are automatically converted to markdown before processing. The document is split at heading boundaries to avoid breaking semantic meaning.

**Usage:**
```bash
versline summarize [OPTIONS] FILE_PATH
```

**Arguments:**
- `FILE_PATH`: Path to the input file (Markdown, TXT, DOCX, PDF, PPTX, …). [Required]

**Options:**
| Option | Short | Description | Default |
| :--- | :--- | :--- | :--- |
| `--mode` | `-m` | Summarization mode: `outline`, `detailed`, or `slides`. | `"detailed"` |
| `--compression` | `-c` | Target output length as a percentage of the original (1–100). `10` = very brief; `50` = moderate; `90` = near-complete. Omit to let the LLM decide. | `None` (LLM decides) |
| `--output-lang` | `-l` | Language to write the summary in (`auto` = same as source). Example: `Persian`, `English`. | `"auto"` |
| `--preserve-terms / --no-preserve-terms` | | When outputting in a different language, include the original-language term in parentheses after each specialised technical term. | `True` |
| `--didactic / --no-didactic` | `-d` | Enable two-phase pedagogical restructuring (see below). | `False` |
| `--output` | `-o` | Output `.md` file path. | `[name]_summary_[mode].md` |
| `--model` | | LLM Model name. | Config |
| `--provider` | | Service provider. | Config |
| `--api-key` | | API Key. | Config |
| `--api-endpoint` | | Custom API Endpoint. | Config |
| `--proxy` | | Proxy URL. | Config |
| `--note` | | Additional instruction appended to the prompt (inline string). | `None` |
| `--note-file` | | Path to a `.md` or `.txt` file whose content is appended to the prompt. | `None` |

**Modes:**

| Mode | Description |
| :--- | :--- |
| `outline` | Hierarchical detailed outline (فهرست تفصیلی) — section/subsection tree with key bullet points |
| `detailed` | Detailed study-ready summary (خلاصه تفصیلی) — flowing prose preserving all important concepts |
| `slides` | Full slide outline for presentation (اوت‌لاین اسلاید) — section headers + per-slide bullet points |

> **Note on `--output-lang`:** The LLM generates the summary *directly* in the target language — there is no separate translation step. This produces more natural output and avoids the semantic loss of a translate-after-summarize pipeline.

> **Note on `--preserve-terms`:** Enabled by default when `--output-lang` differs from the source. The LLM is instructed to write each specialised term followed by the source-language original in parentheses, e.g. *هوش مصنوعی (artificial intelligence)*. Use `--no-preserve-terms` to suppress this.

> **Note on `--didactic`:** Activates a **two-phase pedagogical pipeline** regardless of the selected mode.
> - *Phase 1 (Analysis)*: The full document is sent to the LLM which produces a **teaching blueprint** — concept dependency map, recommended teaching order, sections that need more explanation, and natural concept groupings.
> - *Phase 2 (Generation)*: The full document is sent again together with the blueprint and the mode-specific prompt. The LLM is free to **reorder, expand, or group** content across section boundaries to maximise comprehension.
> - **Prompt caching**: The document tokens from Phase 1 are cached automatically (Google Gemini explicit context cache; OpenAI-compatible providers via stable system-message prefix). Phase 2 reuses those cached tokens, significantly reducing the cost for large documents.

**Examples:**
```bash
# Detailed summary in the same language as the source (default)
versline summarize lecture.md

# Very brief summary (~20% of original length)
versline summarize lecture.md --compression 20

# Near-complete notes (~80% of original length)
versline summarize lecture.md --compression 80 --mode detailed

# Hierarchical outline
versline summarize chapter.pdf --mode outline

# Summary generated directly in Persian (no translation step)
versline summarize paper.md --output-lang Persian

# Slide outline in English, keeping technical terms from the original Farsi source
versline summarize presentation.md --mode slides --output-lang English --preserve-terms

# Suppress parenthetical original terms
versline summarize notes.md --output-lang French --no-preserve-terms

# Didactic mode: reorder + expand for teaching (two-phase, with prompt caching)
versline summarize textbook.md --didactic

# Didactic + cross-language + term preservation in one command
versline summarize lecture.md --didactic --output-lang English --preserve-terms

# Very brief Persian outline of an English paper
versline summarize paper.md --mode outline --output-lang Persian --compression 15

# Slide deck blueprint with custom output path
versline summarize report.docx --mode slides --output report_slides.md

# Append an inline instruction to the prompt
versline summarize lecture.md --note "Focus on practical applications and real-world examples."

# Load a longer instruction from a file
versline summarize thesis.md --note-file my-instructions.md
```

---

### 🧠 `qude`
Generate Flashcards (Anki) or Multiple Choice Questions (MCQ) from documents.

**Usage:**
```bash
versline qude [OPTIONS] INPUT_PATH
```

**Arguments:**
- `INPUT_PATH`: Path to a file (PDF, PPT/PPTX, DOCX, MD) or directory. [Required]

**Options:**
| Option | Short | Description | Default |
| :--- | :--- | :--- | :--- |
| `--type` | `-t` | Output type: `mcq` (JSON/CSV) or `open` (Descriptive/Flashcards). | `"mcq"` |
| `--output` | `-o` | Output directory for results. | `"output"` |
| `--count` | `-c` | Number of questions to generate per chunk. Default: Max possible. | `None` |
| `--formats` | | Output formats: `csv`, `anki`, `html`, or `all`. | `"all"` |
| `--style` | | Path to custom CSS file for Anki/HTML styling. | `None` |
| `--prompt` | | Path to a custom prompt file to override default system prompt. | `None` |
| `--slides-per-batch` | | Number of slides per batch (PPTX; legacy PPT is converted directly). | `5` |
| `--pages-per-batch` | | Number of pages per batch (PDF/DOCX). | `5` |
| `--words-per-batch` | | Number of words per batch (Text/MD). | `2000` |
| `--lang` | `-l` | Language for the questions. | `"en"` |
| `--provider` | `-p` | AI Provider (`openai`, `avalai`, `gemini`, `custom`, etc.). | Config |
| `--model` | `-m` | AI Model name. | Config |
| `--api-key` | `-k` | API Key. | Config |
| `--base-url` | `-b` | Base URL for custom providers. | Config |
| `--proxy` | | Proxy URL. | Config |
| `--force` | `-f` | Force regeneration (ignore cache). | `False` |
| `--no-cache` | | Disable caching entirely. | `False` |
| `--regenerate` | `-r` | Regenerate output files from existing cache (no AI calls). | `False` |
| `--debug` | | Enable debug logging. | `False` |
| `--note` | | Additional instruction appended to the prompt (inline string). | `None` |
| `--note-file` | | Path to a `.md` or `.txt` file whose content is appended to the prompt. | `None` |
| `--answer-length` | | Target answer length for descriptive (`open`) questions. Accepts a word count (e.g. `200`), a preset (`short`, `medium`, `long`), or `mixed` for varied lengths. Ignored for `mcq`. | `None` |

---

### 🔎 `qualcode`
Run qualitative coding on Markdown/Text files with multiple qualitative research methods.

**Usage:**
```bash
versline qualcode [OPTIONS] INPUT_PATH
```

**Arguments:**
- `INPUT_PATH`: Path to Markdown/Text file. [Required]

**Options:**
| Option | Short | Description | Default |
| :--- | :--- | :--- | :--- |
| `--method` | `-m` | Repeatable method: `thematic`, `grounded`, `content`, `framework`, `colaizzi`. | `thematic` |
| `--format` | | Repeatable output format: `json`, `markdown`, `csv`, `segments-csv`, `detailed-csv`. | `json, markdown` |
| `--code` | | Repeatable seed code for the codebook. | `[]` |
| `--codebook` | | Path to codebook file (`.txt/.md/.csv/.json`). | `None` |
| `--central-concepts` | | Path to central concepts file (`.md/.markdown/.txt`) used to guide and update the conceptual map. | `None` |
| `--code-mode` | | `guided` (use codebook + allow new codes) or `strict` (only codebook). | `guided` |
| `--analysis-language` | | Language for analytic fields: `auto`, `fa`, `en`. | `auto` |
| `--fail-on-parse-error` | | Fail command if any batch JSON parse fails. | `False` |
| `--csv-fill-quotes-from-segments / --no-csv-fill-quotes-from-segments` | | Fill CSV quote column from segment text when model returns empty quotes. | `True` |
| `--excel / --no-excel` | | Export `.xlsx` alongside every generated CSV output. | `True` |
| `--citation / --no-citation` | | Include grounded quotes in coded output. | `False` |
| `--words-per-batch` | | Word budget per analysis batch. | `1200` |
| `--output` | `-o` | Output directory. | `output` |
| `--provider` | `-p` | AI provider. | Config |
| `--model` | | AI model. | Config |
| `--api-key` | | API key. | Config |
| `--api-endpoint` | | Custom API endpoint. | Config |
| `--proxy` | | Proxy URL. | Config |
| `--force` | `-f` | Ignore progress cache and rerun. | `False` |
| `--note` | | Additional instruction appended to the prompt (inline string). | `None` |
| `--note-file` | | Path to a `.md` or `.txt` file whose content is appended to the prompt. | `None` |

**Codebook Templates:**
- JSON template: `samples/qualcode/codebook.sample.json`
- TXT template: `samples/qualcode/codebook.sample.txt`

**Examples:**
```bash
# Strict: only codebook codes
versline qualcode interview.md --codebook samples/qualcode/codebook.sample.json --code-mode strict

# Guided: codebook codes + new codes when needed
versline qualcode interview.md --codebook samples/qualcode/codebook.sample.txt --code-mode guided

# Guided coding with central concepts baseline and updated central concepts output
versline qualcode interview.md --central-concepts central-concepts-example.md --method thematic --method grounded
```

---

### 🧾 `research`
Write research sections with a **staged academic pipeline**:

1. Generate an outline for the selected section/method.
2. Review and approve the outline.
3. Generate the full submission-ready text from the approved outline.

Current implementation scope:
- Section: `findings` (chapter 4)
- Method profile: `thematic-colaizzi`

The architecture is registry-based in code, so additional section/method profiles can be added later without changing the CLI shape.

**Usage:**
```bash
versline research [OPTIONS]
```

**Primary input option:**
- `--input-json` / `-i`: Path to a research input JSON file with study metadata/materials. [Optional]

**Options:**
| Option | Short | Description | Default |
| :--- | :--- | :--- | :--- |
| `--stage` | `-s` | Pipeline stage: `outline` or `full`. | `outline` |
| `--section` | | Research section key. | `findings` |
| `--method` | `-m` | Method profile key. (`thematic-colaizzi` currently supported; `colaizzi` alias accepted) | `thematic-colaizzi` |
| `--output-lang` | `-l` | Output language (`auto` keeps source language). | `auto` |
| `--approved-outline-file` | | Approved outline file (`.md/.txt/.docx/...` extractable) required for `--stage full`. | `None` |
| `--approve-outline` | | Explicit confirmation flag required for `--stage full`. | `False` |
| `--demographics-file` | | Demographics material file (`csv/xlsx/md/txt/docx/pdf/...`). | `None` |
| `--themes-table-file` | | Themes/sub-themes table file (`csv/xlsx/md/txt/docx/pdf/...`). | `None` |
| `--central-concepts-file` | | Themes/central concepts material file. | `None` |
| `--coded-segments-file` | | Coded segments/codes file (repeatable; for example MAXQDA analysis export). | `[]` |
| `--coded-segments-dir` | | Directory containing coded segments/code files. | `None` |
| `--writing-guide-file` | | A writing-instructions file (`md/docx/txt/...`) that defines required chapter structure/style. | `None` |
| `--sample-output-file` | | A sample target output file (`md/docx/txt/...`) used as style/flow exemplar. | `None` |
| `--interviews-dir` | | Directory of interview files to ingest as evidence context. | `None` |
| `--interview-file` | | Repeatable single interview file option. | `[]` |
| `--output` | `-o` | Output markdown path. | `output/[stem]_[section]_[stage].md` |
| `--model` | | LLM model override. | Config |
| `--provider` | | LLM provider override. | Config |
| `--api-key` | | API key override. | Config |
| `--api-endpoint` | | API endpoint override. | Config |
| `--proxy` | | Proxy override. | Config |
| `--note` | | Inline additional instruction appended to prompt. | `None` |
| `--note-file` | | File-based additional instruction (`.md/.txt`). | `None` |
| `--revision-file` | | File-based correction brief for reruns (`.md/.txt`). | `None` |
| `--revision-history-file` | | Path to cumulative revision history JSON. If omitted, auto sidecar is used. | Auto |

#### Stage Contract (Important)

- `--stage outline` produces only the chapter structure plan.
- `--stage full` is blocked unless both of these are provided:
    - `--approved-outline-file`
    - `--approve-outline`

This enforces the human-in-the-loop approval checkpoint before long-form generation.

#### Writing Guide and Sample Output Inputs

You can provide two extra inputs for precise academic control:

- `--writing-guide-file`: includes mandatory formatting/structure instructions (for example your exact section template and narrative rules).
- `--sample-output-file`: includes a target style exemplar. The model mirrors rhetorical flow, paragraph rhythm, and table presentation style without copying unrelated content.
- `--revision-file`: adds one revision brief for the current run.
- All revision briefs are accumulated into a history file and injected together in later runs, so full-text generation keeps older reviewer requirements too.
- Default history sidecar path is: `[outline_stem].revision-history.json` (same folder as outline output). You can override it with `--revision-history-file`.

These are injected into research context as:
- `materials.writing_guide`
- `materials.sample_output`
- cumulative `revision history` appended to the research prompt (when provided)

#### Coded Segments vs Interviews

- Use `--coded-segments-file` / `--coded-segments-dir` for analysis artifacts (codes, coded segments, theme matrices, MAXQDA exports).
- Use `--interview-file` / `--interviews-dir` only for raw/full interview transcripts.
- If your files are analysis outputs (not raw transcripts), pass them as coded segments.

#### Research Input JSON Template

Use this as a starting point for `INPUT_JSON`:

```json
{
    "study": {
        "title": "Thesis title",
        "domain": "Psychology",
        "section_goal": "Chapter 4 findings",
        "method": "thematic-colaizzi",
        "research_questions": [
            "Question 1",
            "Question 2"
        ]
    },
    "materials": {
        "demographics_table": "Optional inline demographics table",
        "themes_table": "Optional inline themes/sub-themes table",
        "central_concepts": "Optional inline themes/sub-themes",
        "coded_segments": "Optional inline coded evidence",
        "interviews": [
            {
                "name": "interview_01.md",
                "content": "Optional inline transcript content"
            }
        ]
    }
}
```

You may keep `materials` minimal in JSON and provide most artifacts through CLI file options.

> **Prerequisite note:** Research files with `.docx` content are converted through MarkItDown. This project now installs `markitdown[docx]` so DOCX-based research inputs work out of the box.

#### Suggested Workflow

```bash
# 1) Generate outline
versline research \
    --input-json ./research_input.json \
    --stage outline \
    --section findings \
    --method thematic-colaizzi \
    --demographics-file ./data/demographics.xlsx \
    --themes-table-file ./data/themes-table.xlsx \
    --central-concepts-file ./data/central-concepts.md \
    --coded-segments-dir ./data/coded-segments \
    --writing-guide-file ./templates/ch4-guide.md \
    --sample-output-file ./templates/ch4-sample.docx \
    --output ./output/ch4_outline.md

# 2) After your manual approval, generate full text
versline research \
    --input-json ./research_input.json \
    --stage full \
    --section findings \
    --method thematic-colaizzi \
    --approved-outline-file ./output/ch4_outline_approved.md \
    --approve-outline \
    --writing-guide-file ./templates/ch4-guide.md \
    --sample-output-file ./templates/ch4-sample.docx \
    --revision-file ./templates/ch4-revisions.md \
    --output ./output/ch4_full.md
```

#### Notes and Limits

- The findings profile is constrained to **descriptive chapter-4 writing** (no chapter-5 interpretation/conclusion).
- If required data is missing, the generator inserts explicit placeholders like `[NEEDS DATA: ...]`.
- If a reviewer asks for "leave blank for now", put that instruction in `--revision-file`; the command will re-run with the same cached base prompts and only the revision brief changes.
- If you iterate on the same outline path, previous revision briefs are remembered automatically and reused during `--stage full`.
- Quotes/frequencies should come from provided materials; fabricated evidence is explicitly disallowed by prompts.
- Revision briefs are ideal for iterative changes like:
  - leaving the demographics section blank until the table arrives,
  - enforcing code + direct-quote style for every theme,
  - splitting a single theme matrix into theme-by-theme narrative blocks.

---

### 🎬 `slides`
Generate luxurious, spatially navigable HTML/CSS/TypeScript slide decks from Markdown.

**Usage:**
```bash
versline slides [OPTIONS] INPUT_PATH
```

**Arguments:**
- `INPUT_PATH`: Path to Markdown file. [Required]

**Options:**
| Option | Short | Description | Default |
| :--- | :--- | :--- | :--- |
| `--output` | `-o` | Output directory. | `output` |
| `--prompt-file` | | Path to custom slides prompt file. | `None` |
| `--font-file` | | Local font file path (`.ttf/.otf/.woff/.woff2`). | `src/versline/resources/assets/Vazirmatn[wght].ttf` |
| `--font-family` | | Font family name used in generated CSS. | `Vazirmatn` |
| `--provider` | | LLM provider. | Config |
| `--model` | | LLM model. | Config |
| `--api-key` | | API key. | Config |
| `--api-endpoint` | | Custom API endpoint. | Config |
| `--proxy` | | Proxy URL. | Config |
| `--build` | | Build generated deck with Vite (`dist/`). | `False` |
| `--single-file` | | Enable `vite-plugin-singlefile` during build. | `False` |
| `--install-deps / --no-install-deps` | | Install npm deps before build. | `True` |
| `--include-all-content / --no-include-all-content` | | Instruct the LLM to include every piece of content from the input without omissions. | `False` |
| `--verbatim-text / --no-verbatim-text` | | Instruct the LLM to use only exact verbatim text from the input; no rephrasing. | `False` |
| `--no-scroll / --allow-scroll` | | Design each slide so all content fits without scrolling. | `--no-scroll` |
| `--uniform-size / --no-uniform-size` | | Make all slides the same fixed size. | `--uniform-size` |
| `--slide-size` | | Slide size preset: `small` (720×480), `medium` (960×640), `large` (1280×800). | `medium` |
| `--chunk-size` | | Split markdown into chunks of ~N characters for incremental generation. `0` = no chunking. | `0` |
| `--impress / --no-impress` | | Generate slides using **Impress.js** for cinematic 3D spatial navigation with zoom, rotation, and depth transitions. Produces a standalone HTML deck; `impress.js` is bundled automatically. | `--no-impress` |
| `--revealjs / --no-revealjs` | | Generate slides using **Reveal.js** for a polished, professional presentation with fragment animations, vertical slides, and speaker notes. Assets are bundled automatically. | `--no-revealjs` |
| `--note` | | Additional instruction appended to the prompt (inline string). | `None` |
| `--note-file` | | Path to a `.md` or `.txt` file whose content is appended to the prompt. | `None` |
| `--npm-registry` | | Custom npm registry URL used during `--build` (e.g. `https://registry.npmmirror.com`). Can also be set via `VERSLINE_SLIDES_NPM_REGISTRY`. | `None` |

**Examples:**
```bash
# Generate source files only (index.html, style.css, main.ts)
versline slides ./docs/talk.md

# Generate and build with Vite
versline slides ./docs/talk.md --build

# Generate + Vite single-file output
versline slides ./docs/talk.md --build --single-file

# Use a custom local font file (no CDN font links)
versline slides ./docs/talk.md --font-file ./fonts/IRANSansXVF.woff2 --font-family IRANSansX

# Use custom prompt template
versline slides ./docs/talk.md --prompt-file ./my-slides-prompt.md

# Append an inline instruction to the prompt
versline slides ./docs/talk.md --note "Use a dark theme with blue accent colors."

# Load instruction from a file
versline slides ./docs/talk.md --note-file ./slides-note.md

# Generate an Impress.js deck with cinematic 3D spatial navigation
versline slides ./docs/talk.md --impress

# Impress.js deck with a custom font and a user instruction
versline slides ./docs/talk.md --impress --font-file ./fonts/IRANSansXVF.woff2 --font-family IRANSansX --note "Use a dark background with gold accents."

# Generate a Reveal.js deck with polished slide transitions and fragments
versline slides ./docs/talk.md --revealjs

# Reveal.js deck with a custom font and single-file build output
versline slides ./docs/talk.md --revealjs --font-file ./fonts/IRANSansXVF.woff2 --font-family IRANSansX --build --single-file

# Force-include every piece of content without omissions
versline slides ./docs/talk.md --include-all-content

# Use verbatim text from the source, no rephrasing
versline slides ./docs/talk.md --verbatim-text

# Change slide size and allow scrolling within slides
versline slides ./docs/talk.md --slide-size large --allow-scroll

# Process a large file incrementally in ~4000-character chunks
versline slides ./docs/long-talk.md --chunk-size 4000

# Build using a custom npm registry (useful in air-gapped or regional networks)
versline slides ./docs/talk.md --build --npm-registry https://registry.npmmirror.com
```

`slides` always copies the selected font file into the deck directory and injects local `@font-face` rules. Any external CDN links generated by the model are stripped from HTML/CSS output.

#### Impress.js mode (`--impress`)

When `--impress` is used, `versline slides` switches to a completely different generation pipeline:

- An **Impress.js v1.1.0-specific prompt** is sent to the LLM, instructing it to produce a spatially arranged 3D deck with `data-x`, `data-y`, `data-z`, `data-rel-x`, `data-rel-y`, `data-rotate`, `data-rotate-x`, `data-rotate-y`, `data-scale`, and `.substep` animated bullet reveals on each `<div class="step slide">` element.
- Navigation (arrow keys, space, swipe, overview with `O`, help with `?`) is handled entirely by `impress.js` — no custom TypeScript runtime is generated.
- `impress.js` (v1.1.0 full bundle with all plugins) is bundled in-package at `src/versline/resources/assets/impress.js`. If absent, it is downloaded once from unpkg and cached. Subsequent runs use the cached copy.
- The output deck is a fully standalone directory: `index.html`, `style.css`, `main.ts` (placeholder), `impress.js`, and the font file. Open `index.html` directly in a browser — no build step required.
- `--build` works with impress mode: Vite bundles `impress.js` alongside `index.html` and `style.css` into `dist/`.

#### Reveal.js mode (`--revealjs`)

When `--revealjs` is used, `versline slides` switches to the Reveal.js generation pipeline:

- A **Reveal.js v5.1.0-specific prompt** is sent to the LLM, instructing it to produce a deck with section-based slides, fragment animations (`.fragment`), vertical slide groups (`sub_slides`), speaker notes, and background options.
- Layout and navigation are handled entirely by Reveal.js — left/right for horizontal slides, up/down for vertical slide groups. No custom layout TypeScript is generated.
- Three asset files are bundled in-package at `src/versline/resources/assets/`: `reveal.js`, `reveal.css`, and `reveal-theme.css` (black theme). If absent, they are downloaded once from jsDelivr CDN and cached. Subsequent runs use the cached copies.
- The output deck directory contains: `index.html`, `style.css`, `main.ts` (DOM builder + `Reveal.initialize()`), `reveal.js`, `reveal.css`, `reveal-theme.css`, and the font file. Open `index.html` directly in a browser — no build step required.
- `--build` works with Reveal.js mode: Vite bundles all assets into `dist/`. `--single-file` inlines all three Reveal.js asset files.
- `--impress` and `--revealjs` are mutually exclusive; if both are given, `--revealjs` takes precedence.

> **Pre-caching assets manually:** If you have already downloaded the Reveal.js files, place them here to avoid the automatic CDN download:
> ```
> src/versline/resources/assets/reveal.js        ← reveal.js dist/reveal.js
> src/versline/resources/assets/reveal.css       ← reveal.js dist/reveal.css
> src/versline/resources/assets/reveal-theme.css ← reveal.js dist/theme/black.css
> ```

---

### ⬇️ `download`
Download a file from a URL using HTTP/Stream.

For `qualcode --format csv`, generated CSV columns are:
- `code`
- `quotes`
- `segment_ids`
- `method`

For `qualcode --format segments-csv`, generated CSV columns are:
- `source_file`
- `segment_id`
- `start_line`
- `end_line`
- `word_count`
- `text`

For `qualcode --format detailed-csv`, generated CSV columns are:
- `code`
- `method`
- `segment_ids`
- `segment_1`, `segment_2`, ... (each related segment in a separate column)

For all CSV outputs (`csv`, `segments-csv`, `detailed-csv`), a matching Excel file (`.xlsx`) is generated by default.

When `--central-concepts` is provided, `qualcode` also generates:
- an updated central concepts Markdown file: `<input_stem>_central_concepts_<timestamp>.md`
- a `central_concepts` section in JSON output containing both `original` and `updated` structures plus `update_memo`

**Usage:**
```bash
versline download [OPTIONS] URL
```
| Option | Short | Description |
| :--- | :--- | :--- |
| `--output` | `-o` | Output file path or directory. |


## 📣 Telegram Channel Archive

Archive a Telegram channel into an Obsidian vault: **one Markdown note per post** (caption, transcript of audio/video, optional summary and *taqrir*, detailed frontmatter) plus a channel index note. Works for audio/video channels, text-only channels and mixed ones.

### Quick start

```sh
# 1. Log in once (see "Choosing how to connect" below; skip with --web for public channels)
versline telegram login

# 2. See what a date range contains (nothing is downloaded or written)
versline telegram archive @channel --since 2026-03-01 --until 2026-03-31 --dry-run

# 3. Archive it into your vault
versline telegram archive @channel --since 2026-03-01 --until 2026-03-31 -o ~/Vault/Telegram/channel
```

LLM settings (provider, key, model, proxy, `extra_body`) come from the usual `VERSLINE_LLM_*` variables / `.env` / `--env-file`, or from the command-line overrides listed below.

### Choosing how to connect

| | Logged-in account (default) | Web preview (`--web`) |
| :--- | :--- | :--- |
| Needs `api_id` / `api_hash` and `telegram login` | Yes | **No** |
| Channels | Public, private, and ones you joined by invite link | **Public only** (`@name`, `t.me/name`) |
| Audio files, documents, very large videos | Downloaded and transcribed | **Not downloadable** (no URL on the preview) – the post still gets a note with its caption/metadata and a `skipped_media` entry |
| Voice messages, round videos, small videos | Yes | Yes |
| Speed | Fast | Slower (polite delay between requests); date ranges are located by binary search, so old ranges are still quick to reach |

**Logged-in account.**
1. Create an app at <https://my.telegram.org> → *API development tools* to get `api_id` / `api_hash`.
2. Either put them in your env file (`VERSLINE_TELEGRAM_API_ID`, `VERSLINE_TELEGRAM_API_HASH`) or let `versline telegram login` ask for them and save them to your per-user config.
3. Run `versline telegram login`: it asks for your phone number, the code Telegram sends you and, if enabled, your 2FA password. Setting the variables alone is **not** enough – the account login is a separate step. A session file is then stored in your user config directory (override with `VERSLINE_TELEGRAM_SESSION_PATH`).
4. `versline telegram logout` ends the session and deletes the file.

> The session file grants access to your Telegram account. Keep it private and never commit it.

**Web preview.** Add `--web` to read `https://t.me/s/<channel>` instead. No account, no login. Private channels, invite links and `t.me/c/...` links are rejected with a clear message; use the logged-in mode for those. A channel that doesn't exist or has the web preview disabled gives a "not found" error.

**Behind a filter?** Use `--proxy` on `login` (or `--telegram-proxy` on `archive`), or set `VERSLINE_TELEGRAM_PROXY`. Supported: `socks5://host:port`, `socks5://user:pass@host:port`, `http://host:port`. For Telegram the order is `--telegram-proxy` → `VERSLINE_TELEGRAM_PROXY` → `--proxy`/`VERSLINE_LLM_PROXY`. (`--proxy` on `archive` is the proxy for the LLM provider.)

### `telegram login`

```bash
versline telegram login [--proxy URL]
```

### `telegram logout`

```bash
versline telegram logout
```

### `telegram archive`

```bash
versline telegram archive [OPTIONS] CHANNEL
```

`CHANNEL` can be `@name`, `name`, `https://t.me/name`, `https://t.me/c/<id>` (private) or an invite link of a channel you already joined (the last two need the logged-in mode).

**Selecting posts**

| Option | Description | Default |
| :--- | :--- | :--- |
| `--since` | Only posts from this date. `YYYY-MM-DD[ HH:MM]`, Gregorian or Shamsi (`1404-07-01`). | Beginning of channel |
| `--until` | Only posts up to and including this date. A date without a time covers the whole day. | End of channel |
| `--limit` | Process at most N matching posts. | No limit |
| `--types` | Comma-separated post types: `audio`, `voice`, `video`, `video_note`, `photo`, `document`, `text`. See below. | All types |
| `--dry-run` | List the matching posts (id, date, type, duration, title) without downloading or writing anything. | `False` |

A post's type is the type of its **first** media item (an album starting with a photo is `photo`); a post without media is `text`. `--types voice,audio,video` keeps only spoken content; `--types text` keeps only text-only posts. Only audio, voice and video are transcribed; other types just get their caption and metadata.

**Output**

| Option | Short | Description | Default |
| :--- | :--- | :--- | :--- |
| `--output` | `-o` | Output folder. Point it at your Obsidian vault. | `output/<channel username>` (`VERSLINE_OUTPUT_DIRECTORY`) |
| `--keep-media` | | Save media under `attachments/` and embed it in the notes. | `False` |
| `--max-size` | | Skip media larger than this many MB (recorded in `skipped_media`). | No limit |
| `--no-transcribe` | | Only save captions/metadata; do not transcribe. | `False` |

**Extra sections (optional, LLM)**

| Option | Description |
| :--- | :--- |
| `--summary` | Add a **خلاصه** (summary) section at the top of each note. Built from the transcript, or from the caption for text posts. Skipped for content shorter than ~300 characters. |
| `--taqrir` | Add a **تقریر و صورت‌بندی** section after the transcript: the talk rewritten as a structured, formulated written exposition (issue, claims, arguments, objections, conclusion), faithful to the speaker. For text posts it is built from the caption (≥ ~300 characters) with a prompt suited to written text. |
| `--output-lang` | Language of the summary/taqrir (e.g. `English`). Default: same language as the content. |

Both use the model from `VERSLINE_LLM_*` / `--model` and their cost is included in the cost report printed at the end. The prompts live in `src/versline/resources/prompts/` (`channel_summary_prompt.md`, `channel_taqrir_prompt.md`, `channel_taqrir_text_prompt.md`); edit them to change the style. Each extra call costs tokens, so try `--limit 3` first on large channels.

**Resuming and redoing**

| Option | Short | Description |
| :--- | :--- | :--- |
| *(none)* | | Re-running skips posts already archived (manifest `.versline-channel.json` in the output folder). A failing post is reported, marked failed and retried next run without stopping the rest. Ctrl+C is safe: finished posts are kept. |
| `--force` | `-f` | Re-process archived posts **from scratch**, including transcription (the transcription cache is ignored). |
| `--reuse-transcripts` | | Re-process archived posts (captions, titles, tags, `--summary`, `--taqrir`, …) but **keep the transcript already stored in each note** – no download and no new transcription cost. Posts without a stored transcript are transcribed normally. If combined with `--force`, this option wins. Edits you made to a note's transcript are preserved; edits elsewhere in the note are overwritten. |

**LLM / transcription overrides** (same meaning as in `versline transcribe`)

| Option | Description |
| :--- | :--- |
| `--model`, `--provider`, `--api-key`, `--api-endpoint` | Provider settings (override config). |
| `--proxy` | Proxy for the LLM provider. |
| `--telegram-proxy` | Proxy for Telegram (defaults to `VERSLINE_TELEGRAM_PROXY`, then `--proxy`). |
| `--extra-body` | JSON merged into every OpenAI-compatible request body (also `VERSLINE_LLM_EXTRA_BODY`). Not applied to native Gemini. |
| `--note`, `--note-file` | Extra instruction appended to the transcription prompt. |
| `--chunk-size`, `--overlap` | Audio chunk length and overlap in seconds (`900` / `180`). |
| `--skip-blocked` | Skip chunks blocked by the provider instead of failing the post. |

### What gets written

```text
<out>/
├── <Channel title>.md                     # index: table of all archived posts
├── .versline-channel.json                 # manifest used for resuming
├── posts/
│   └── 2026-03-14 - 223 - <title>.md      # one note per post
└── attachments/                           # only with --keep-media
```

Each post note contains, in order: the frontmatter, a title (the first meaningful line of the caption, without hashtags, links or Markdown), **خلاصه** (`--summary`), **توضیحات** (the caption, with bold/italic/links preserved), **متن پیاده‌شده** (transcript; several media items become `### 1`, `### 2`, …), **تقریر و صورت‌بندی** (`--taqrir`), **پیوست‌ها** (`--keep-media`) and a link back to the original post.

Frontmatter: `title`, `source`, `channel`, `channel_title`, `post_id`, `url`, `date`, `date_shamsi`, `media_type`, `duration`, `file_name`, `views`, `forwards`, `forwarded_from`, `album_size`, `tags`, `aliases`, `archived_at`, and when applicable `transcribed`, `transcription_model`, `summary_model`, `taqrir_model`, `skipped_media`. Hashtags in the caption become `tags` (a zero-width non-joiner or space inside a hashtag is turned into `_`, e.g. `#حسن‌صباح` → `حسن_صباح`, because Obsidian rejects it otherwise); `telegram` is always added.

The transcript is cleaned of the model's chatter (an opening such as «بله، حتماً…» and a closing «[---پایان فایل صوتی---]» are removed).

### Recipes

```sh
# Audio channel: transcripts + summary + taqrir, media kept, into the vault
versline --env-file ~/.versline.env telegram archive @lectures --since 1404-07-01 \
  --summary --taqrir --keep-media -o ~/Vault/Telegram/lectures

# Text-only channel without any login: structured notes (+ summaries/taqrir of long posts)
versline telegram archive @news --web --types text --summary --taqrir

# Add summaries and taqrir to posts you already archived, without re-transcribing
versline telegram archive @lectures --since 1404-07-01 --summary --taqrir --reuse-transcripts \
  -o ~/Vault/Telegram/lectures

# Only spoken content, skip files above 200 MB, in English summaries
versline telegram archive @lectures --types audio,voice,video --max-size 200 --summary --output-lang English
```

### Environment variables

| Variable | Description |
| :--- | :--- |
| `VERSLINE_TELEGRAM_API_ID` | `api_id` from <https://my.telegram.org>. |
| `VERSLINE_TELEGRAM_API_HASH` | `api_hash` from <https://my.telegram.org>. |
| `VERSLINE_TELEGRAM_PROXY` | Proxy for Telegram (`socks5://…` / `http://…`); falls back to `VERSLINE_LLM_PROXY`. |
| `VERSLINE_TELEGRAM_SESSION_PATH` | Custom Telethon session file path (default: per-user config dir). |

### Troubleshooting

- **"Not logged in to Telegram"** – run `versline telegram login` (env variables alone don't log you in), or use `--web` for a public channel.
- **"api_id/api_hash are not set"** – put them in the env file passed with `--env-file`, or run `versline telegram login` to be asked for them.
- **Web mode says "not found or its web preview is disabled"** – the channel is private, doesn't exist, or its owner disabled the preview; use the logged-in mode.
- **Posts show `audio not downloadable` in `skipped_media`** – that is the web preview's limit; use the logged-in mode to transcribe audio files and large videos.
- **Nothing happens for a date range** – check it with `--dry-run`; dates are interpreted in local time and Shamsi years (< 1700) are converted automatically.
- **A note's title/tags look old after an update** – re-run the range with `--reuse-transcripts` (or `--force`).

## 🛠️ Features
- **Smart Context**: Uses previous chunks to identify speakers consistently.
- **Retry Mechanism**: Automatically retries failed API calls.
- **Rich UI**: Colorful progress bars and spinners.
- **Flexible**: Agnostic to LLM provider (Google, OpenAI, OpenRouter, AvalAI, Custom).
- **Markdown-to-Slides**: Generate immersive slide decks (`index.html`, `style.css`, `main.ts`) with optional Vite build and single-file export.
- **Telegram Archive**: Turn channels (audio, video or text) into Obsidian notes with transcripts, summaries and taqrir, with or without logging in (`--web`).
- **Proxy Support**: Full support for HTTP/HTTPS proxies.
- **Resource Limits**: Cap RAM, CPU cores, and GPU VRAM via env vars to prevent OOM crashes on shared machines.

## 📦 Python Library Usage

Versline is designed to be easily imported into your Python projects.

### Basic Setup
```python
from versline import AudioTranscriber, TextTranslator, MarkdownSlideDeckGenerator, download_file, settings, reload_settings

# Optional: load a specific env file in library mode
reload_settings("/path/to/.env")

# Or rely on fallback from environment variable:
# os.environ["VERSLINE_ENV_FILE"] = "/path/to/.env"
# reload_settings()

# Configure globally (or load from .env automatically)
settings.llm.provider = "AvalAI"
settings.llm.api_key = "YOUR_API_KEY"
settings.llm.model = "gpt-4o-mini"
# Optional AvalAI routing/cost settings
settings.llm.avalai_provider = "openai"  # e.g. google/openai/anthropic

# Optional proxy for API calls and cost lookup
settings.llm.proxy = "socks5://127.0.0.1:10808"
```

When using AvalAI with Gemini model IDs (for example `gemini-3-flash-preview`), Versline sends provider hint `google` automatically unless you set `settings.llm.avalai_provider` (or `VERSLINE_LLM_AVALAI_PROVIDER`) explicitly.

### Advanced Examples

**1. Transcribe with Custom Options:**
```python
transcriber = AudioTranscriber()

# Basic transcription
full_text = transcriber.process_file("interview.mp3")
print(full_text)

# Timestamp-aligned transcription (dual strategy)
# - First tries native segmentation via STT API (verbose_json + timestamps)
# - Falls back to chunk-based method if provider doesn't support timestamps
result = transcriber.process_file(
    "lecture.mp3",
    timestamped=True,                   # Enable timestamp mode
    timestamp_model="gpt-4o-mini-transcribe",  # STT model for timestamps
    chunk_minutes=3                     # Chunk size for fallback method
)
print(result["text"])                   # Full high-quality transcription
for seg in result["segments"]:          # Time-aligned segments
    m = int(seg["start"] // 60)
    s = int(seg["start"] % 60)
    print(f"{m}:{s:02d} — {seg['text'][:100]}")
```

**2. Translate Text:**
```python
translator = TextTranslator()
result = translator.process_file(
    "document.txt", 
    target_language="German"
)
```

**3. Summarize a Document:**
```python
from versline.services.summarizer import TextSummarizer

# Default: same language as source, detailed mode
summarizer = TextSummarizer(mode="detailed")
markdown_summary = summarizer.process_file("lecture.pdf")

# Generate a Persian summary of an English paper directly (no translation step)
summarizer = TextSummarizer(mode="detailed", output_lang="Persian", preserve_terms=True)
persian_summary = summarizer.process_file("paper.md")
# Technical terms appear as: شبکه عصبی (neural network)

# Didactic mode: two-phase pedagogical restructuring with prompt caching
# Phase 1 → teaching blueprint; Phase 2 → reordered/expanded output (cached tokens)
summarizer = TextSummarizer(mode="detailed", didactic=True)
didactic_summary = summarizer.process_file("textbook.md")

# Presentation slide outline in English with didactic restructuring
slide_summarizer = TextSummarizer(mode="slides", output_lang="English", didactic=True)
slide_outline = slide_summarizer.process_file("report.docx")
```

**4. Qualitative Coding in Library Mode:**
```python
from versline import QualitativeCoder, settings

settings.llm.provider = "AvalAI"
settings.llm.model = "gemini-3-flash-preview"
settings.llm.api_key = "YOUR_API_KEY"

coder = QualitativeCoder(
    output_dir="output",
    methods=["colaizzi"],
    output_formats=["json", "csv", "segments-csv"],
    code_mode="guided",
    analysis_language="fa",
    include_citation=True,
)

outputs = coder.process_file("interview.md")
print(outputs)  # generated files per format
print(coder.last_parse_failures)
```

**5. Markdown to Slide Deck (HTML/CSS/TypeScript):**
```python
from versline import MarkdownSlideDeckGenerator

generator = MarkdownSlideDeckGenerator()
result = generator.generate_from_markdown(
    input_path="talk.md",
    output_dir="output",
    build=True,
    single_file=True,
    install_deps=True,
)

print(result["deck_dir"])
print(result.get("dist_dir"))
```
