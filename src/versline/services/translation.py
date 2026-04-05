import os
import time
from pathlib import Path
from loguru import logger
from versline.config import settings
from versline.services import ai
from versline.core.prompts import load_prompt
from versline.services.pricing import TokenTracker
from versline.services.document_processor import convert_to_markdown

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

    def _read_source_text(self, file_path: str) -> str:
        path = Path(file_path)
        text_extensions = {".txt", ".md", ".markdown", ".csv", ".json", ".xml", ".html", ".htm", ".yaml", ".yml"}
        extension = path.suffix.lower()

        if extension in text_extensions:
            raw = path.read_bytes()
            for encoding in ("utf-8", "utf-8-sig", "cp1256", "cp1252", "latin-1"):
                try:
                    return raw.decode(encoding)
                except UnicodeDecodeError:
                    continue
            raise ValueError(
                "Could not decode text file with supported encodings (utf-8, utf-8-sig, cp1256, cp1252, latin-1)."
            )

        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning(
                f"UTF-8 decode failed for {path}; attempting document text extraction"
            )

            try:
                extracted_text = convert_to_markdown(str(path))
            except Exception as extraction_error:
                raise ValueError(
                    "Could not read file as UTF-8 text and automatic document extraction failed. "
                    f"Please provide a readable text document. Details: {extraction_error}"
                ) from extraction_error

            if not extracted_text or not extracted_text.strip():
                raise ValueError("No readable text could be extracted from the input file.")

            return extracted_text

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
        text = self._read_source_text(file_path)

        if not text.strip():
            raise ValueError("Input file is empty after text extraction.")

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
