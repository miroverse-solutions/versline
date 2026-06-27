from typing import Optional
from pathlib import Path
import os
import warnings
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv


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
    stt_timeout_seconds: int = Field(
        default=120,
        description="HTTP timeout in seconds for /audio/transcriptions STT requests",
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


class Settings(BaseSettings):
    llm: LLMSettings = Field(default_factory=LLMSettings)
    transcription: TranscriptionSettings = Field(default_factory=TranscriptionSettings)
    ffmpeg: FFmpegSettings = Field(default_factory=FFmpegSettings)
    resource: ResourceSettings = Field(default_factory=ResourceSettings)
    slides: SlidesSettings = Field(default_factory=SlidesSettings)

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


_bootstrap_env_path = _resolve_env_file_path(None)
if _bootstrap_env_path is not None:
    _load_env_file(_bootstrap_env_path, override=False, raise_if_missing=False)


# Global settings instance
settings = Settings()


def reload_settings(env_file: Optional[Path] = None, *, override_env: bool = True) -> Settings:
    env_path = _resolve_env_file_path(env_file)
    if env_path is not None:
        effective_override = override_env if env_file is not None else False
        _load_env_file(env_path, override=effective_override, raise_if_missing=True)

    refreshed_settings = Settings()
    settings.llm = refreshed_settings.llm
    settings.ffmpeg = refreshed_settings.ffmpeg
    settings.resource = refreshed_settings.resource
    settings.slides = refreshed_settings.slides
    settings.output_directory = refreshed_settings.output_directory
    settings.temp_directory = refreshed_settings.temp_directory
    return settings


