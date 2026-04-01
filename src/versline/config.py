from typing import Optional, List
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class LLMSettings(BaseSettings):
    provider: str = Field(default="Google", description="LLM Provider (Google, OpenAI, OpenRouter, AvalAI, OpenAICompatible)")
    api_key: Optional[str] = Field(default=None, description="API Key for LLM")
    model: str = Field(default="gemini-2.0-flash", description="LLM Model")
    api_endpoint: Optional[str] = Field(default=None, description="Custom API Endpoint")
    proxy: Optional[str] = Field(default=None, description="Proxy URL")

    model_config = SettingsConfigDict(env_prefix='VERSLINE_LLM_', env_file='.env', extra='ignore')

class FFmpegSettings(BaseSettings):
    ffmpeg_path: Optional[str] = Field(default=None, description="Path to FFmpeg executable")
    ffprobe_path: Optional[str] = Field(default=None, description="Path to FFprobe executable")
    
    model_config = SettingsConfigDict(env_prefix='VERSLINE_FFMPEG_', env_file='.env', extra='ignore')


class RAGSettings(BaseSettings):
    vector_backend: str = Field(default="qdrant", description="Vector backend type")
    collection_name: str = Field(default="versline_docs", description="Default vector collection")
    qdrant_url: str = Field(default="http://localhost:6333", description="Qdrant URL")
    qdrant_api_key: Optional[str] = Field(default=None, description="Qdrant API key")
    qdrant_distance: str = Field(default="cosine", description="Vector distance metric")
    embedding_model: str = Field(default="text-embedding-3-small", description="Embedding model")
    chunk_size: int = Field(default=1200, description="Chunk size in characters")
    chunk_overlap: int = Field(default=200, description="Chunk overlap in characters")
    generation_prompt_file: str = Field(default="rag_generate_prompt.md", description="Prompt file used for RAG generation")

    model_config = SettingsConfigDict(env_prefix='VERSLINE_RAG_', env_file='.env', extra='ignore')

class Settings(BaseSettings):
    llm: LLMSettings = Field(default_factory=LLMSettings)
    ffmpeg: FFmpegSettings = Field(default_factory=FFmpegSettings)
    rag: RAGSettings = Field(default_factory=RAGSettings)
    
    # Common settings
    output_directory: Path = Field(default=Path("output"), description="Default output directory")
    temp_directory: Path = Field(default=Path("temp"), description="Temporary directory")
    
    model_config = SettingsConfigDict(env_prefix='VERSLINE_', env_file='.env', extra='ignore')

# Global settings instance
settings = Settings()
