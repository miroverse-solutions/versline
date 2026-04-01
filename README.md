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
2.  **`.env` File**: Create a `.env` file in your working directory.
3.  **Environment Variables**: Export variables in your shell.

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
```

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
from versline import AudioTranscriber, TextTranslator, download_file, settings

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


