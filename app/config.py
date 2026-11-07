from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "HackDesk"
    environment: str = "local"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_fallback_model: str = "gpt-4.1-mini"
    llm_timeout_seconds: float = Field(default=30, gt=0)
    llm_retries: int = Field(default=2, ge=0, le=10)
    llm_input_cost_per_million: float = Field(default=0.15, ge=0)
    llm_output_cost_per_million: float = Field(default=0.60, ge=0)
    llm_fallback_input_cost_per_million: float = Field(default=0.40, ge=0)
    llm_fallback_output_cost_per_million: float = Field(default=1.60, ge=0)
    database_url: str = "sqlite:///./usage.db"

    # Week 3 RAG & Vector store settings
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    rag_top_k: int = 4
    rag_similarity_threshold: float = 0.0
    docs_data_path: str = "data"


@lru_cache
def get_settings() -> Settings:
    return Settings()
