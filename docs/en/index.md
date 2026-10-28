# Versline Documentation

**English** · [فارسی](../fa/index.md)

Versline is a command-line toolkit and Python library by Miroverse Solutions. It uses large language models (LLMs) to turn media and documents into useful text. Current version: **1.0.4** (MIT license).

## What it does

| Command | Purpose |
| :--- | :--- |
| `transcribe` | Audio/video (file or URL) to text, optionally with timestamps |
| `translate` | Translate a text/document file |
| `summarize` | Summarize a file (outline, detailed, slides; optional didactic mode) |
| `qude` | Generate MCQ / open questions and export to CSV, Anki, HTML |
| `qualcode` | Qualitative coding (thematic, grounded, content, framework, Colaizzi) |
| `research` | Staged academic writing of a "findings" chapter |
| `slides` | Generate HTML/TypeScript slide decks from Markdown |
| `telegram` | Archive a Telegram channel into Obsidian notes (with transcripts, summaries, taqrir) |
| `init`, `config`, `update` | First-time setup, show saved settings, self-update |

Supported LLM providers: **Google (Gemini), OpenAI, OpenRouter, AvalAI, and any OpenAI-compatible endpoint**.

## Contents

1. [Installation](installation.md)
2. [Configuration](configuration.md)
3. [Command reference](commands.md)
4. [Telegram channel archive](telegram.md)
5. [Python library and MCP server](library.md)
6. [Architecture and development](architecture.md)
7. [Troubleshooting](troubleshooting.md)

## Quick start

```sh
# 1. Install (see installation.md for Windows)
curl -LsSf https://raw.githubusercontent.com/miroverse-solutions/versline/main/install.sh | sh

# 2. One-time setup: pick a provider and save your API key
versline init

# 3. Use it
versline transcribe interview.mp3
versline translate article.md --lang English
versline summarize paper.pdf --mode outline
```

Results are written to the `output/` folder of the current directory by default (`VERSLINE_OUTPUT_DIRECTORY`).
