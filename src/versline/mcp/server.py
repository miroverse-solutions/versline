"""
versline MCP Server

Exposes versline CLI commands as MCP tools. Uses subprocess to call versline,
so it does NOT import versline modules directly.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "versline",
    instructions="Miroverse Toolkit — transcription, translation, summarization, Q&A, slides, RAG, and more.",
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Find project root (parent of src/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_VERSLINE_PYTHON = sys.executable


def _versline_subprocess(*args: str, timeout: int = 600) -> str:
    """Run versline CLI as a subprocess and return captured output."""
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", f"{_PROJECT_ROOT / 'src'}:{env.get('PYTHONPATH', '')}")

    # Only add PYTHONPATH if versline isn't already installed
    try:
        import versline  # noqa: F401
    except ImportError:
        pass
    else:
        env.pop("PYTHONPATH", None)

    cmd = [_VERSLINE_PYTHON, "-m", "versline.cli", *args]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"versline CLI failed (exit {result.returncode}):\n"
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    # versline logs go to stderr (loguru), actual result to stdout
    return result.stdout.strip() or result.stderr.strip()


def _save_temp_file(content: str, suffix: str = ".md") -> str:
    """Write content to a temp file, return its path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    )
    tmp.write(content)
    tmp.close()
    return tmp.name


# ---------------------------------------------------------------------------
# Helper: build common args
# ---------------------------------------------------------------------------

def _build_llm_args(
    model: Optional[str] = None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    endpoint: Optional[str] = None,
) -> list[str]:
    args = []
    if model:
        args += ["--model", model]
    if provider:
        args += ["--provider", provider]
    if api_key:
        args += ["--api-key", api_key]
    if endpoint:
        args += ["--api-endpoint", endpoint]
    return args


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(
    name="transcribe",
    description="Transcribe an audio/video file to text using LLMs. Supports local paths and URLs.",
)
def transcribe(
    file_path: str,
    *,
    output: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    json_output: bool = False,
    note: Optional[str] = None,
) -> str:
    cmd = ["transcribe", file_path]
    cmd += _build_llm_args(model=model, provider=provider)
    if output:
        cmd += ["--output", output]
    if json_output:
        cmd += ["--json"]
    if note:
        cmd += ["--note", note]
    return _versline_subprocess(*cmd)


@mcp.tool(
    name="translate",
    description="Translate a text/markdown file to another language.",
)
def translate(
    file_path: str,
    target_lang: str = "Persian",
    *,
    output: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    note: Optional[str] = None,
) -> str:
    cmd = ["translate", file_path, "--lang", target_lang]
    cmd += _build_llm_args(model=model, provider=provider)
    if output:
        cmd += ["--output", output]
    if note:
        cmd += ["--note", note]
    return _versline_subprocess(*cmd)


@mcp.tool(
    name="summarize",
    description="Summarize a file in multiple modes: outline, detailed, slides, or didactic.",
)
def summarize(
    file_path: str,
    mode: str = "detailed",
    *,
    output_lang: Optional[str] = None,
    compression: Optional[int] = None,
    didactic: bool = False,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    note: Optional[str] = None,
) -> str:
    supported = ("outline", "detailed", "slides")
    if mode not in supported:
        raise ValueError(f"Unsupported mode '{mode}'. Choose: {', '.join(supported)}")
    cmd = ["summarize", file_path, "--mode", mode]
    cmd += _build_llm_args(model=model, provider=provider)
    if output_lang:
        cmd += ["--output-lang", output_lang]
    if compression is not None:
        cmd += ["--compression", str(compression)]
    if didactic:
        cmd += ["--didactic"]
    if note:
        cmd += ["--note", note]
    return _versline_subprocess(*cmd)


@mcp.tool(
    name="generate_questions",
    description="Generate questions (MCQ or open-ended) from a document.",
)
def generate_questions(
    file_path: str,
    question_type: str = "mcq",
    *,
    language: str = "en",
    count: Optional[int] = None,
    output_dir: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    note: Optional[str] = None,
) -> str:
    if question_type not in ("mcq", "open"):
        raise ValueError("question_type must be 'mcq' or 'open'")
    cmd = ["qude", file_path, "--type", question_type, "--lang", language]
    cmd += _build_llm_args(model=model, provider=provider)
    if count is not None:
        cmd += ["--count", str(count)]
    if output_dir:
        cmd += ["--output", output_dir]
    if note:
        cmd += ["--note", note]
    return _versline_subprocess(*cmd)


@mcp.tool(
    name="generate_slides",
    description="Generate an HTML/CSS/TS slide deck from a markdown file.",
)
def generate_slides(
    file_path: str,
    *,
    output_dir: Optional[str] = None,
    use_impress: bool = False,
    use_revealjs: bool = False,
    build: bool = False,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    note: Optional[str] = None,
) -> str:
    cmd = ["slides", file_path]
    cmd += _build_llm_args(model=model, provider=provider)
    if output_dir:
        cmd += ["--output", output_dir]
    if use_impress:
        cmd += ["--impress"]
    if use_revealjs:
        cmd += ["--revealjs"]
    if build:
        cmd += ["--build"]
    if note:
        cmd += ["--note", note]
    return _versline_subprocess(*cmd)


@mcp.tool(
    name="transcribe_text",
    description="Transcribe text content directly (writes to temp file first).",
)
def transcribe_text(
    text: str,
    *,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    note: Optional[str] = None,
) -> str:
    tmp = _save_temp_file(text, suffix=".txt")
    try:
        return transcribe(tmp, model=model, provider=provider, note=note)
    finally:
        os.unlink(tmp)


@mcp.tool(
    name="translate_text",
    description="Translate plain text directly without a file on disk.",
)
def translate_text(
    text: str,
    target_lang: str = "Persian",
    *,
    model: Optional[str] = None,
    provider: Optional[str] = None,
) -> str:
    tmp = _save_temp_file(text, suffix=".txt")
    try:
        return translate(tmp, target_lang, model=model, provider=provider)
    finally:
        os.unlink(tmp)


@mcp.tool(
    name="summarize_text",
    description="Summarize plain text directly without a file on disk.",
)
def summarize_text(
    text: str,
    mode: str = "detailed",
    *,
    output_lang: Optional[str] = None,
    compression: Optional[int] = None,
    didactic: bool = False,
    model: Optional[str] = None,
    provider: Optional[str] = None,
) -> str:
    tmp = _save_temp_file(text, suffix=".md")
    try:
        return summarize(
            tmp,
            mode=mode,
            output_lang=output_lang,
            compression=compression,
            didactic=didactic,
            model=model,
            provider=provider,
        )
    finally:
        os.unlink(tmp)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == "__main__":
    main()
