# Versline AI Coding Instructions

You are an expert developer working on **Versline**, a Python-based CLI toolkit and library for media processing (transcription, translation) and educational content generation (quizzes, flashcards) using LLMs.

## 🏗️ Architecture & Organization

- **Core Structure**: The project follows the `src/` layout.
  - `src/versline/commands/`: CLI entry points using `typer`. Logic here should be thin wrappers around services.
  - `src/versline/services/`: Business logic (AI interaction, media processing, network).
    - `transcription.py`: Audio processing with chunking, resuming, and speaker usage.
    - `translation.py`: Document translation with chunking.
    - `question_generator.py`: Quiz/Flashcard generation logic.
  - `src/versline/resources/prompts/`: Markdown files containing system prompts.
  - `src/versline/core/`: Shared constants and utilities (e.g., `load_prompt`).

- **Data Flow**:
  1.  **CLI** parses args and initializes `Settings`.
  2.  **Service** is instantiated (e.g., `AudioTranscriber`).
  3.  **Service** loads prompts via `load_prompt("filename.md")`.
  4.  **LLM Client** (`services.ai`) is configured based on `settings.llm` (provider agnostic).
  5.  **Processing** occurs in chunks (audio or text) with progress tracking.

## 🔑 Key Conventions & Patterns

### 1. Prompt Management
- **Storage**: Store ALL system prompts in `src/versline/resources/prompts/` as `.md` files.
- **Loading**: Use `versline.core.prompts.load_prompt` to read them.
- **Parametrization**: Use standard f-string formatting or `.format()` in services to inject context into prompts.

### 2. LLM Integration (`services/ai.py`)
- **Agnostic Design**: Code must work across `OpenAI`, `Google` (Gemini), `AvalAI`, and `OpenAICompatible` providers.
- **Configuration**: Use `versline.config.settings.llm` to access global configuration.
- **Client Instantiation**: Use factory functions in `services.ai` (e.g., `configure_openai`, `configure_gemini`) rather than direct SDK usage in commands.

### 3. Resumable Long-Running Tasks
- **State Tracking**: `process_file` methods in services (like `transcription.py`) implement their own state persistence.
- **Progress File**: Use `progress.json` stored in `work_dir/{filename_stem}/` to track completed chunks.
- **Force Mode**: Implement a `force=True` argument in `process_file` to strictly delete existing partial progress and restart.

### 4. CLI with Typer & Rich
- **Progress Bars**: Use `rich.progress` contexts within CLI commands, passing a callback (`progress_callback`) to services.
- **Arguments**: Use `typer.Option` for configuration and `typer.Argument` for required inputs.
- **Help**: Ensure `help="..."` strings are provided for all arguments.

### 5. Output Management
- **JSON Handling**: When outputs are JSON (like `transcribe --json`), ensure:
  - Markdown code blocks (````json ... ````) are stripped from LLM responses before parsing.
  - Multi-chunk JSON responses are merged intelligently (concatenating lists, merging text), not just appended.

### 6. Configuration Loading (`config.py`)
- **Single Source of Truth**: Keep configuration loading centralized in `src/versline/config.py`.
- **Do NOT load dotenv in commands/services**: Use `versline.config.settings` and `versline.config.reload_settings(...)` instead of ad-hoc `load_dotenv` usage.
- **Supported Env Sources (current behavior):**
  1. CLI command options (e.g. `--api-key`) override settings at runtime.
  2. Global CLI `--env-file` (on root command) loads a custom env file before subcommands.
  3. Process environment variables are respected.
  4. Local `.env` is read by pydantic settings (`env_file='.env'`).
  5. `VERSLINE_ENV_FILE` acts as fallback custom env path when `--env-file` is not provided.
- **Override Semantics**:
  - Explicit `reload_settings(env_file=...)` should override existing env keys.
  - Fallback via `VERSLINE_ENV_FILE` should not overwrite already-defined process env values.
- **Library Usage Contract**:
  - In embedded/library scenarios, call `reload_settings('/path/to/.env')` when a non-default env file must be applied.

## 🛠️ Workflows & Commands

### Build & Install
Due to network isolation in some build environments, use `--no-isolation` when building if dependencies are already present in the environment.

```bash
# Install in editable mode
pip install -e .

# Build distribution (Wheel/Tarball)
python -m build --no-isolation
```

### Running CLI in Dev
Use the module execution method to test changes without reinstalling:
```bash
# Add src to pythonpath if needed, though pip -e . handles it usually
python -m versline.cli [COMMAND] [ARGS]
```

## 🚨 Critical Rules
1.  **Never hardcode prompts** in Python files. Move them to `resources/prompts`.
2.  **Respect `settings`**: Always check `versline.config.settings` for API keys and Proxies before falling back to defaults.
3.  **Logging**: Use `loguru` (`from loguru import logger`) instead of standard `logging`.
