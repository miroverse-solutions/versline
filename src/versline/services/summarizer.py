import re
import time
from pathlib import Path

from loguru import logger

from versline.config import settings
from versline.core.prompts import load_prompt
from versline.services import ai
from versline.services.document_processor import convert_to_markdown
from versline.services.pricing import TokenTracker

MODES = {
    "outline": "summarize_outline_prompt.md",
    "detailed": "summarize_detailed_prompt.md",
    "slides": "summarize_slides_prompt.md",
}


# Sentinel for "same language as input"
_AUTO_LANG = "auto"


class TextSummarizer:
    """Summarize documents in one of three modes: outline, detailed, or slides.

    Parameters
    ----------
    mode:
        One of ``"outline"``, ``"detailed"``, or ``"slides"``.
    output_lang:
        Language to write the output in.  Use ``"auto"`` (default) to keep the
        same language as the source text.  Any other value (e.g. ``"English"``,
        ``"Persian"``) instructs the LLM to generate directly in that language.
    preserve_terms:
        When *True* and *output_lang* differs from the source language, the LLM
        is instructed to include the original-language term in parentheses after
        every specialised technical term it translates.
    """

    def __init__(
        self,
        mode: str = "detailed",
        output_lang: str = _AUTO_LANG,
        preserve_terms: bool = True,
    ):
        if mode not in MODES:
            raise ValueError(f"Invalid mode '{mode}'. Choose from: {list(MODES)}")
        self.mode = mode
        self.output_lang = output_lang.strip() if output_lang else _AUTO_LANG
        self.preserve_terms = preserve_terms
        self.tracker = TokenTracker()

        try:
            self.prompt_template = load_prompt(MODES[mode])
        except FileNotFoundError:
            logger.warning(f"Summarization prompt for mode '{mode}' not found.")
            self.prompt_template = "{text}"

    # ------------------------------------------------------------------
    # Prompt instruction builders
    # ------------------------------------------------------------------

    def _language_instruction(self) -> str:
        if self.output_lang.lower() == _AUTO_LANG:
            return "Write the output in the same language as the input text."
        return (
            f"Write the entire output in {self.output_lang}. "
            "Generate the content directly in this language — do not first write "
            "in another language and then translate."
        )

    def _terms_instruction(self) -> str:
        if not self.preserve_terms or self.output_lang.lower() == _AUTO_LANG:
            return "Preserve specialised technical terms as they appear in the source."
        return (
            "For specialised technical terms that originate from the source language, "
            "include the original-language term in parentheses immediately after the "
            "output-language equivalent, "
            "e.g.: شبکه عصبی مصنوعی (artificial neural network). "
            "If a widely accepted equivalent exists in the output language, prefer it; "
            "otherwise keep the source-language term unchanged."
        )

    # ------------------------------------------------------------------
    # Text reading
    # ------------------------------------------------------------------

    def _read_source_text(self, file_path: str) -> str:
        path = Path(file_path)
        text_extensions = {
            ".txt", ".md", ".markdown", ".csv", ".json",
            ".xml", ".html", ".htm", ".yaml", ".yml",
        }
        extension = path.suffix.lower()

        if extension in text_extensions:
            raw = path.read_bytes()
            for encoding in ("utf-8", "utf-8-sig", "cp1256", "cp1252", "latin-1"):
                try:
                    return raw.decode(encoding)
                except UnicodeDecodeError:
                    continue
            raise ValueError(
                "Could not decode text file with supported encodings "
                "(utf-8, utf-8-sig, cp1256, cp1252, latin-1)."
            )

        # Non-text file: convert to markdown via markitdown
        try:
            extracted = convert_to_markdown(str(path))
        except Exception as exc:
            raise ValueError(
                "Could not read file as UTF-8 text and automatic document "
                f"extraction failed. Details: {exc}"
            ) from exc

        if not extracted or not extracted.strip():
            raise ValueError("No readable text could be extracted from the input file.")

        return extracted

    # ------------------------------------------------------------------
    # Semantic chunking
    # ------------------------------------------------------------------

    @staticmethod
    def split_by_sections(text: str, max_chars: int = 3000) -> list[str]:
        """Split *text* into semantically coherent chunks.

        Strategy (in order of preference):
        1. Split at top-level heading boundaries (# or ##).
        2. If a section still exceeds *max_chars*, sub-split at ### headings.
        3. If still too large, fall back to paragraph splitting while
           preserving the parent heading as a context header in each sub-chunk.
        """
        # Normalise line endings
        text = text.replace("\r\n", "\n")

        heading_re = re.compile(r"^(#{1,2})\s+.+", re.MULTILINE)
        sections = _split_at_pattern(text, heading_re)

        chunks: list[str] = []
        for section in sections:
            if len(section) <= max_chars:
                chunks.append(section)
            else:
                chunks.extend(_subsplit_section(section, max_chars))

        # Remove empty chunks
        return [c for c in chunks if c.strip()]

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    def summarize_chunk(self, text: str, model_name: str, max_retries: int = 3) -> str:
        prompt = self.prompt_template.format(
            text=text,
            language_instruction=self._language_instruction(),
            terms_instruction=self._terms_instruction(),
        )

        for attempt in range(max_retries):
            try:
                provider = (settings.llm.provider or "google").lower()
                logger.debug(f"Summarizing chunk with {provider} (attempt {attempt + 1})")

                result: str | None = None

                if provider == "google":
                    client = ai.configure_gemini(settings.llm)
                    response = client.models.generate_content(
                        model=model_name, contents=prompt
                    )
                    if response.usage_metadata:
                        self.tracker.add_usage(
                            response.usage_metadata.prompt_token_count,
                            response.usage_metadata.candidates_token_count,
                        )
                    result = response.text

                elif provider in ("openai", "openrouter", "avalai", "openaicompatible"):
                    if provider == "openai":
                        client = ai.configure_openai(settings.llm)
                    elif provider == "openrouter":
                        client = ai.configure_openrouter(settings.llm)
                    elif provider == "avalai":
                        original_endpoint = settings.llm.api_endpoint
                        settings.llm.api_endpoint = (
                            original_endpoint or "https://api.avalai.ir/v1"
                        )
                        try:
                            client = ai.configure_openai(settings.llm)
                        finally:
                            settings.llm.api_endpoint = original_endpoint
                    else:
                        client = ai.configure_openai(settings.llm)

                    is_avalai = provider == "avalai" or (
                        hasattr(client, "base_url")
                        and (
                            "avalai.ir" in str(client.base_url)
                            or "avalapis.ir" in str(client.base_url)
                        )
                    )

                    if is_avalai and hasattr(client.chat.completions, "with_raw_response"):
                        raw = client.chat.completions.with_raw_response.create(
                            model=model_name,
                            messages=[{"role": "user", "content": prompt}],
                        )
                        request_id = raw.headers.get("x-request-id")
                        if request_id:
                            self.tracker.add_avalai_request(request_id)
                        completion = raw.parse()
                    else:
                        completion = client.chat.completions.create(
                            model=model_name,
                            messages=[{"role": "user", "content": prompt}],
                        )

                    if completion.usage:
                        self.tracker.add_usage(
                            completion.usage.prompt_tokens,
                            completion.usage.completion_tokens,
                        )
                    result = completion.choices[0].message.content

                else:
                    raise ValueError(
                        f"Provider '{provider}' is not supported for summarization."
                    )

                if result:
                    return result

            except Exception as exc:
                logger.warning(f"Summarization attempt {attempt + 1} failed: {exc}")
                time.sleep(2)

        raise RuntimeError(f"Failed to summarize chunk after {max_retries} attempts")

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def process_file(
        self,
        file_path: str,
        progress_callback=None,
    ) -> str:
        """Read *file_path*, summarize it in *self.mode*, and return Markdown."""
        text = self._read_source_text(file_path)

        if not text.strip():
            raise ValueError("Input file is empty after text extraction.")

        chunks = self.split_by_sections(text)
        total = len(chunks)
        results: list[str] = []

        if progress_callback:
            progress_callback(0, total, "Starting summarization…")

        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                results.append("")
                continue

            if progress_callback:
                progress_callback(i, total, f"Summarizing part {i + 1}/{total}…")

            summarized = self.summarize_chunk(chunk, settings.llm.model)
            results.append(summarized)

            if progress_callback:
                progress_callback(i + 1, total, f"Completed part {i + 1}")

        return "\n\n".join(r for r in results if r.strip())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _split_at_pattern(text: str, pattern: re.Pattern) -> list[str]:
    """Split *text* at every match of *pattern* (match becomes start of new section)."""
    matches = list(pattern.finditer(text))
    if not matches:
        return [text]

    sections: list[str] = []
    prev_end = 0

    # Text before first heading
    if matches[0].start() > 0:
        sections.append(text[prev_end : matches[0].start()])

    for idx, match in enumerate(matches):
        next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections.append(text[match.start() : next_start])

    return sections


