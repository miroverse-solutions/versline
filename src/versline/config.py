from typing import Optional, List
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class LLMSettings(BaseSettings):
    provider: str = Field(default="Google", description="LLM Provider")
    api_key: Optional[str] = Field(default=None, description="API Key for LLM")
    model: str = Field(default="gemini-2.0-flash", description="LLM Model")
    api_endpoint: Optional[str] = Field(default=None, description="Custom API Endpoint")
    proxy: Optional[str] = Field(default=None, description="Proxy URL")

    model_config = SettingsConfigDict(env_prefix='VERSLINE_LLM_', env_file='.env', extra='ignore')

class FFmpegSettings(BaseSettings):
    ffmpeg_path: Optional[str] = Field(default=None, description="Path to FFmpeg executable")
    ffprobe_path: Optional[str] = Field(default=None, description="Path to FFprobe executable")
    
    model_config = SettingsConfigDict(env_prefix='VERSLINE_FFMPEG_', env_file='.env', extra='ignore')

class Settings(BaseSettings):
    llm: LLMSettings = Field(default_factory=LLMSettings)
    ffmpeg: FFmpegSettings = Field(default_factory=FFmpegSettings)
    
    # Common settings
    output_directory: Path = Field(default=Path("output"), description="Default output directory")
    temp_directory: Path = Field(default=Path("temp"), description="Temporary directory")
    
    model_config = SettingsConfigDict(env_prefix='VERSLINE_', env_file='.env', extra='ignore')

# Global settings instance
settings = Settings()
