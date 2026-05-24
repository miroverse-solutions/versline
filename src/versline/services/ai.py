from http import client
import os
import time
import json
from typing import Optional, List, Dict, Any, Tuple
from loguru import logger
import openai
from pydantic import BaseModel

try:
    from .pricing import TokenTracker
except ImportError:
    # Fallback to avoid circular import errors at runtime if pricing also imports ai
    class TokenTracker:
        def __init__(self): 
            self.total_input_tokens = 0
            self.total_output_tokens = 0
            self.total_cost_usd = 0.0
            self.avalai_request_ids = []
        def add_usage(self, i, o, c=0.0): 
            self.total_input_tokens += i
            self.total_output_tokens += o
            self.total_cost_usd += c
        def add_avalai_request(self, r): 
            self.avalai_request_ids.append(r)

class LLMSettings(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    api_endpoint: Optional[str] = None
    proxy: Optional[str] = None

def configure_gemini(llm_settings):
    """Configure Gemini API client with defined settings."""
    try:
        from google import genai
        
        if llm_settings.api_endpoint:
            client = genai.Client(api_key=llm_settings.api_key,  http_options={"base_url": llm_settings.api_endpoint})
            logger.info("✅ Gemini client configured successfully.")
            logger.info(f"🔧 Using custom endpoint: {llm_settings.api_endpoint}")
        else:
            if llm_settings.proxy:
                os.environ["HTTP_PROXY"] = llm_settings.proxy
                os.environ["HTTPS_PROXY"] = llm_settings.proxy
            client = genai.Client(api_key=llm_settings.api_key)
            logger.info("✅ Gemini client configured successfully.")
        return client
    except Exception as e:
        logger.error(f"❌ Error configuring Gemini client: {e}")
        return None


# ---------------------------------------------------------------------------
# Prompt caching helpers
# ---------------------------------------------------------------------------

def create_gemini_context_cache(
    client,
    model: str,
    document_text: str,
    ttl_seconds: int = 3600,
) -> Optional[str]:
    """Upload *document_text* to a Gemini context cache and return the cache name.

    Returns *None* if context caching is unavailable for the model, the document
    is too small, or any other error occurs — callers should fall back gracefully.
    """
    try:
        from google.genai import types

        cache = client.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part(text=document_text)],
                    )
                ],
                ttl=f"{ttl_seconds}s",
            ),
        )
        logger.debug(f"Gemini context cache created: {cache.name}")
        return cache.name
    except Exception as exc:
        logger.debug(f"Gemini context cache creation skipped ({type(exc).__name__}): {exc}")
        return None


def delete_gemini_context_cache(client, cache_name: str) -> None:
    """Delete a Gemini context cache.  Errors are silently ignored."""
    try:
        client.caches.delete(name=cache_name)
        logger.debug(f"Gemini context cache deleted: {cache_name}")
    except Exception as exc:
        logger.debug(f"Failed to delete Gemini cache {cache_name}: {exc}")


def call_gemini_with_cache(
    client,
    model: str,
    cache_name: str,
    prompt: str,
    tracker,
) -> str:
    """Generate text from *prompt* using a pre-created Gemini context cache.

    The cached document content is prepended automatically by the API;
    *prompt* should contain only the new instruction for this call.
    """
    from google.genai import types

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(cached_content=cache_name),
    )
    if response.usage_metadata:
        cached = (
            getattr(response.usage_metadata, "cached_content_token_count", None) or 0
        )
        tracker.add_usage(
            response.usage_metadata.prompt_token_count,
            response.usage_metadata.candidates_token_count,
            cached_tokens=cached,
        )
    return response.text


def call_openai_with_document_prefix(
    client,
    model: str,
    document_text: str,
    instruction: str,
    tracker,
    is_avalai: bool = False,
) -> str:
    """Call an OpenAI-compatible API with the document in the system message.

    Placing the document as a stable system-message prefix enables automatic
    prompt caching on supported models (gpt-4o, etc.) when the total prompt
    exceeds 1 024 tokens — no extra API calls or setup required.

    Cached-token savings are read from ``usage.prompt_tokens_details`` and
    recorded in *tracker*.
    """
    messages = [
        {"role": "system", "content": document_text},
        {"role": "user", "content": instruction},
    ]

    if is_avalai and hasattr(client.chat.completions, "with_raw_response"):
        raw = client.chat.completions.with_raw_response.create(
            model=model,
            messages=messages,
        )
        request_id = raw.headers.get("x-request-id")
        if request_id:
            tracker.add_avalai_request(request_id)
        completion = raw.parse()
    else:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
        )

    if completion.usage:
        cached = (
            getattr(
                getattr(completion.usage, "prompt_tokens_details", None),
                "cached_tokens",
                None,
            )
            or 0
        )
        tracker.add_usage(
            completion.usage.prompt_tokens,
            completion.usage.completion_tokens,
            cached_tokens=cached,
        )
    return completion.choices[0].message.content

