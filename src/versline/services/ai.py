from http import client
import os
from loguru import logger
import openai

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
                os.environ['HTTP_PROXY'] = llm_settings.proxy
                os.environ['HTTPS_PROXY'] = llm_settings.proxy
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
        if llm_settings.api_endpoint:
            client = OpenAI(api_key=llm_settings.api_key, base_url=llm_settings.api_endpoint)
            logger.info(f"🔧 Using custom OpenAI endpoint: {llm_settings.api_endpoint}")
        else:
            client = OpenAI(api_key=llm_settings.api_key)
            logger.info("🔧 Using default OpenAI endpoint.")
        if llm_settings.proxy:
            os.environ['HTTP_PROXY'] = llm_settings.proxy
            os.environ['HTTPS_PROXY'] = llm_settings.proxy
        logger.info("✅ OpenAI client configured successfully.")
        return client
    except Exception as e:
        logger.error(f"❌ Error configuring OpenAI client: {e}")
        return None
    
def configure_openrouter(llm_settings):
    """Configure OpenRouter API client with defined settings."""
    try:
        # Assuming openrouter package usage is similar to old project
        # In requirements.txt it was openrouter>=0.1.3
        # If not available, we might need to use OpenAI client with base_url
        from openrouter import OpenRouter
        client = OpenRouter(api_key=llm_settings.api_key)
        logger.info("🔧 Using default OpenRouter endpoint.")
        logger.info("✅ OpenRouter client configured successfully.")
        return client
    except ImportError:
        logger.warning("OpenRouter package not found, trying OpenAI client with OpenRouter base URL")
        from openai import OpenAI
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=llm_settings.api_key,
        )
        return client
    except Exception as e:
        logger.error(f"❌ Error configuring OpenRouter client: {e}")
        return None
