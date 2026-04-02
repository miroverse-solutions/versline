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
    python -m build
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
VERSLINE_LLM_PROVIDER=AvalAI # Google, OpenAI, OpenRouter, AvalAI, OpenAICompatible
VERSLINE_LLM_API_KEY=your_api_key_here
VERSLINE_LLM_MODEL=gemini-2.0-flash
VERSLINE_LLM_PROXY=http://127.0.0.1:2080 # Optional
# VERSLINE_LLM_API_ENDPOINT=https://custom-api.example.com/v1 # Optional

VERSLINE_RAG_VECTOR_BACKEND=qdrant
VERSLINE_RAG_COLLECTION_NAME=versline_docs
VERSLINE_RAG_QDRANT_URL=http://localhost:6333
# VERSLINE_RAG_QDRANT_API_KEY=your_qdrant_api_key_here
VERSLINE_RAG_EMBEDDING_MODEL=text-embedding-3-small
# VERSLINE_RAG_EMBEDDING_PROXY=http://127.0.0.1:2080
# VERSLINE_RAG_GENERATION_PROXY=http://127.0.0.1:2080
# VERSLINE_RAG_QDRANT_PROXY=
VERSLINE_RAG_HYBRID_ENABLED=true
VERSLINE_RAG_SPARSE_EMBEDDING_MODEL=prithivida/Splade_PP_en_v1
VERSLINE_RAG_RERANK_ENABLED=false
VERSLINE_RAG_RERANK_PROVIDER=cohere
VERSLINE_RAG_RERANK_MODEL=rerank-v3.5
# VERSLINE_RAG_RERANK_API_KEY=your_rerank_api_key_here
# VERSLINE_RAG_RERANK_PROXY=http://127.0.0.1:2080
VERSLINE_RAG_RATE_LIMIT_RERANK_RPM=0
VERSLINE_RAG_RATE_LIMIT_EMBEDDING_RPM=0
VERSLINE_RAG_RATE_LIMIT_GENERATION_RPM=0
VERSLINE_RAG_RATE_LIMIT_QDRANT_RPM=0
VERSLINE_RAG_RATE_LIMIT_EMBEDDING_TPM=0
VERSLINE_RAG_RATE_LIMIT_GENERATION_TPM=0
VERSLINE_RAG_RATE_LIMIT_RERANK_TPM=0
VERSLINE_RAG_TOKEN_LIMIT_MODE=estimate_only
VERSLINE_RAG_MCP_ENABLED=false
VERSLINE_RAG_MCP_TRANSPORT=http
# VERSLINE_RAG_MCP_SERVER_URL=http://localhost:8080/mcp/context
# VERSLINE_RAG_MCP_SERVER_COMMAND=npx
# VERSLINE_RAG_MCP_SERVER_ARGS=@modelcontextprotocol/server-filesystem /home/mirza/projects/versline
VERSLINE_RAG_MCP_TOOL_NAME=retrieve_context
VERSLINE_RAG_MCP_TIMEOUT_SECONDS=30
VERSLINE_RAG_MCP_MAX_CONTEXT_CHARS=8000
VERSLINE_RAG_WEB_SEARCH_ENABLED=false
VERSLINE_RAG_WEB_SEARCH_PROVIDER=duckduckgo
# VERSLINE_RAG_WEB_SEARCH_API_KEY=your_tavily_api_key_here
# VERSLINE_RAG_WEB_SEARCH_ENDPOINT=https://api.tavily.com/search
VERSLINE_RAG_WEB_SEARCH_TIMEOUT_SECONDS=15
VERSLINE_RAG_WEB_SEARCH_TOP_K=3
# VERSLINE_RAG_WEB_SEARCH_PROXY=http://127.0.0.1:2080
VERSLINE_RAG_WEB_SEARCH_MAX_CONTEXT_CHARS=6000
VERSLINE_RAG_RATE_LIMIT_WEB_SEARCH_RPM=0
VERSLINE_RAG_RETRY_MAX_RETRIES=4
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

**Codebook Templates:**
- JSON template: `examples/qualcode/codebook.sample.json`
- TXT template: `examples/qualcode/codebook.sample.txt`

**Examples:**
```bash
# Strict: only codebook codes
versline qualcode interview.md --codebook examples/qualcode/codebook.sample.json --code-mode strict

# Guided: codebook codes + new codes when needed
versline qualcode interview.md --codebook examples/qualcode/codebook.sample.txt --code-mode guided
```

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
```

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
- **Proxy Support**: Full support for HTTP/HTTPS proxies.

## 📦 Python Library Usage

Versline is designed to be easily imported into your Python projects.

### Basic Setup
```python
from versline import AudioTranscriber, TextTranslator, download_file, settings, reload_settings

# Optional: load a specific env file in library mode
reload_settings("/path/to/.env")

# Or rely on fallback from environment variable:
# os.environ["VERSLINE_ENV_FILE"] = "/path/to/.env"
# reload_settings()

# Configure globally (or load from .env automatically)
settings.llm.provider = "AvalAI"
settings.llm.api_key = "YOUR_API_KEY"
settings.llm.model = "gpt-4o-mini"
```

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

**3. Qualitative Coding in Library Mode:**
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