def configure_openai(llm_settings):
    """Configure OpenAI API client with defined settings."""
    try:
        from openai import OpenAI
        
        # Configure http client for proxy if needed
        http_client = None
        if llm_settings.proxy:
            import httpx
            http_client = httpx.Client(proxy=llm_settings.proxy)

        if llm_settings.api_endpoint:
            client = OpenAI(
                api_key=llm_settings.api_key, 
                base_url=llm_settings.api_endpoint,
                http_client=http_client
            )
            logger.info(f"🔧 Using custom OpenAI endpoint: {llm_settings.api_endpoint}")
        else:
            client = OpenAI(
                api_key=llm_settings.api_key,
                http_client=http_client
            )
            logger.info("🔧 Using default OpenAI endpoint.")
            
        logger.info("✅ OpenAI client configured successfully.")
        return client
    except Exception as e:
        logger.error(f"❌ Error configuring OpenAI client: {e}")
        return None

class AIClient:
    def __init__(
        self,
        provider: str,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        proxy_url: Optional[str] = None,
    ):
        self.provider = provider.lower() if provider else "openai"
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.proxy_url = proxy_url
        
        # Initialize TokenTracker
        try:
            from .pricing import TokenTracker
            self.tracker = TokenTracker()
        except ImportError:
            self.tracker = TokenTracker() 

        # Configure settings object for helpers
        self.settings = LLMSettings(
            provider=self.provider,
            model=model,
            api_key=api_key,
            api_endpoint=base_url,
            proxy=proxy_url
        )
        
        self.client = self._initialize_client()
        
    def _initialize_client(self):
        if self.provider in ["gemini", "google"]:
            return configure_gemini(self.settings)
        else:
            if self.provider == "avalai" and not self.base_url:
                 self.settings.api_endpoint = "https://api.avalai.ir/v1"
            elif self.provider == "openrouter" and not self.base_url:
                self.settings.api_endpoint = "https://openrouter.ai/api/v1"
            elif self.provider == "custom":
                pass
                
            return configure_openai(self.settings)

    def send_with_retry(
        self, 
        content: str, 
        prompt: str, 
        batch_info: str = "",
        max_retries: int = 3
    ) -> Tuple[List[Dict[str, Any]], float]:
        
        full_prompt = f"{prompt}\n\nContext:\n{content}"
        
        for attempt in range(max_retries):
            try:
                if self.provider in ["gemini", "google"]:
                    return self._send_gemini(full_prompt, batch_info)
                else:
                    return self._send_openai(full_prompt, batch_info)
                    
            except Exception as e:
                logger.warning(f"Error (Attempt {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))
                else:
                    logger.error(f"Failed to process chunk {batch_info}")
                    return [], 0.0
                    
        return [], 0.0

    def _send_openai(self, full_prompt: str, batch_info: str):
        if not self.client:
            raise ValueError("OpenAI Client not initialized")

        messages = [
            {"role": "system", "content": "You are a helpful assistant that generates questions in JSON format."},
            {"role": "user", "content": full_prompt}
        ]

        if self.provider == "avalai" and hasattr(self.client.chat.completions, "with_raw_response"):
            raw = self.client.chat.completions.with_raw_response.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.7
            )
            request_id = raw.headers.get("x-request-id")
            if request_id:
                self.tracker.add_avalai_request(request_id)
            response = raw.parse()
        else:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.7
            )
        
        content = response.choices[0].message.content
        usage = response.usage
        
        if usage:
            self.tracker.add_usage(usage.prompt_tokens, usage.completion_tokens)
        
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                questions = data.get("questions", [])
                if not questions: questions = data.get("flashcards", [])
            elif isinstance(data, list):
                questions = data
            else:
                questions = []
            return questions, 0.0
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON response for {batch_info}")
            return [], 0.0

    def _send_gemini(self, full_prompt: str, batch_info: str):
        if not self.client:
            raise ValueError("Gemini Client not initialized")

        try:
            from google.genai.types import GenerateContentConfig
            response = self.client.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config=GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7
                )
            )
            text = response.text
             # Gemini usage
            if hasattr(response, "usage_metadata"):
                 self.tracker.add_usage(
                     response.usage_metadata.prompt_token_count,
                     response.usage_metadata.candidates_token_count
                 )
            
            data = json.loads(text)
            if isinstance(data, dict):
                 questions = data.get("questions", data.get("flashcards", []))
            elif isinstance(data, list):
                questions = data
            else:
                questions = []
            return questions, 0.0
        except Exception as e:
             logger.error(f"Failed to parse JSON response (Gemini) for {batch_info}: {e}")
             return [], 0.0
