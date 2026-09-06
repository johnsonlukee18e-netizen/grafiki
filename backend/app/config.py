"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- environment -----------------------------------------------------
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"

    # --- database --------------------------------------------------------
    database_url: str = "postgresql+psycopg://nurse:nurse@localhost:5432/nurse"

    # --- session / security ---------------------------------------------
    session_secret: str = "change-me-in-production-please-use-32-bytes-min"
    session_cookie_name: str = "nurse_session"
    session_max_age_seconds: int = 60 * 60 * 8  # 8h
    session_idle_timeout_seconds: int = 60 * 60 * 2  # rolling refresh window
    csrf_cookie_name: str = "nurse_csrf"

    # --- Google OAuth ----------------------------------------------------
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"
    google_discovery_url: str = "https://accounts.google.com/.well-known/openid-configuration"
    google_allowed_domain: str = ""  # optional hd restriction

    # --- frontend --------------------------------------------------------
    frontend_url: str = "http://localhost:5173"
    cors_origins: str = ""  # comma separated; defaults to frontend_url

    # --- bootstrap -------------------------------------------------------
    # Comma separated e-mails that are granted ADMIN on first login.
    initial_admin_emails: str = ""

    # Development-only login shortcut (never honoured when app_env=production).
    dev_auth_enabled: bool = False
    dev_auth_email: str = "dev.admin@example.com"

    # --- solver ----------------------------------------------------------
    solver_time_limit_seconds: int = 60
    solver_seed: int = 42
    solver_workers: int = 8

    # --- rate limiting ---------------------------------------------------
    rate_limit_enabled: bool = True
    rate_limit_default: int = 300  # requests per window per client
    rate_limit_window_seconds: int = 60
    rate_limit_auth: int = 20  # tighter bucket for /api/auth/*

    @field_validator("session_secret")
    @classmethod
    def _secret_len(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SESSION_SECRET must be at least 32 characters")
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cookie_secure(self) -> bool:
        return self.is_production

    @property
    def allowed_origins(self) -> list[str]:
        raw = self.cors_origins or self.frontend_url
        return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]

    @property
    def admin_emails(self) -> set[str]:
        return {e.strip().lower() for e in self.initial_admin_emails.split(",") if e.strip()}

    @property
    def dev_auth_allowed(self) -> bool:
        return self.dev_auth_enabled and not self.is_production

    @property
    def oauth_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
