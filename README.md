# Versline
**Advanced Toolkit for Transcription, Translation, and Media Processing**

## 🚀 Installation

### 📦 Local Installation (user)
To install Versline functionally on your machine:

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
versline --env-file /path/to/.env rag ask "main points" --collection my_docs
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

# --- RAG configuration ---
VERSLINE_RAG_VECTOR_BACKEND=qdrant
VERSLINE_RAG_COLLECTION_NAME=versline_docs
VERSLINE_RAG_VECTOR_SIZE= # optional fixed dimension (e.g. 1024, 1536); leave empty to infer from embedding model
VERSLINE_RAG_QDRANT_URL=http://localhost:6333
VERSLINE_RAG_QDRANT_API_KEY=
VERSLINE_RAG_EMBEDDING_MODEL=text-embedding-3-small
VERSLINE_RAG_EMBEDDING_PROVIDER=openai # openai, openrouter, avalai, openaicompatible, fastembed, sentence-transformers, flagembedding, optimum-intel
VERSLINE_RAG_EMBEDDING_API_KEY=
VERSLINE_RAG_EMBEDDING_API_ENDPOINT=
VERSLINE_RAG_EMBEDDING_TIMEOUT_SECONDS=60
VERSLINE_RAG_EMBEDDING_MODEL_PATH=
VERSLINE_RAG_EMBEDDING_CACHE_DIR=
VERSLINE_RAG_EMBEDDING_LOCAL_FILES_ONLY=false
VERSLINE_RAG_EMBEDDING_USE_FP16=true
VERSLINE_RAG_EMBEDDING_DEVICE=
VERSLINE_RAG_EMBEDDING_BATCH_SIZE=16
VERSLINE_RAG_EMBEDDING_INFERENCE_BACKEND=auto # auto, openvino
VERSLINE_RAG_OPENVINO_CACHE_DIR= # cache dir for compiled OpenVINO artifacts (CPU/GPU)
VERSLINE_RAG_EMBEDDING_ONNX_PROVIDERS= # e.g. OpenVINOExecutionProvider,CPUExecutionProvider
VERSLINE_RAG_SPARSE_EMBEDDING_PROXY=
VERSLINE_RAG_GENERATION_TIMEOUT_SECONDS=120
VERSLINE_RAG_QDRANT_TIMEOUT_SECONDS=20
VERSLINE_RAG_RERANK_TIMEOUT_SECONDS=60
VERSLINE_RAG_CHUNK_SIZE=1200
VERSLINE_RAG_CHUNK_OVERLAP=200
VERSLINE_RAG_PARENT_CHILD_ENABLED=false
VERSLINE_RAG_PARENT_CHUNK_SIZE=2400
VERSLINE_RAG_PARENT_CHUNK_OVERLAP=200
VERSLINE_RAG_PARENT_CHILD_FETCH_K=48
VERSLINE_RAG_INGESTION_BATCH_SIZE=32
VERSLINE_RAG_RETRIEVE_FETCH_K=24
VERSLINE_RAG_LOG_EVERY_BATCHES=1
VERSLINE_RAG_SPARSE_EMBEDDING_MODEL=prithivida/Splade_PP_en_v1
VERSLINE_RAG_SPARSE_EMBEDDING_PROVIDER=fastembed # fastembed, flagembedding
VERSLINE_RAG_SPARSE_EMBEDDING_MODEL_PATH=
VERSLINE_RAG_SPARSE_EMBEDDING_CACHE_DIR=
VERSLINE_RAG_SPARSE_EMBEDDING_LOCAL_FILES_ONLY=false
VERSLINE_RAG_SPARSE_EMBEDDING_USE_FP16=true
VERSLINE_RAG_SPARSE_EMBEDDING_DEVICE=
VERSLINE_RAG_SPARSE_EMBEDDING_BATCH_SIZE=16
VERSLINE_RAG_SPARSE_EMBEDDING_ONNX_PROVIDERS= # e.g. OpenVINOExecutionProvider,CPUExecutionProvider
VERSLINE_RAG_HYBRID_ENABLED=true
VERSLINE_RAG_HYBRID_DENSE_WEIGHT=0.7
VERSLINE_RAG_HYBRID_LEXICAL_WEIGHT=0.3
VERSLINE_RAG_RERANK_ENABLED=false
VERSLINE_RAG_RERANK_PROVIDER=cohere # cohere, jina, openai, openrouter, avalai, openaicompatible, local, fastembed, sentence-transformers, optimum-intel
VERSLINE_RAG_RERANK_MODEL=rerank-v3.5
VERSLINE_RAG_RERANK_API_KEY=
VERSLINE_RAG_RERANK_API_ENDPOINT=
VERSLINE_RAG_RERANK_MODEL_PATH=
VERSLINE_RAG_RERANK_CACHE_DIR=
VERSLINE_RAG_RERANK_LOCAL_FILES_ONLY=false
VERSLINE_RAG_RERANK_DEVICE=
VERSLINE_RAG_RERANK_BATCH_SIZE=16
VERSLINE_RAG_RERANK_INFERENCE_BACKEND=auto # auto, openvino
VERSLINE_RAG_RERANK_ONNX_PROVIDERS= # e.g. OpenVINOExecutionProvider,CPUExecutionProvider
VERSLINE_RAG_EMBEDDING_PROXY=
VERSLINE_RAG_GENERATION_PROXY=
VERSLINE_RAG_QDRANT_PROXY=
VERSLINE_RAG_RERANK_PROXY=
VERSLINE_RAG_RATE_LIMIT_EMBEDDING_RPM=0
VERSLINE_RAG_RATE_LIMIT_EMBEDDING_TPM=0
VERSLINE_RAG_RATE_LIMIT_GENERATION_RPM=0
VERSLINE_RAG_RATE_LIMIT_GENERATION_TPM=0
VERSLINE_RAG_RATE_LIMIT_QDRANT_RPM=0
VERSLINE_RAG_RATE_LIMIT_RERANK_RPM=0
VERSLINE_RAG_RATE_LIMIT_RERANK_TPM=0
VERSLINE_RAG_TOKEN_LIMIT_MODE=estimate_only
VERSLINE_RAG_MCP_ENABLED=false
VERSLINE_RAG_MCP_TRANSPORT=http
VERSLINE_RAG_MCP_SERVER_URL=
VERSLINE_RAG_MCP_SERVER_COMMAND=
VERSLINE_RAG_MCP_SERVER_ARGS=
VERSLINE_RAG_MCP_TOOL_NAME=retrieve_context
VERSLINE_RAG_MCP_TIMEOUT_SECONDS=30
VERSLINE_RAG_MCP_MAX_CONTEXT_CHARS=8000
VERSLINE_RAG_MCP_PROXY=
VERSLINE_RAG_WEB_SEARCH_ENABLED=false
VERSLINE_RAG_WEB_SEARCH_PROVIDER=duckduckgo # duckduckgo, tavily
VERSLINE_RAG_WEB_SEARCH_API_KEY=
VERSLINE_RAG_WEB_SEARCH_ENDPOINT=
VERSLINE_RAG_WEB_SEARCH_TIMEOUT_SECONDS=15
VERSLINE_RAG_WEB_SEARCH_TOP_K=3
VERSLINE_RAG_WEB_SEARCH_PROXY=
VERSLINE_RAG_WEB_SEARCH_MAX_CONTEXT_CHARS=6000
VERSLINE_RAG_RATE_LIMIT_WEB_SEARCH_RPM=0
VERSLINE_RAG_RETRY_MAX_RETRIES=4
VERSLINE_RAG_RETRY_BASE_DELAY_SECONDS=1.0
VERSLINE_RAG_RETRY_MAX_DELAY_SECONDS=12.0
VERSLINE_RAG_PREFLIGHT_ENABLED=true
VERSLINE_RAG_PREFLIGHT_NETWORK=true

