# Versline
**Advanced Toolkit for Transcription, Translation, and Media Processing**

## 🚀 Installation

```bash
pip install .
```

## ⚙️ Configuration

You can configure Versline using any of the following methods (in order of priority):

1.  **CLI Arguments**: Pass directly to commands (e.g., `--api-key`).
2.  **`.env` File**: Create a `.env` file in your working directory.
3.  **Environment Variables**: Export variables in your shell.

### `.env` File Example
Run `cp .env.example .env` to start, or create one manually:

```dotenv
VERSLINE_LLM_PROVIDER=Google
VERSLINE_LLM_API_KEY=your_api_key_here
VERSLINE_LLM_MODEL=gemini-2.0-flash
# VERSLINE_FFMPEG_FFMPEG_PATH=/usr/bin/ffmpeg
```

## 📖 Usage Guide

Run `versline --help` to see the colorful interactive guide.

### 🎙️ 1. Transcribe (Speech to Text)

Convert audio or video files to text with high accuracy using LLMs.

**Basic Usage:**
```bash
versline transcribe file interview.mp3
```

**Auto-Download & Transcribe:**
Pass a URL directly, and Versline will download it first:
```bash
versline transcribe file "https://example.com/podcast.mp3"
```

**Advanced Options:**
```bash
versline transcribe file interview.wav \
  --provider Google \
  --model gemini-1.5-pro \
  --chunk-size 600 \
  --overlap 60 \
  --output ./final_text.md
```

### 📝 2. Translate

Translate large text files into any language (default: Persian) with context-aware splitting.

```bash
versline translate file ./document.txt --lang "English"
```

## 🛠️ Features
- **Smart Context**: Uses previous chunks to identify speakers consistently.
- **Retry Mechanism**: Automatically retries failed API calls.
- **Rich UI**: Colorful progress bars and spinners.
- **Flexible**: Agnostic to LLM provider (Google, OpenAI, OpenRouter).

## 📦 Python Library Usage

Versline is designed to be easily imported into your Python projects.

### Basic Setup
```python
from versline import AudioTranscriber, TextTranslator, download_file, settings

# Configure globally (or load from .env automatically)
settings.llm.provider = "Google"
settings.llm.api_key = "YOUR_API_KEY"
settings.llm.model = "gemini-2.0-flash"
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


