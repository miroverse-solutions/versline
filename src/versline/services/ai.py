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
            
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that generates questions in JSON format."},
                {"role": "user", "content": full_prompt}
            ],
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
