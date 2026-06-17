#!/bin/bash
# versline MCP server — standalone (direct imports, no subprocess)
# This avoids loading heavy RAG/CLI dependencies.
export VERSLINE_ENV_FILE="$(dirname "$0")/.env"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$(pwd)/src"
cd "$(dirname "$0")"
exec python3 -c "
import sys
sys.path.insert(0, 'src')

# Only import what we need (no CLI, no RAG)
from versline.services.transcription import AudioTranscriber
from versline.services.translation import TextTranslator
from versline.services.summarizer import TextSummarizer, MODES
from versline.services.question_generator import QuestionDesigner
from versline.services.slides import MarkdownSlideDeckGenerator
from versline.config import settings

from mcp.server.fastmcp import FastMCP

mcp = FastMCP('versline')

from typing import Optional
import tempfile, os, json

def _save_temp_file(content: str, suffix: str = '.md') -> str:
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False, encoding='utf-8')
    tmp.write(content)
    tmp.close()
    return tmp.name

@mcp.tool(name='transcribe', description='Transcribe an audio/video file to text using LLMs. Set timestamped=true for timestamp-aligned segments.')
def transcribe(file_path: str, *, model: Optional[str] = None, provider: Optional[str] = None, json_output: bool = False, note: Optional[str] = None, timestamped: bool = False, timestamp_model: Optional[str] = None, chunk_minutes: Optional[int] = None) -> str:
    if model: settings.llm.model = model
    if provider: settings.llm.provider = provider
    transcriber = AudioTranscriber(user_note=note)
    result = transcriber.process_file(file_path, timestamped=timestamped, timestamp_model=timestamp_model, chunk_minutes=chunk_minutes)
    if timestamped and isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False, indent=2)
    return result

@mcp.tool(name='translate', description='Translate a text/markdown file to another language.')
def translate(file_path: str, target_lang: str = 'Persian', *, model: Optional[str] = None, provider: Optional[str] = None, note: Optional[str] = None) -> str:
    if model: settings.llm.model = model
    if provider: settings.llm.provider = provider
    translator = TextTranslator(user_note=note)
    return translator.process_file(file_path, target_language=target_lang)

@mcp.tool(name='summarize', description='Summarize a file: outline, detailed, slides, or didactic.')
def summarize(file_path: str, mode: str = 'detailed', *, output_lang: Optional[str] = None, compression: Optional[int] = None, didactic: bool = False, model: Optional[str] = None, provider: Optional[str] = None, note: Optional[str] = None) -> str:
    if mode not in MODES: raise ValueError(f'Unsupported mode')
    if model: settings.llm.model = model
    if provider: settings.llm.provider = provider
    summarizer = TextSummarizer(mode=mode, output_lang=output_lang or 'auto', preserve_terms=True, didactic=didactic, compression=compression, user_note=note)
    return summarizer.process_file(file_path)

@mcp.tool(name='generate_questions', description='Generate MCQ or open-ended questions from a document.')
def generate_questions(file_path: str, question_type: str = 'mcq', *, language: str = 'en', count: Optional[int] = None, model: Optional[str] = None, provider: Optional[str] = None, note: Optional[str] = None) -> str:
    designer = QuestionDesigner(input_path=file_path, output_dir='output', question_type=question_type, language=language, num_questions=count, user_note=note, provider=provider, model=model)
    designer.process()
    return f'Questions generated from {file_path}'

@mcp.tool(name='generate_slides', description='Generate an HTML/CSS/TS slide deck from markdown.')
def generate_slides(file_path: str, *, output_dir: Optional[str] = None, use_impress: bool = False, use_revealjs: bool = False, build: bool = False, model: Optional[str] = None, provider: Optional[str] = None, note: Optional[str] = None) -> str:
    if use_impress and use_revealjs: use_impress = False
    if model: settings.llm.model = model
    if provider: settings.llm.provider = provider
    generator = MarkdownSlideDeckGenerator(provider=settings.llm.provider, model=settings.llm.model, api_key=settings.llm.api_key, api_endpoint=settings.llm.api_endpoint, proxy=settings.llm.proxy, use_impress=use_impress, use_revealjs=use_revealjs, user_note=note)
    result = generator.generate_from_markdown(input_path=file_path, output_dir=output_dir or 'output', build=build)
    return f'Slides generated: {result.get('index_html', '')}'

@mcp.tool(name='transcribe_text', description='Transcribe text content directly.')
def transcribe_text(text: str, *, model: Optional[str] = None, provider: Optional[str] = None, note: Optional[str] = None) -> str:
    tmp = _save_temp_file(text, '.txt')
    try: return transcribe(tmp, model=model, provider=provider, note=note)
    finally: os.unlink(tmp)

@mcp.tool(name='translate_text', description='Translate plain text directly.')
def translate_text(text: str, target_lang: str = 'Persian', *, model: Optional[str] = None, provider: Optional[str] = None) -> str:
    tmp = _save_temp_file(text, '.txt')
    try: return translate(tmp, target_lang, model=model, provider=provider)
    finally: os.unlink(tmp)

@mcp.tool(name='summarize_text', description='Summarize plain text directly.')
def summarize_text(text: str, mode: str = 'detailed', *, output_lang: Optional[str] = None, compression: Optional[int] = None, didactic: bool = False, model: Optional[str] = None, provider: Optional[str] = None) -> str:
    tmp = _save_temp_file(text, '.md')
    try: return summarize(tmp, mode=mode, output_lang=output_lang, compression=compression, didactic=didactic, model=model, provider=provider)
    finally: os.unlink(tmp)

mcp.run()
" "$@"
