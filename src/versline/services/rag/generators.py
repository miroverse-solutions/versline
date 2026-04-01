from __future__ import annotations

from typing import List

from versline.config import settings
from versline.core.prompts import load_prompt
from versline.services import ai
from versline.services.rag.base import BaseGenerator, RetrievedChunk


class PromptRAGGenerator(BaseGenerator):
    def __init__(self, model: str, prompt_file: str = "rag_generate_prompt.md"):
        self.model = model
        self.prompt_template = load_prompt(prompt_file)
        self.provider = settings.llm.provider.lower() if settings.llm.provider else "google"

    def _openai_compatible_client(self):
        if self.provider == "openrouter":
            original_endpoint = settings.llm.api_endpoint
            if not original_endpoint:
                settings.llm.api_endpoint = "https://openrouter.ai/api/v1"
            try:
                return ai.configure_openai(settings.llm)
            finally:
                settings.llm.api_endpoint = original_endpoint
        if self.provider == "avalai":
            original_endpoint = settings.llm.api_endpoint
            settings.llm.api_endpoint = "https://api.avalai.ir/v1"
            try:
                return ai.configure_openai(settings.llm)
            finally:
                settings.llm.api_endpoint = original_endpoint
        return ai.configure_openai(settings.llm)

    def generate(self, query: str, context_chunks: List[RetrievedChunk], **kwargs) -> str:
        context_lines = []
        for index, item in enumerate(context_chunks, start=1):
            source = item.metadata.get("source", "unknown")
            context_lines.append(f"[{index}] source={source} score={item.score:.4f}\n{item.text}")
        context = "\n\n".join(context_lines)

        prompt = self.prompt_template.format(query=query, context=context)

        if self.provider in ["google", "gemini"]:
            client = ai.configure_gemini(settings.llm)
            response = client.models.generate_content(model=self.model, contents=prompt)
            return response.text

        client = self._openai_compatible_client()
        completion = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        return completion.choices[0].message.content or ""
