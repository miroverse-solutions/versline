import os
import time
from pathlib import Path
from loguru import logger
from versline.config import settings
from versline.services import ai
from versline.core.prompts import load_prompt
from versline.services.pricing import TokenTracker

class TextTranslator:
    def __init__(self):
        self.tracker = TokenTracker()
        try:
            self.prompt_template = load_prompt("translation_prompt.md")
        except FileNotFoundError:
            logger.warning("Default translation prompt file not found.")
            self.prompt_template = "{text}" # Fallback


    def split_text(self, text, max_chars=2000):
        """Split text into chunks by paragraphs to fit context window."""
        chunks = []
        current_chunk = []
        current_length = 0
        
        paragraphs = text.split("\n\n")
        
        for para in paragraphs:
            # If a single paragraph is too huge, we might need to split it further (not implemented for simplicity)
            if current_length + len(para) > max_chars:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [para]
                current_length = len(para)
            else:
                current_chunk.append(para)
                current_length += len(para)
        
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
            
        return chunks

    def translate_chunk(self, text, target_language, model_name, max_retries=3):
        prompt = self.prompt_template.format(target_language=target_language, text=text)
        
        for attempt in range(max_retries):
            try:
                provider = settings.llm.provider.lower() if settings.llm.provider else "google"
                logger.debug(f"Translating chunk with {provider} (attempt {attempt+1})")
                
                client = None
                result = None
                
                if provider == "google":
                    client = ai.configure_gemini(settings.llm)
                    # content generation
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt
                    )
                    if response.usage_metadata:
                        self.tracker.add_usage(
                            response.usage_metadata.prompt_token_count,
                            response.usage_metadata.candidates_token_count
                        )
                    result = response.text
                elif provider in ["openai", "openrouter", "avalai", "openaicompatible"]:
                    if provider == "openai":
                        client = ai.configure_openai(settings.llm)
                    elif provider == "openrouter":
                        client = ai.configure_openrouter(settings.llm)
                    elif provider == "avalai":
                        original_endpoint = settings.llm.api_endpoint
                        settings.llm.api_endpoint = "https://api.avalai.ir/v1"
                        try:
                            client = ai.configure_openai(settings.llm)
                        finally:
                            settings.llm.api_endpoint = original_endpoint
                    elif provider == "openaicompatible":
                        client = ai.configure_openai(settings.llm)
                    
                    is_avalai = provider == "avalai" or (hasattr(client, 'base_url') and ("avalai.ir" in str(client.base_url) or "avalapis.ir" in str(client.base_url)))

                    if is_avalai and hasattr(client.chat.completions, 'with_raw_response'):
                        response_raw = client.chat.completions.with_raw_response.create(
                            model=model_name,
                            messages=[{"role": "user", "content": prompt}]
                        )
                        request_id = response_raw.headers.get("x-request-id")
                        if request_id:
                            self.tracker.add_avalai_request(request_id)
                        completion = response_raw.parse()
                    else:
                        completion = client.chat.completions.create(
                            model=model_name,
                            messages=[{"role": "user", "content": prompt}]
                        )

                    if completion.usage:
                        self.tracker.add_usage(
                            completion.usage.prompt_tokens,
                            completion.usage.completion_tokens
                        )

                    result = completion.choices[0].message.content
                else:
                    raise ValueError(f"Provider {provider} not supported for string translation yet.")

                if result:
                    return result
                    
            except Exception as e:
                logger.warning(f"Translation attempt {attempt+1} failed: {e}")
                time.sleep(2)
        
        raise RuntimeError(f"Failed to translate chunk after {max_retries} attempts")

    def process_file(self, file_path: str, target_language="Persian", progress_callback=None, force=False):
        text = Path(file_path).read_text(encoding="utf-8")
        chunks = self.split_text(text)
        
        translated_chunks = []
        total = len(chunks)
        
        if progress_callback:
            progress_callback(0, total, "Starting translation...")
            
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                translated_chunks.append("")
                continue
                
            if progress_callback:
                progress_callback(i, total, f"Translating part {i+1}/{total}...")
                
            translated = self.translate_chunk(chunk, target_language, settings.llm.model)
            translated_chunks.append(translated)
            
            if progress_callback:
                progress_callback(i+1, total, f"Completed part {i+1}")
                
        return "\n\n".join(translated_chunks)
