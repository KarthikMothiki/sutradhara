"""Multi-Agent Task Management System — Configuration."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Gemini / Google AI ──────────────────────────────────────
    google_api_key: str = ""
    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"
    google_cloud_bucket: str = ""

    # ── Demo Mode ────────────────────────────────────────────────
    # When True, all MCP calls return seed data instead of hitting live APIs.
    #
    # Auto-detection logic:
    #   • Cloud Run always sets the K_SERVICE env var → default to Demo Mode
    #     so judges see safe pre-seeded data on the public URL.
    #   • Localhost never has K_SERVICE → default to the DEMO_MODE env var
    #     (set to "false" in .env) so your real calendar & Notion are used.
    demo_mode: bool = bool(
        os.getenv("K_SERVICE")  # Cloud Run auto-inject → Demo Mode ON
        if os.getenv("K_SERVICE")
        else os.getenv("DEMO_MODE", "false").lower() in ("true", "1")
    )

    # Runtime overrides (stateless, passed per-request)
    runtime_notion_token: Optional[str] = None
    runtime_notion_db_id: Optional[str] = None

    # ── Model Fallback Chain ────────────────────────────────────
    # Comma-separated list: tries each model in order until one works
    # gemini-2.5-flash for Manager; gemini-2.0-flash-lite for Planner/Focus
    model_fallback_chain: str = (
        "gemini-2.5-flash,gemini-2.0-flash,gemini-2.0-flash-lite"
    )


    # ── Google Calendar ─────────────────────────────────────────
    google_calendar_credentials_path: str = "./credentials.json"
    google_calendar_token_path: str = "./token.json"

    # ── Notion ──────────────────────────────────────────────────
    notion_token: str = ""
    notion_database_id: str = ""

    # ── Database ────────────────────────────────────────────────
    # For Cloud SQL: postgresql+asyncpg://user:password@/dbname?host=/cloudsql/project:region:instance
    # Local fallback: sqlite+aiosqlite:///./sutradhara.db
    database_url: str = os.getenv(
        "DATABASE_URL", "sqlite+aiosqlite:///./sutradhara.db"
    )
    cloud_sql_connection_name: str = os.getenv("CLOUD_SQL_CONNECTION_NAME", "")

    # ── Server ──────────────────────────────────────────────────
    port: int = 8080
    host: str = "0.0.0.0"
    log_level: str = "info"

    # ── Scheduler (Tier 3) ──────────────────────────────────────
    scheduler_enabled: bool = True
    daily_briefing_time: str = "08:00"
    weekly_review_day: str = "friday"
    weekly_review_time: str = "18:00"

    # ── Derived Properties ──────────────────────────────────────
    @property
    def model_chain(self) -> list[str]:
        """Parse the model fallback chain into a list."""
        return [m.strip() for m in self.model_fallback_chain.split(",") if m.strip()]

    @property
    def primary_model(self) -> str:
        """The primary (first) model in the fallback chain."""
        chain = self.model_chain
        return chain[0] if chain else "gemini-2.5-flash"

    @property
    def use_vertex_ai(self) -> bool:
        """Whether Vertex AI is configured as a fallback."""
        return bool(self.google_cloud_project)


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton for application settings."""
    return Settings()