# Preset: Sentence-Transformers (Dense, local/offline friendly)
# Use this when a dense model is not available in FastEmbed (e.g. many Qwen embedding IDs).
# VERSLINE_RAG_EMBEDDING_PROVIDER=sentence-transformers
# VERSLINE_RAG_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
# VERSLINE_RAG_EMBEDDING_MODEL_PATH=/absolute/path/to/Qwen3-Embedding-0.6B
# VERSLINE_RAG_EMBEDDING_LOCAL_FILES_ONLY=true
# VERSLINE_RAG_EMBEDDING_DEVICE=cpu
# VERSLINE_RAG_EMBEDDING_BATCH_SIZE=16

# Preset: optimum-intel (OVModelForFeatureExtraction, Intel CPU/iGPU)
# Best throughput on Intel hardware. Point MODEL_PATH to a pre-exported OpenVINO IR dir
# (contains openvino_model.xml) to skip the one-time export step.
# VERSLINE_RAG_EMBEDDING_PROVIDER=optimum-intel
# VERSLINE_RAG_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
# VERSLINE_RAG_EMBEDDING_MODEL_PATH=/absolute/path/to/Qwen3-Embedding-0.6B-OpenVINO
# VERSLINE_RAG_EMBEDDING_LOCAL_FILES_ONLY=true
# VERSLINE_RAG_EMBEDDING_DEVICE=CPU  # or GPU for Intel iGPU
# VERSLINE_RAG_EMBEDDING_BATCH_SIZE=16
# VERSLINE_RAG_OPENVINO_CACHE_DIR=/absolute/path/to/openvino_cache

