import json
from typing import Any, Dict, Optional
from pathlib import Path
import os
import warnings
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

from versline.userconfig import user_env_path


ENV_FILE_ENV_VAR = "VERSLINE_ENV_FILE"

class TranscriptionSettings(BaseSettings):
    timestamp_model: str = Field(
        default="gpt-4o-mini-transcribe",
        description="Cheap/fast model for timestamp chunk transcription (must support audio input)",
    )
    timestamp_chunk_minutes: int = Field(
        default=3,
        description="Chunk duration in minutes for timestamped mode",
    )
    timestamp_prompt_file: str = Field(
        default="timestamp_chunk_prompt.md",
        description="Prompt file used for timestamp chunk transcription",
    )
    timestamp_timeout_seconds: int = Field(
        default=120,
        validation_alias=AliasChoices(
            "VERSLINE_TRANSCRIPTION_TIMESTAMP_TIMEOUT_SECONDS",
            "VERSLINE_TRANSCRIPTION_STT_TIMEOUT_SECONDS",
            "timestamp_timeout_seconds",
        ),
        description="HTTP timeout in seconds for /audio/transcriptions STT requests",
    )
    timestamp_provider: Optional[str] = Field(
        default=None,
        description="STT provider (OpenAI, AvalAI, OpenRouter, OpenAICompatible). Falls back to the LLM provider settings when empty",
    )
    timestamp_api_key: Optional[str] = Field(
        default=None,
        description="API key for the STT endpoint. Falls back to the LLM API key when empty",
    )
    timestamp_api_endpoint: Optional[str] = Field(
        default=None,
        description="Base URL of the STT endpoint (without /audio/transcriptions). Falls back to the provider default or LLM endpoint",
    )
    timestamp_proxy: Optional[str] = Field(
        default=None,
        description="Proxy URL for STT requests. Falls back to the LLM proxy when empty",
    )
    timestamp_language: Optional[str] = Field(
        default="fa",
        description="Language code sent to the STT endpoint (e.g. fa, en). Empty means auto-detect",
    )

    model_config = SettingsConfigDict(env_prefix='VERSLINE_TRANSCRIPTION_', env_file='.env', extra='ignore')


class LLMSettings(BaseSettings):
    provider: str = Field(default="Google", description="LLM Provider (Google, OpenAI, OpenRouter, AvalAI, OpenAICompatible)")
    api_key: Optional[str] = Field(default=None, description="API Key for LLM")
    model: str = Field(default="gemini-2.0-flash", description="LLM Model")
    api_endpoint: Optional[str] = Field(default=None, description="Custom API Endpoint")
    proxy: Optional[str] = Field(default=None, description="Proxy URL")
    avalai_provider: Optional[str] = Field(
        default=None,
        description="Optional AvalAI upstream provider hint (e.g. google, openai, anthropic)",
    )

    extra_body: Optional[Dict[str, Any]] = Field(
        default=None,
        description='Extra JSON merged into every OpenAI-compatible request body (e.g. {"reasoning": {"max_tokens": 1500}})',
    )

    model_config = SettingsConfigDict(env_prefix='VERSLINE_LLM_', env_file='.env', extra='ignore')

class FFmpegSettings(BaseSettings):
    ffmpeg_path: Optional[str] = Field(default=None, description="Path to FFmpeg executable")
    ffprobe_path: Optional[str] = Field(default=None, description="Path to FFprobe executable")
    
    model_config = SettingsConfigDict(env_prefix='VERSLINE_FFMPEG_', env_file='.env', extra='ignore')


class ResourceSettings(BaseSettings):
    max_ram_mb: int = Field(default=0, description="Maximum RAM usage in MB (0 = unlimited)")
    max_cpu_cores: int = Field(default=0, description="Maximum CPU cores/threads to use (0 = unlimited)")
    max_gpu_vram_fraction: float = Field(default=0.0, description="Maximum GPU VRAM fraction per device (0.0 = unlimited, e.g. 0.8 = 80%)")

    model_config = SettingsConfigDict(env_prefix='VERSLINE_RESOURCE_', env_file='.env', extra='ignore')


