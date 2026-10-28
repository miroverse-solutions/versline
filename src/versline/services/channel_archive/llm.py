from __future__ import annotations

import time

from loguru import logger

from versline.config import settings
from versline.services import ai
from versline.services.ai import track_openai_usage


class TextLLM:
    """Single-prompt text generation with the configured LLM provider (used for summaries and taqrir)."""

    def __init__(self, tracker):
        self.tracker = tracker

    def _openai_client(self, provider: str):
        if provider == "openrouter":
            return ai.configure_openrouter(settings.llm)
        if provider == "avalai":
            original = settings.llm.api_endpoint
            settings.llm.api_endpoint = original or "https://api.avalai.ir/v1"
            try:
                return ai.configure_openai(settings.llm)
            finally:
                settings.llm.api_endpoint = original
        return ai.configure_openai(settings.llm)

    def _once(self, prompt: str) -> str:
        provider = (settings.llm.provider or "google").lower()
        model = settings.llm.model
        if provider == "google":
            client = ai.configure_gemini(settings.llm)
            response = client.models.generate_content(model=model, contents=prompt)
            if response.usage_metadata:
                self.tracker.add_usage(
                    response.usage_metadata.prompt_token_count,
                    response.usage_metadata.candidates_token_count,
                )
            return response.text or ""
        if provider in ("openai", "openrouter", "avalai", "openaicompatible"):
            client = self._openai_client(provider)
            is_avalai = provider == "avalai" or "avalai.ir" in str(getattr(client, "base_url", ""))
            return ai.call_openai_with_document_prefix(client, model, "", prompt, self.tracker, is_avalai=is_avalai) or ""
        raise ValueError(f"Provider '{provider}' is not supported for text generation.")

    def generate(self, prompt: str, max_retries: int = 3) -> str:
        for attempt in range(max_retries):
            try:
                text = self._once(prompt).strip()
                if text:
                    return text
            except Exception as exc:
                logger.warning(f"LLM call failed (attempt {attempt + 1}/{max_retries}): {exc}")
            time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"LLM returned no text after {max_retries} attempts")