# --- Media configuration ---
# Full path to ffmpeg/ffprobe binaries if not in system PATH
VERSLINE_FFMPEG_FFMPEG_PATH=
VERSLINE_FFMPEG_FFPROBE_PATH=

# --- General System ---
VERSLINE_OUTPUT_DIRECTORY=output
VERSLINE_TEMP_DIRECTORY=temp

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

Versline can apply OS-level resource limits at startup to prevent the process from consuming too much RAM, CPU, or GPU VRAM. This is useful when running large embedding or transcription workloads on shared machines.

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

> **RAM note:** The primary mechanism writes the limit to the process's own **cgroup v2 `memory.max`** file. This is enforced synchronously by the kernel on every allocation, so even a sudden spike during model export or OpenVINO conversion is caught immediately — unlike a polling watchdog. If the cgroup file is not writable (e.g. in non-systemd or container environments), a fallback RSS watchdog thread is started instead.
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
| `--note` | | Additional instruction appended to the prompt (inline string). | `None` |
| `--note-file` | | Path to a `.md` or `.txt` file whose content is appended to the prompt. | `None` |

AvalAI-specific env options (applies to all commands that use LLM settings):
- `VERSLINE_LLM_AVALAI_PROVIDER`: Upstream provider hint for AvalAI routing (for example `google`, `openai`, `anthropic`).
- `VERSLINE_LLM_PROXY`: Proxy used for model calls and AvalAI cost lookup in restricted networks.

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
- `INPUT_PATH`: Path to a file (PDF, PPTX, DOCX, MD) or directory. [Required]

**Options:**
| Option | Short | Description | Default |
| :--- | :--- | :--- | :--- |
| `--type` | `-t` | Output type: `mcq` (JSON/CSV) or `open` (Descriptive/Flashcards). | `"mcq"` |
| `--output` | `-o` | Output directory for results. | `"output"` |
| `--count` | `-c` | Number of questions to generate per chunk. Default: Max possible. | `None` |
| `--formats` | | Output formats: `csv`, `anki`, `html`, or `all`. | `"all"` |
| `--style` | | Path to custom CSS file for Anki/HTML styling. | `None` |
| `--prompt` | | Path to a custom prompt file to override default system prompt. | `None` |
| `--slides-per-batch` | | Number of slides per batch (PPTX). | `5` |
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
- JSON template: `examples/qualcode/codebook.sample.json`
- TXT template: `examples/qualcode/codebook.sample.txt`

**Examples:**
```bash
# Strict: only codebook codes
versline qualcode interview.md --codebook examples/qualcode/codebook.sample.json --code-mode strict

# Guided: codebook codes + new codes when needed
versline qualcode interview.md --codebook examples/qualcode/codebook.sample.txt --code-mode guided

# Guided coding with central concepts baseline and updated central concepts output
versline qualcode interview.md --central-concepts central-concepts-example.md --method thematic --method grounded
```

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

---

### 🧩 `rag`
Run modular RAG pipelines with preprocessing, ingestion, retrieval, and generation.

**Usage:**
```bash
versline rag [COMMAND] [OPTIONS]
```

**Commands:**
- `ingest`: ingest a file into vector store (currently Markdown/Text input)
- `ask`: retrieve context and generate answer from indexed content