class SlidesSettings(BaseSettings):
    npm_registry: Optional[str] = Field(
        default=None,
        description="Custom npm registry URL used during slide deck build (e.g. https://registry.npmmirror.com)",
    )

    model_config = SettingsConfigDict(env_prefix='VERSLINE_SLIDES_', env_file='.env', extra='ignore')


class TelegramSettings(BaseSettings):
    api_id: Optional[int] = Field(default=None, description="Telegram API id from https://my.telegram.org")
    api_hash: Optional[str] = Field(default=None, description="Telegram API hash from https://my.telegram.org")
    session_path: Optional[str] = Field(default=None, description="Telethon session file (defaults to the per-user config dir)")
    proxy: Optional[str] = Field(default=None, description="Proxy URL for Telegram (socks5://host:port or http://host:port). Falls back to the LLM proxy")

    model_config = SettingsConfigDict(env_prefix='VERSLINE_TELEGRAM_', env_file='.env', extra='ignore')


class Settings(BaseSettings):
    llm: LLMSettings = Field(default_factory=LLMSettings)
    transcription: TranscriptionSettings = Field(default_factory=TranscriptionSettings)
    ffmpeg: FFmpegSettings = Field(default_factory=FFmpegSettings)
    resource: ResourceSettings = Field(default_factory=ResourceSettings)
    slides: SlidesSettings = Field(default_factory=SlidesSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)

    # Common settings
    output_directory: Path = Field(default=Path("output"), description="Default output directory")
    temp_directory: Path = Field(default=Path("temp"), description="Temporary directory")
    
    model_config = SettingsConfigDict(env_prefix='VERSLINE_', env_file='.env', extra='ignore')


def _resolve_env_file_path(env_file: Optional[Path]) -> Optional[Path]:
    if env_file is not None:
        return Path(env_file).expanduser()

    env_file_value = os.getenv(ENV_FILE_ENV_VAR)
    if not env_file_value:
        return None
    return Path(env_file_value).expanduser()


def _load_env_file(env_path: Path, *, override: bool, raise_if_missing: bool) -> None:
    if not env_path.exists() or not env_path.is_file():
        if raise_if_missing:
            raise FileNotFoundError(f"Env file not found: {env_path}")
        warnings.warn(f"Env file from {ENV_FILE_ENV_VAR} not found: {env_path}", stacklevel=2)
        return
    load_dotenv(dotenv_path=env_path, override=override)


def _load_default_env_files() -> None:
    """Lowest-precedence sources: the working-directory .env, then the per-user config.env."""
    load_dotenv(dotenv_path=Path(".env"), override=False)
    user_env = user_env_path()
    if user_env.is_file():
        load_dotenv(dotenv_path=user_env, override=False)


_bootstrap_env_path = _resolve_env_file_path(None)
if _bootstrap_env_path is not None:
    _load_env_file(_bootstrap_env_path, override=False, raise_if_missing=False)
_load_default_env_files()


# Global settings instance
settings = Settings()


def reload_settings(env_file: Optional[Path] = None, *, override_env: bool = True) -> Settings:
    env_path = _resolve_env_file_path(env_file)
    if env_path is not None:
        effective_override = override_env if env_file is not None else False
        _load_env_file(env_path, override=effective_override, raise_if_missing=True)

    refreshed_settings = Settings()
    settings.llm = refreshed_settings.llm
    settings.transcription = refreshed_settings.transcription
    settings.ffmpeg = refreshed_settings.ffmpeg
    settings.resource = refreshed_settings.resource
    settings.slides = refreshed_settings.slides
    settings.telegram = refreshed_settings.telegram
    settings.output_directory = refreshed_settings.output_directory
    settings.temp_directory = refreshed_settings.temp_directory
    return settings




def parse_extra_body(raw: str) -> Dict[str, Any]:
    """Parse the --extra-body CLI value into a JSON object."""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--extra-body must be valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("--extra-body must be a JSON object, e.g. '{\"reasoning\": {\"max_tokens\": 1500}}'")
    return value
