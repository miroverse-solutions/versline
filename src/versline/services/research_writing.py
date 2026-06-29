import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Type

from loguru import logger

from versline.config import settings
from versline.core.prompts import load_prompt
from versline.services import ai
from versline.services.pricing import TokenTracker


def load_research_input(input_path: str) -> Dict[str, Any]:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Research input file not found: {input_path}")

    suffix = path.suffix.lower()
    if suffix != ".json":
        raise ValueError("Research input file must be a JSON file.")

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Research input JSON must be an object.")
    return data


class BaseResearchSectionWriter:
    def __init__(
        self,
        user_note: Optional[str] = None,
        revision_note: Optional[str] = None,
        output_lang: str = "auto",
    ):
        self.user_note = user_note
        self.revision_note = revision_note
        self.output_lang = (output_lang or "auto").strip()
        self.tracker = TokenTracker()

    def generate_outline(self, research_inputs: Dict[str, Any]) -> str:
        raise NotImplementedError

    def generate_full_text(self, research_inputs: Dict[str, Any], approved_outline: str) -> str:
        raise NotImplementedError

    def _call_llm(self, prompt: str, model_name: str, max_retries: int = 3) -> str:
        provider = (settings.llm.provider or "google").lower()

        for attempt in range(max_retries):
            try:
                if provider == "google":
                    client = ai.configure_gemini(settings.llm)
                    response = client.models.generate_content(model=model_name, contents=prompt)
                    if response.usage_metadata:
                        self.tracker.add_usage(
                            response.usage_metadata.prompt_token_count,
                            response.usage_metadata.candidates_token_count,
                        )
                    if response.text:
                        return response.text

                elif provider in ("openai", "openrouter", "avalai", "openaicompatible"):
                    if provider == "openai":
                        client = ai.configure_openai(settings.llm)
                    elif provider == "openrouter":
                        client = ai.configure_openrouter(settings.llm)
                    elif provider == "avalai":
                        original_endpoint = settings.llm.api_endpoint
                        settings.llm.api_endpoint = original_endpoint or "https://api.avalai.ir/v1"
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
                    content = completion.choices[0].message.content
                    if content:
                        return content

                else:
                    raise ValueError(f"Provider '{provider}' is not supported for research writing.")

            except Exception as exc:
                logger.warning(f"Research writing attempt {attempt + 1} failed: {exc}")
                time.sleep(2)

        raise RuntimeError(f"Failed to produce output after {max_retries} attempts")

    def _language_instruction(self) -> str:
        if self.output_lang.lower() == "auto":
            return "Write in the same language as the source research materials."
        return (
            f"Write the output in {self.output_lang}. "
            "Generate directly in this language instead of translating after generation."
        )


class FindingsThematicColaizziWriter(BaseResearchSectionWriter):
    OUTLINE_PROMPT = "research_findings_colaizzi_outline_prompt.md"
    FULL_PROMPT = "research_findings_colaizzi_full_prompt.md"
    REVISION_PROMPT = "research_findings_revision_prompt.md"

    def __init__(
        self,
        user_note: Optional[str] = None,
        revision_note: Optional[str] = None,
        output_lang: str = "auto",
    ):
        super().__init__(user_note=user_note, revision_note=revision_note, output_lang=output_lang)
        self.outline_template = load_prompt(self.OUTLINE_PROMPT)
        self.full_template = load_prompt(self.FULL_PROMPT)
        self.revision_template = load_prompt(self.REVISION_PROMPT)

    def _append_revision_block(self, prompt: str) -> str:
        if not self.revision_note:
            return prompt

        revision_block = self.revision_template.format(revision_instructions=self.revision_note)
        return f"{prompt}\n\n---\n\n{revision_block}"

    def generate_outline(self, research_inputs: Dict[str, Any]) -> str:
        context_json = json.dumps(research_inputs, ensure_ascii=False, indent=2)
        prompt = self.outline_template.format(
            research_context_json=context_json,
            language_instruction=self._language_instruction(),
        )
        prompt = self._append_revision_block(prompt)
        if self.user_note:
            prompt = prompt + f"\n\n---\n\nAdditional user instructions:\n{self.user_note}"

        return self._call_llm(prompt=prompt, model_name=settings.llm.model)

    def generate_full_text(self, research_inputs: Dict[str, Any], approved_outline: str) -> str:
        if not approved_outline or not approved_outline.strip():
            raise ValueError("Approved outline is required for full-text generation.")

        context_json = json.dumps(research_inputs, ensure_ascii=False, indent=2)
        prompt = self.full_template.format(
            research_context_json=context_json,
            approved_outline=approved_outline,
            language_instruction=self._language_instruction(),
        )
        prompt = self._append_revision_block(prompt)
        if self.user_note:
            prompt = prompt + f"\n\n---\n\nAdditional user instructions:\n{self.user_note}"

        return self._call_llm(prompt=prompt, model_name=settings.llm.model)


def _normalize_key(section: str, method: str) -> Tuple[str, str]:
    normalized_section = (section or "").strip().lower()
    normalized_method = (method or "").strip().lower().replace("_", "-").replace(" ", "-")
    if normalized_method in {"colaizzi", "thematic-colaizzi", "thematic-colaizi"}:
        normalized_method = "thematic-colaizzi"
    return normalized_section, normalized_method


WRITER_REGISTRY: Dict[Tuple[str, str], Type[BaseResearchSectionWriter]] = {
    ("findings", "thematic-colaizzi"): FindingsThematicColaizziWriter,
}


class ResearchWritingService:
    def __init__(
        self,
        section: str,
        method: str,
        user_note: Optional[str] = None,
        revision_note: Optional[str] = None,
        output_lang: str = "auto",
    ):
        key = _normalize_key(section, method)
        writer_cls = WRITER_REGISTRY.get(key)
        if writer_cls is None:
            supported = [f"{sec}:{m}" for sec, m in WRITER_REGISTRY.keys()]
            raise ValueError(
                f"Unsupported section/method '{section}:{method}'. Supported: {', '.join(supported)}"
            )

        self.section, self.method = key
        self.writer = writer_cls(user_note=user_note, revision_note=revision_note, output_lang=output_lang)
        self.tracker = self.writer.tracker

    def generate_outline(self, research_inputs: Dict[str, Any]) -> str:
        return self.writer.generate_outline(research_inputs)

    def generate_full_text(self, research_inputs: Dict[str, Any], approved_outline: str) -> str:
        return self.writer.generate_full_text(research_inputs, approved_outline)
