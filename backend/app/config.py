"""
Application configuration via environment variables.
All settings can be overridden by a .env file in the backend/ directory.
"""

from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key. Leave empty to use template-based fallback.",
    )
    llm_model: str = Field(
        default="claude-3-haiku-20240307",
        description="Anthropic model ID for intent classification + narrative generation.",
    )
    llm_max_tokens: int = Field(default=1024)
    llm_temperature: float = Field(default=0.1)

    # Database
    database_path: str = Field(
        default="data/olap.duckdb",
        description="Path to DuckDB file (relative to backend/ directory).",
    )

    # API
    cors_origins: List[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000", "http://localhost:80"],
        description="Allowed CORS origins.",
    )

    # Session management
    session_ttl_minutes: int = Field(
        default=30,
        description="Session expiry after this many minutes of inactivity.",
    )
    max_session_turns: int = Field(
        default=10,
        description="Max conversation turns stored per session.",
    )

    # Drill-through pagination
    drill_through_page_size: int = Field(
        default=20,
        description="Default page size for drill-through raw row queries.",
    )

    log_level: str = Field(default="INFO")
    app_version: str = Field(default="1.0.0")


settings = Settings()