**Examples:**
```bash
# Ingest markdown into Qdrant collection
versline rag ingest notes.md --collection my_docs --provider OpenAI --api-key $OPENAI_API_KEY

# Ask from collection
versline rag ask "خلاصه نکات اصلی چیست؟" --collection my_docs --top-k 5 --provider OpenAI --api-key $OPENAI_API_KEY

# Ingest a whole directory with resumable progress and per-service proxies
versline rag ingest ./docs --collection my_docs --resume --embedding-proxy http://127.0.0.1:2080 --qdrant-proxy ""

# Ask with hybrid retrieval + custom rate limits
versline rag ask "main points" --collection my_docs --hybrid --embedding-rpm 120 --generation-rpm 30 --qdrant-rpm 300

# Ingest + ask with hierarchical parent-child retrieval
versline rag ingest ./docs --collection my_docs --parent-child --parent-chunk-size 2400 --chunk-size 1200
versline rag ask "main points" --collection my_docs --parent-child --top-k 5

# Ask with mixed RPM + TPM limits
versline rag ask "main points" --collection my_docs --embedding-rpm 120 --embedding-tpm 80000 --generation-rpm 30 --generation-tpm 20000 --rerank --rerank-tpm 30000

# Ask with adaptive TPM correction (estimate + actual usage)
versline rag ask "main points" --collection my_docs --embedding-tpm 80000 --generation-tpm 20000 --token-limit-mode estimate_and_adjust

# Ask with MCP external context (HTTP mode)
versline rag ask "main points" --collection my_docs --mcp --mcp-transport http --mcp-server-url http://localhost:8080/mcp/context

# Ask with MCP external context (stdio mode)
versline rag ask "main points" --collection my_docs --mcp --mcp-transport stdio --mcp-server-command npx --mcp-server-args "@modelcontextprotocol/server-filesystem /home/mirza/projects/versline"

# Ask with web search context (DuckDuckGo, no API key)
versline rag ask "latest updates about qdrant hybrid search" --collection my_docs --web-search --web-search-provider duckduckgo --web-search-top-k 3

# Ask with Tavily web search context + per-service rate limit/proxy
versline rag ask "main points" --collection my_docs --web-search --web-search-provider tavily --web-search-api-key $TAVILY_API_KEY --web-search-rpm 60 --web-search-proxy http://127.0.0.1:2080

# Ask with dedicated rerank model
versline rag ask "main points" --collection my_docs --hybrid --rerank --rerank-provider cohere --rerank-model rerank-v3.5 --rerank-api-key $COHERE_API_KEY

# Ask with local rerank model (OpenAI-compatible endpoint, default: http://localhost:11434/v1)
versline rag ask "main points" --collection my_docs --hybrid --rerank --rerank-provider local --rerank-model bge-reranker-v2-m3 --rerank-api-endpoint http://localhost:11434/v1

# Ask with local-file rerank model (sentence-transformers CrossEncoder)
versline rag ask "main points" --collection my_docs --hybrid --rerank --rerank-provider local --rerank-model BAAI/bge-reranker-v2-m3 --rerank-model-path /models/bge-reranker-v2-m3 --rerank-local-files-only --rerank-device cpu

# Ask with OpenVINO backend for embedding + rerank
versline rag ask "main points" --collection my_docs --hybrid --embedding-provider sentence-transformers --embedding-model sentence-transformers/all-MiniLM-L6-v2 --embedding-backend openvino --rerank --rerank-provider local --rerank-model BAAI/bge-reranker-v2-m3 --rerank-backend openvino

# Ask with per-service timeouts + preflight tuned for restricted/offline network
versline rag ask "main points" --collection my_docs --embedding-timeout 90 --generation-timeout 180 --qdrant-timeout 30 --rerank-timeout 90 --preflight --no-preflight-network

# Ingest using FastEmbed sparse backend with local cache-only mode
versline rag ingest ./docs --collection my_docs --hybrid --sparse-provider fastembed --sparse-model prithivida/Splade_PP_en_v1 --sparse-cache-dir /models/fastembed --sparse-local-files-only

# Ask using FlagEmbedding sparse backend (e.g. BGE-M3 lexical) on CUDA
versline rag ask "main points" --collection my_docs --hybrid --sparse-provider flagembedding --sparse-model BAAI/bge-m3 --sparse-device cuda --sparse-use-fp16 --sparse-batch-size 8

# Ask with local/offline dense embeddings via FastEmbed
versline rag ask "main points" --collection my_docs --embedding-provider fastembed --embedding-model BAAI/bge-base-en-v1.5 --embedding-cache-dir /models/dense --embedding-local-files-only

# Ask with local dense embeddings via Sentence-Transformers
versline rag ask "main points" --collection my_docs --embedding-provider sentence-transformers --embedding-model sentence-transformers/all-MiniLM-L6-v2 --embedding-device cpu --embedding-batch-size 32

# Ask with Sentence-Transformers using a local Qwen embedding model path
versline rag ask "main points" --collection my_docs --embedding-provider sentence --embedding-model Qwen/Qwen3-Embedding-0.6B --embedding-model-path /models/Qwen3-Embedding-0.6B --embedding-local-files-only --embedding-device cpu

# Ask with FlagEmbedding dense backend (BGE-M3)
versline rag ask "main points" --collection my_docs --embedding-provider flagembedding --embedding-model BAAI/bge-m3 --embedding-device cuda --embedding-use-fp16

# Ask with optimum-intel backend (pre-exported OpenVINO IR on Intel CPU)
versline rag ask "main points" --collection my_docs --embedding-provider optimum-intel --embedding-model Qwen/Qwen3-Embedding-0.6B --embedding-model-path /models/Qwen3-Embedding-0.6B-OpenVINO --embedding-local-files-only --embedding-device CPU --embedding-batch-size 16

# Ask with optimum-intel backend on Intel iGPU (GPU device)
versline rag ask "main points" --collection my_docs --embedding-provider optimum-intel --embedding-model Qwen/Qwen3-Embedding-0.6B --embedding-model-path /models/Qwen3-Embedding-0.6B-OpenVINO --embedding-local-files-only --embedding-device GPU

# Ask with optimum-intel reranker (pre-exported OpenVINO IR cross-encoder on Intel CPU)
versline rag ask "main points" --collection my_docs --hybrid --rerank --rerank-provider optimum-intel --rerank-model BAAI/bge-reranker-v2-m3 --rerank-model-path /models/bge-reranker-v2-m3-OpenVINO --rerank-local-files-only --rerank-device CPU

# Ask with both optimum-intel embedding and reranker on Intel CPU
versline rag ask "main points" --collection my_docs --hybrid --embedding-provider optimum-intel --embedding-model Qwen/Qwen3-Embedding-0.6B --embedding-model-path /models/Qwen3-Embedding-0.6B-OpenVINO --embedding-local-files-only --embedding-device CPU --rerank --rerank-provider optimum-intel --rerank-model BAAI/bge-reranker-v2-m3 --rerank-model-path /models/bge-reranker-v2-m3-OpenVINO --rerank-local-files-only --rerank-device CPU
```

