from __future__ import annotations

from typing import List, Optional

import httpx
from openai import OpenAI

from versline.config import settings
from versline.core.prompts import load_prompt
from versline.services import ai
from versline.services.pricing import TokenTracker
from versline.services.rag.base import BaseGenerator, RetrievedChunk
from versline.services.rag.runtime import (
    RateLimiter,
    TokenRateLimiter,
    estimate_tokens_from_text,
    retry_call,
    scoped_proxy,
)


class PromptRAGGenerator(BaseGenerator):
    def __init__(
        self,
        model: str,
        prompt_file: str = "rag_generate_prompt.md",
        provider: Optional[str] = None,
        proxy: Optional[str] = None,
        rate_limiter: Optional[RateLimiter] = None,
        token_rate_limiter: Optional[TokenRateLimiter] = None,
        tracker: Optional[TokenTracker] = None,
    ):
        self.model = model
        self.prompt_template = load_prompt(prompt_file)
        self.provider = (provider or settings.llm.provider or "google").lower()
        self.proxy = proxy if proxy is not None else settings.rag.generation_proxy
        self.rate_limiter = rate_limiter or RateLimiter(settings.rag.rate_limit_generation_rpm)
        self.token_rate_limiter = token_rate_limiter or TokenRateLimiter(settings.rag.rate_limit_generation_tpm)
        self.tracker = tracker

    def _openai_compatible_client(self):
        resolved_endpoint = settings.llm.api_endpoint
        if self.provider == "openrouter":
            resolved_endpoint = resolved_endpoint or "https://openrouter.ai/api/v1"
        elif self.provider == "avalai":
            resolved_endpoint = resolved_endpoint or "https://api.avalai.ir/v1"

        http_client = httpx.Client(proxy=self.proxy) if self.proxy else None
        return OpenAI(
            api_key=settings.llm.api_key,
            base_url=resolved_endpoint,
            http_client=http_client,
        )

    def _is_avalai(self, client: OpenAI) -> bool:
        if self.provider == "avalai":
            return True
        base_url = getattr(client, "base_url", None)
        return bool(base_url and ("avalai.ir" in str(base_url) or "avalapis.ir" in str(base_url)))

    def generate(self, query: str, context_chunks: List[RetrievedChunk], **kwargs) -> str:
        context_lines = []
        for index, item in enumerate(context_chunks, start=1):
            source = item.metadata.get("source", "unknown")
            context_lines.append(f"[{index}] source={source} score={item.score:.4f}\n{item.text}")
        context = "\n\n".join(context_lines)

        external_context = kwargs.get("external_context")
        if isinstance(external_context, str) and external_context.strip():
            context = (
                f"{context}\n\n"
                "[External Context]\n"
                f"{external_context.strip()}"
            )

        prompt = self.prompt_template.format(query=query, context=context)

        self.rate_limiter.wait()
        reservation_id = self.token_rate_limiter.reserve(estimate_tokens_from_text(prompt))

        def operation() -> str:
            if self.provider in ["google", "gemini"]:
                with scoped_proxy(self.proxy):
                    client = ai.configure_gemini(settings.llm)
                    response = client.models.generate_content(model=self.model, contents=prompt)
                if self.tracker and getattr(response, "usage_metadata", None):
                    prompt_count = int(getattr(response.usage_metadata, "prompt_token_count", 0) or 0)
                    candidate_count = int(getattr(response.usage_metadata, "candidates_token_count", 0) or 0)
                    self.tracker.add_usage(
                        prompt_count,
                        candidate_count,
                    )
                    self.token_rate_limiter.finalize(
                        reservation_id,
                        actual_tokens=prompt_count + candidate_count,
                        mode=settings.rag.token_limit_mode,
                    )
                return response.text

            with scoped_proxy(self.proxy):
                client = self._openai_compatible_client()
                is_avalai = self._is_avalai(client)
                if is_avalai and hasattr(client.chat.completions, "with_raw_response"):
                    response_raw = client.chat.completions.with_raw_response.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    request_id = response_raw.headers.get("x-request-id")
                    if self.tracker and request_id:
                        self.tracker.add_avalai_request(request_id)
                    completion = response_raw.parse()
                else:
                    completion = client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                    )
            if self.tracker and completion.usage:
                prompt_tokens = int(completion.usage.prompt_tokens or 0)
                completion_tokens = int(completion.usage.completion_tokens or 0)
                self.tracker.add_usage(
                    prompt_tokens,
                    completion_tokens,
                )
                self.token_rate_limiter.finalize(
                    reservation_id,
                    actual_tokens=prompt_tokens + completion_tokens,
                    mode=settings.rag.token_limit_mode,
                )
            return completion.choices[0].message.content or ""

        return retry_call(
            operation,
            max_retries=settings.rag.retry_max_retries,
            base_delay_seconds=settings.rag.retry_base_delay_seconds,
            max_delay_seconds=settings.rag.retry_max_delay_seconds,
            operation_name="generation_request",
        )
