from __future__ import annotations

import base64
import mimetypes
import time
from pathlib import Path
from typing import Callable

from loguru import logger

from versline.config import settings
from versline.services import ai
from versline.services.ai import track_openai_usage


class TextLLM:
    """Single-prompt text generation with the configured LLM provider (summaries, taqrir, reading images)."""

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

    def _image_once(self, prompt: str, image_path: Path) -> str:
        provider = (settings.llm.provider or "google").lower()
        model = settings.llm.model
        data = Path(image_path).read_bytes()
        mime = mimetypes.guess_type(str(image_path))[0] or "image/jpeg"
        if provider == "google":
            from google.genai import types

            client = ai.configure_gemini(settings.llm)
            response = client.models.generate_content(
                model=model, contents=[prompt, types.Part.from_bytes(data=data, mime_type=mime)]
            )
            if response.usage_metadata:
                self.tracker.add_usage(
                    response.usage_metadata.prompt_token_count,
                    response.usage_metadata.candidates_token_count,
                )
            return response.text or ""
        if provider in ("openai", "openrouter", "avalai", "openaicompatible"):
            client = self._openai_client(provider)
            is_avalai = provider == "avalai" or "avalai.ir" in str(getattr(client, "base_url", ""))
            data_url = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
            messages = [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}]
            if is_avalai and hasattr(client.chat.completions, "with_raw_response"):
                raw = client.chat.completions.with_raw_response.create(model=model, messages=messages)
                request_id = raw.headers.get("x-request-id")
                if request_id:
                    self.tracker.add_avalai_request(request_id)
                completion = raw.parse()
            else:
                completion = client.chat.completions.create(model=model, messages=messages)
            if completion.usage:
                track_openai_usage(self.tracker, completion.usage)
            return completion.choices[0].message.content or ""
        raise ValueError(f"Provider '{provider}' is not supported for reading images.")

    @staticmethod
    def _retry(call: Callable[[], str], max_retries: int) -> str:
        for attempt in range(max_retries):
            try:
                text = call().strip()
                if text:
                    return text
            except ai.MissingAPIKeyError:
                raise
            except Exception as exc:
                logger.warning(f"LLM call failed (attempt {attempt + 1}/{max_retries}): {exc}")
            time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"LLM returned no text after {max_retries} attempts")

    def generate(self, prompt: str, max_retries: int = 3) -> str:
        return self._retry(lambda: self._once(prompt), max_retries)

    def generate_with_image(self, prompt: str, image_path: Path, max_retries: int = 3) -> str:
        """Ask the (multimodal) model about one image, e.g. to read the text in it."""
        return self._retry(lambda: self._image_once(prompt, image_path), max_retries)