### RAG Operational Profiles

- **Direct (no proxy):** do not set `VERSLINE_RAG_*_PROXY` values (or pass empty values via CLI).
- **Per-service proxy:** set only the services you need, e.g. `VERSLINE_RAG_EMBEDDING_PROXY`, `VERSLINE_RAG_GENERATION_PROXY`, `VERSLINE_RAG_WEB_SEARCH_PROXY`, while keeping `VERSLINE_RAG_QDRANT_PROXY=` empty.
- **Offline dense mode:** set `VERSLINE_RAG_EMBEDDING_PROVIDER` to `fastembed` / `sentence-transformers` / `flagembedding` / `optimum-intel`, enable `VERSLINE_RAG_EMBEDDING_LOCAL_FILES_ONLY=true`, and set `VERSLINE_RAG_EMBEDDING_CACHE_DIR` or `VERSLINE_RAG_EMBEDDING_MODEL_PATH`.
- **Intel CPU/iGPU acceleration (optimum-intel):** set `VERSLINE_RAG_EMBEDDING_PROVIDER=optimum-intel` and point `VERSLINE_RAG_EMBEDDING_MODEL_PATH` to a pre-exported OpenVINO IR directory (contains `openvino_model.xml`). Set `VERSLINE_RAG_EMBEDDING_DEVICE=CPU` or `GPU` for iGPU. On first run with a plain HF model directory the model is exported automatically (requires network access once).
- **Offline sparse mode:** set `VERSLINE_RAG_SPARSE_EMBEDDING_LOCAL_FILES_ONLY=true` and point `VERSLINE_RAG_SPARSE_EMBEDDING_CACHE_DIR` or `VERSLINE_RAG_SPARSE_EMBEDDING_MODEL_PATH` to local artifacts.
- **Hierarchical parent-child retrieval:** set `VERSLINE_RAG_PARENT_CHILD_ENABLED=true` to index parent+child chunks and retrieve child matches expanded to parent context for generation.
- **Local rerank mode:** set `VERSLINE_RAG_RERANK_PROVIDER=local`. If `VERSLINE_RAG_RERANK_MODEL_PATH` (or `VERSLINE_RAG_RERANK_LOCAL_FILES_ONLY`) is set, Versline loads a local sentence-transformers CrossEncoder model from files; otherwise it uses an OpenAI-compatible endpoint (default `http://localhost:11434/v1`, placeholder API key `local` when empty).
- **Intel CPU/iGPU reranker acceleration (optimum-intel):** set `VERSLINE_RAG_RERANK_PROVIDER=optimum-intel` and point `VERSLINE_RAG_RERANK_MODEL_PATH` to a pre-exported OpenVINO IR directory (contains `openvino_model.xml`). Uses `OVModelForSequenceClassification` directly (no inference-backend flag required). Set `VERSLINE_RAG_RERANK_DEVICE=CPU` or `GPU` for iGPU. On first run with a plain HF checkpoint the model is exported automatically (requires network access once).
- **OpenVINO acceleration:** set `VERSLINE_RAG_EMBEDDING_INFERENCE_BACKEND=openvino` and/or `VERSLINE_RAG_RERANK_INFERENCE_BACKEND=openvino` to enable OpenVINO where the selected provider supports it (for local sentence-transformers embedding/rerank paths). The selected provider is preserved and is not auto-switched.
- **Preflight in locked environments:** keep `VERSLINE_RAG_PREFLIGHT_ENABLED=true` and set `VERSLINE_RAG_PREFLIGHT_NETWORK=false` to validate config without outbound endpoint checks.

### OpenVINO Troubleshooting