def _subsplit_section(section: str, max_chars: int) -> list[str]:
    """Try to split *section* at ### headings; fall back to paragraphs."""
    # Extract a potential parent heading for context
    first_line_end = section.find("\n")
    parent_heading = section[: first_line_end + 1] if first_line_end != -1 else ""

    sub_re = re.compile(r"^###\s+.+", re.MULTILINE)
    sub_sections = _split_at_pattern(section, sub_re)

    chunks: list[str] = []
    for sub in sub_sections:
        if len(sub) <= max_chars:
            chunks.append(sub)
        else:
            # Fall back to paragraph splitting, keeping parent heading as context
            chunks.extend(
                _split_by_paragraphs(sub, max_chars, context_header=parent_heading)
            )

    return chunks


def _split_by_paragraphs(
    text: str, max_chars: int, context_header: str = ""
) -> list[str]:
    """Split *text* into paragraph-based chunks not exceeding *max_chars*."""
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = len(context_header)

    for para in paragraphs:
        if current_len + len(para) > max_chars and current_parts:
            chunk_text = context_header + "\n\n".join(current_parts)
            chunks.append(chunk_text)
            current_parts = [para]
            current_len = len(context_header) + len(para)
        else:
            current_parts.append(para)
            current_len += len(para)

    if current_parts:
        chunks.append(context_header + "\n\n".join(current_parts))

    return chunks
