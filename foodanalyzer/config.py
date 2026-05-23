"""Typed application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AI Food Analyzer"
    log_level: str = "INFO"
    database_url: str = "postgresql://postgres:dev@localhost:5432/foodanalyzer"
    nutrition_cache_ttl_seconds: int = Field(default=86400, ge=1)
    max_image_size_mb: int = Field(default=5, ge=1)
    max_concurrency: int = Field(default=10, ge=1)
    retry_attempts: int = Field(default=3, ge=1)
    http_port: int = Field(default=8000, ge=1, le=65535)
    upload_dir: Path = Path("uploads")
    offline_mode: bool = False

    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-6"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_reasoning_enabled: bool = True
    openrouter_reasoning_exclude: bool = True
    nutrition_provider: str = "usda"
    usda_api_key: str | None = None

    @field_validator("log_level")
    @classmethod
    def uppercase_log_level(cls, value: str) -> str:
        value = value.strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if value not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return value

    @property
    def max_image_bytes(self) -> int:
        return self.max_image_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()