- Install minimum runtime dependencies in your environment:
    ```bash
    pip install -U openvino 'optimum[openvino]' sentence-transformers numpy
    ```
- Use a local sentence-transformers path for predictable OpenVINO runs:
    - `VERSLINE_RAG_EMBEDDING_PROVIDER=sentence-transformers`
    - `VERSLINE_RAG_EMBEDDING_INFERENCE_BACKEND=openvino`
    - `VERSLINE_RAG_RERANK_PROVIDER=local` or `sentence-transformers`
    - `VERSLINE_RAG_RERANK_INFERENCE_BACKEND=openvino`
    - `VERSLINE_RAG_OPENVINO_CACHE_DIR=/absolute/path/to/openvino_cache`
- If you see backend or export errors, clear model cache and re-download/export once:
    - remove the model cache directory used by `VERSLINE_RAG_EMBEDDING_CACHE_DIR` / `VERSLINE_RAG_RERANK_CACHE_DIR`
    - rerun with network access one time, then switch back to local/offline mode
- OpenVINO is a local inference runtime. It applies to sentence-transformers/local rerank paths and can also be used with FastEmbed (embedding and rerank) when ONNX providers are set to `OpenVINOExecutionProvider,CPUExecutionProvider`.
- The `optimum-intel` provider uses `OVModelForFeatureExtraction` directly with mean-pooling. It operates independently of `embedding_inference_backend` and is best suited for Intel CPU/iGPU scenarios on pre-exported OpenVINO IR models. To export a model from HuggingFace:
    ```bash
    optimum-cli export openvino --model Qwen/Qwen3-Embedding-0.6B --task feature-extraction /models/Qwen3-Embedding-0.6B-OpenVINO
    ```
- To use `optimum-intel` for **reranking**, set `VERSLINE_RAG_RERANK_PROVIDER=optimum-intel`. Uses `OVModelForSequenceClassification` with sigmoid over the first logit. Export a cross-encoder model with:
    ```bash
    optimum-cli export openvino --model BAAI/bge-reranker-v2-m3 --task sequence-classification /models/bge-reranker-v2-m3-OpenVINO
    ```
- API-managed providers (`openai`, `cohere`, `jina`, `openrouter`, `avalai`) keep their own provider runtime.

### RAG Key Options (CLI)

| Group | Main flags |
| :--- | :--- |
| Chunking/Ingest | `--vector-size`, `--chunk-size`, `--chunk-overlap`, `--parent-child/--no-parent-child`, `--parent-chunk-size`, `--parent-chunk-overlap`, `--parent-child-fetch-k`, `--ingestion-batch-size`, `--log-every-batches`, `--resume`, `--force` |
| Retrieval/Hybrid | `--top-k`, `--retrieve-fetch-k`, `--hybrid/--no-hybrid`, `--hybrid-dense-weight`, `--hybrid-lexical-weight` |
| Dense backend | `--embedding-provider`, `--embedding-model`, `--embedding-model-path`, `--embedding-cache-dir`, `--embedding-local-files-only`, `--embedding-device`, `--embedding-use-fp16`, `--embedding-batch-size`, `--embedding-backend` |
| Sparse backend | `--sparse-provider`, `--sparse-model`, `--sparse-model-path`, `--sparse-cache-dir`, `--sparse-local-files-only`, `--sparse-device`, `--sparse-use-fp16`, `--sparse-batch-size` |
| Rerank | `--rerank/--no-rerank`, `--rerank-provider`, `--rerank-model`, `--rerank-api-key`, `--rerank-api-endpoint`, `--rerank-model-path`, `--rerank-cache-dir`, `--rerank-local-files-only`, `--rerank-device`, `--rerank-batch-size`, `--rerank-backend`, `--rerank-onnx-providers` |
| Timeouts | `--embedding-timeout`, `--generation-timeout`, `--qdrant-timeout`, `--rerank-timeout`, `--web-search-timeout`, `--mcp-timeout` |
| Rate limits | `--embedding-rpm`, `--embedding-tpm`, `--generation-rpm`, `--generation-tpm`, `--qdrant-rpm`, `--rerank-rpm`, `--rerank-tpm`, `--web-search-rpm` |
| External context | `--mcp`, `--mcp-transport`, `--mcp-server-url`, `--mcp-server-command`, `--mcp-server-args`, `--web-search`, `--web-search-provider` |
| Preflight | `--preflight/--no-preflight`, `--preflight-network/--no-preflight-network` |

### RAG Ecosystem Comparison (Web Research Snapshot — 2026-04-02)

The table below compares publicly available options that are close to Versline's RAG direction, based on official repository/docs sources.

#### 1) Library-First Comparison (Features, Quality, Ease of Use)

