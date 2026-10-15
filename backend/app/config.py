"""Environment configuration (.env locally, SSM-provided env vars in prod)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"), extra="ignore"
    )

    env: Literal["dev", "prod"] = "dev"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5433/cold_email"

    auth_disabled: bool = False
    allowed_email: str = ""
    supabase_url: str = ""
    supabase_jwt_secret: str = ""

    cors_origins: str = "http://localhost:3000"

    storage_backend: Literal["local", "supabase"] = "local"
    local_storage_dir: Path = BACKEND_DIR / "uploads"

    @model_validator(mode="after")
    def _check(self) -> "Config":
        if self.env == "prod" and self.auth_disabled:
            raise ValueError("AUTH_DISABLED=true is not allowed when ENV=prod")
        if not self.auth_disabled and not self.allowed_email:
            raise ValueError("ALLOWED_EMAIL is required when auth is enabled")
        # Supabase hands out postgres:// URLs; SQLAlchemy needs the psycopg driver named.
        for prefix in ("postgres://", "postgresql://"):
            if self.database_url.startswith(prefix):
                self.database_url = "postgresql+psycopg://" + self.database_url[len(prefix):]
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_config() -> Config:
    return Config()
