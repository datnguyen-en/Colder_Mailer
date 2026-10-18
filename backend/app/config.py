"""Environment configuration (.env locally, SSM-provided env vars in prod).

ENV_FILE picks a different file for one command, e.g. running migrations
against Supabase: `ENV_FILE=../.env.prod uv run alembic upgrade head`.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.environ.get("ENV_FILE") or (REPO_DIR / ".env", BACKEND_DIR / ".env"),
        extra="ignore",
    )

    env: Literal["dev", "prod"] = "dev"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5433/cold_email"
    # Migrations need a session connection; Lambda uses Supabase's transaction pooler.
    migrations_database_url: str = ""

    auth_disabled: bool = False
    allowed_email: str = ""
    supabase_url: str = ""
    supabase_jwt_secret: str = ""

    cors_origins: str = "http://localhost:3000"

    storage_backend: Literal["local", "supabase"] = "local"
    local_storage_dir: Path = BACKEND_DIR / "uploads"
    supabase_secret_key: str = ""  # server-only key for the private resume bucket
    supabase_bucket: str = "resumes"

    # Gmail OAuth (Google Cloud "Web application" client)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/gmail/callback"
    # Where the OAuth callback sends the browser afterwards
    frontend_url: str = "http://localhost:3000"
    # Fernet key that encrypts the stored Gmail refresh token
    token_encryption_key: str = ""

    @model_validator(mode="after")
    def _check(self) -> "Config":
        if self.env == "prod" and self.auth_disabled:
            raise ValueError("AUTH_DISABLED=true is not allowed when ENV=prod")
        if not self.auth_disabled and not self.allowed_email:
            raise ValueError("ALLOWED_EMAIL is required when auth is enabled")
        if self.storage_backend == "supabase" and not (self.supabase_url and self.supabase_secret_key):
            raise ValueError("STORAGE_BACKEND=supabase needs SUPABASE_URL and SUPABASE_SECRET_KEY")
        self.database_url = _with_driver(self.database_url)
        self.migrations_database_url = _with_driver(self.migrations_database_url)
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


def _with_driver(url: str) -> str:
    """Supabase hands out postgres:// URLs; SQLAlchemy needs the psycopg driver named."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


@lru_cache
def get_config() -> Config:
    return Config()