This quick matrix focuses specifically on **library usage** (not CLI), based on practical developer experience patterns and public project direction.

| Project | Features | RAG Output Quality | Library Ease of Use | Best Fit |
| :--- | :---: | :---: | :---: | :--- |
| **Versline (this repo)** | High (focused) | Very Good | Very Good (for current scope) | Ready-to-use ingestion/ask flow with built-in hybrid, rerank, rate limits, MCP |
| **LlamaIndex** | High | Very Good | Very Good | Fastest path for Python-first RAG apps with low boilerplate |
| **Haystack** | Very High | Excellent (production pipelines) | Medium–High | Complex, composable, production-grade pipelines and orchestration |
| **LangChain** | Very High (ecosystem) | Good–Very Good (depends on composition) | Medium | Flexible framework when you need broad integrations and custom chains |
| **txtai** | Medium–High | Good | High | Lightweight library/API-first setups with simple deployment paths |

#### 2) Operational Capabilities Matrix

This matrix checks three practical production needs: request/token rate limiting (and their combination), token usage tracking, and proxy-readiness.

| Project | Rate Limiting (Request + Token + Combination) | Token Tracker | Proxy Config Ready |
| :--- | :---: | :---: | :---: |
| **Versline (this repo)** | ✅ Native (RPM + TPM + combined) | ✅ Native | ✅ Native (per service) |
| **LlamaIndex** | ✅ Native (`requests_per_minute` + `tokens_per_minute`) | ✅ (`TokenCountingHandler`) | ⚠️ Provider/client dependent |
| **Haystack** | ⚠️ Primarily retry/fallback; no clear global native RPM+TPM combo | ✅ (`meta.usage` token usage fields) | ✅ (`http_client_kwargs`) |
| **LangChain** | ⚠️ Native request limiter, but no native token-based combo limiter | ✅ (`UsageMetadataCallbackHandler` / callbacks) | ✅ (`openai_proxy` and client config) |
| **txtai** | ❌ No clear native unified RPM/TPM limiter in core | ⚠️ Not a unified built-in token tracker in core | ⚠️ Mostly backend/kwargs dependent |

Legend: ✅ supported natively, ⚠️ partial or backend-dependent, ❌ not clearly available as a native unified capability.

*Proxy footnote:* In Versline, the ability to keep `qdrant` outside proxy routing while applying proxies to other services required additional customization due to practical limitations in `qdrant-client`; this behavior is implemented.

#### 3) Ecosystem Coverage (CLI, Library, Ingest/Query, Service Mode)

| Project | RAG CLI | Python Library | Ingest + Query Flow | Service/API Mode | Notes vs Versline |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Versline (this repo)** | ✅ `versline rag ingest/ask` | ✅ (`versline.services.rag`) | ✅ built-in with resumable ingest, hybrid + rerank, rate limits, MCP | ⚠️ Not a standalone HTTP service yet (CLI-first) | Strong CLI UX + provider-agnostic settings + resumability out of the box |
| **LlamaIndex** | ✅ `llamaindex-cli rag` ([source][cmp-llama-cli-readme], [source][cmp-llama-cli-cmd]) | ✅ core Python framework ([source][cmp-llama-readme]) | ✅ CLI and Python workflows both documented ([source][cmp-llama-rag-doc], [source][cmp-llama-workflow]) | ⚠️ Mostly via custom app code; CLI can scaffold create-llama path ([source][cmp-llama-rag-base]) | Closest "both CLI + library" alternative in this snapshot |
| **txtai** | ⚠️ No single `txtai rag` command found in examined docs; uses API/server + config | ✅ (`Embeddings`, `RAG`) ([source][cmp-txtai-rag-quickstart]) | ✅ Python + YAML/API flows documented ([source][cmp-txtai-rag-md], [source][cmp-txtai-api]) | ✅ FastAPI endpoints include `/rag` and `/batchrag` ([source][cmp-txtai-rag-router]) | Strong API-first path; CLI interaction is mostly `uvicorn` + config |
| **Haystack** | ⚠️ Core Haystack is Python-first; RAG CLI appears through **Hayhooks** deployment CLI ([source][cmp-hayhooks-cli]) | ✅ (`haystack-ai`) ([source][cmp-haystack-get-started]) | ✅ modular RAG pipelines in Python ([source][cmp-haystack-rag-pipeline]) | ✅ via Hayhooks serving/deploy endpoints ([source][cmp-hayhooks-overview]) | Very strong pipeline composition; less direct single-command local RAG than Versline CLI |
| **LangChain** | ⚠️ No first-party end-user RAG CLI in examined LangChain core docs/repo excerpts | ✅ (`pip install langchain`) ([source][cmp-langchain-readme]) | ✅ retrieval/RAG patterns available in Python APIs/guides ([source][cmp-langchain-rag-guide]) | ⚠️ Not shown as built-in RAG service in examined core sources | Broad ecosystem/framework; usually requires composition with extra components |

**Methodology note:** direct outbound HTTP from this environment was blocked, so this comparison uses official GitHub repository/documentation artifacts reachable via indexed repository queries.

[cmp-llama-cli-readme]: https://github.com/run-llama/llama_index/tree/main/llama-index-cli/README.md
[cmp-llama-cli-cmd]: https://github.com/run-llama/llama_index/tree/main/llama-index-cli/llama_index/cli/command_line.py
[cmp-llama-readme]: https://github.com/run-llama/llama_index/tree/main/README.md
[cmp-llama-rag-doc]: https://github.com/run-llama/llama_index/tree/main/docs/src/content/docs/framework/getting_started/starter_tools/rag_cli.md
[cmp-llama-workflow]: https://github.com/run-llama/llama_index/tree/main/docs/examples/workflow/rag.ipynb
[cmp-llama-rag-base]: https://github.com/run-llama/llama_index/tree/main/llama-index-cli/llama_index/cli/rag/base.py
[cmp-txtai-rag-quickstart]: https://github.com/neuml/txtai/tree/main/examples/rag_quickstart.py
[cmp-txtai-rag-md]: https://github.com/neuml/txtai/tree/main/docs/pipeline/llm/rag.md
[cmp-txtai-api]: https://github.com/neuml/txtai/tree/main/docs/api/index.md
[cmp-txtai-rag-router]: https://github.com/neuml/txtai/tree/main/src/python/txtai/api/routers/rag.py
[cmp-haystack-get-started]: https://github.com/deepset-ai/haystack/tree/main/docs-website/docs/overview/get-started.mdx
[cmp-haystack-rag-pipeline]: https://github.com/deepset-ai/haystack/tree/main/docs-website/docs/concepts/pipelines/creating-pipelines.mdx
[cmp-hayhooks-overview]: https://github.com/deepset-ai/haystack/tree/main/docs-website/docs/development/hayhooks.mdx
[cmp-hayhooks-cli]: https://github.com/deepset-ai/haystack/tree/main/docs-website/docs/development/hayhooks.mdx
[cmp-langchain-readme]: https://github.com/langchain-ai/langchain/tree/main/README.md
[cmp-langchain-rag-guide]: https://github.com/langchain-ai/langchain/tree/main/libs/langchain/langchain_classic/chains/question_answering/chain.py

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


## 🛠️ Features
- **Smart Context**: Uses previous chunks to identify speakers consistently.
- **Retry Mechanism**: Automatically retries failed API calls.
- **Rich UI**: Colorful progress bars and spinners.
- **Flexible**: Agnostic to LLM provider (Google, OpenAI, OpenRouter, AvalAI, Custom).
- **Markdown-to-Slides**: Generate immersive slide decks (`index.html`, `style.css`, `main.ts`) with optional Vite build and single-file export.
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

# Process file with specific chunking configuration
full_text = transcriber.process_file(
    "interview.mp3",
    chunk_length=600,  # 10 minutes
    overlap=60         # 1 minute overlap
)
print(full_text)
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

**4. RAG in Library Mode (Full Control):**
```python
from versline.services.rag import RAGPipeline
from versline.config import settings

settings.rag.web_search_enabled = True
settings.rag.web_search_provider = "duckduckgo"

pipeline = RAGPipeline(
    collection_name="fiqh_docs",
    embedding_model="text-embedding-3-small",
    embedding_provider="openai",
    embedding_api_key="YOUR_EMBEDDING_KEY",
    qdrant_url="http://localhost:6333",
    chunk_size=1200,
    chunk_overlap=200,
    ingestion_batch_size=32,
    hybrid_enabled=True,
    sparse_embedding_provider="flagembedding",  # fastembed | flagembedding
    sparse_embedding_model="BAAI/bge-m3",
    sparse_embedding_device="cpu",
    sparse_embedding_use_fp16=False,
    sparse_embedding_batch_size=8,
    sparse_embedding_local_files_only=True,
    sparse_embedding_model_path="/models/bge-m3",
    embedding_timeout_seconds=90,
    generation_timeout_seconds=180,
    qdrant_timeout_seconds=30,
    rerank_timeout_seconds=90,
    preflight=True,
    preflight_network=False,
)

# Ingest a directory
pipeline.ingest_path("./data/docs", resume=True, force=False)

# Ask with optional web context
result = pipeline.generate(
    query="خلاصه نکات اصلی چیست؟",
    top_k=5,
)

print(result["answer"])
print(result["metadata"].get("web_sources", []))
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


