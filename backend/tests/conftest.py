import os
import tempfile

# Configure the app for tests before anything imports it.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5433/cold_email_test"
)
os.environ.update(
    ENV="dev",
    DATABASE_URL=TEST_DATABASE_URL,
    AUTH_DISABLED="true",
    ALLOWED_EMAIL="me@example.com",
    SUPABASE_JWT_SECRET="",
    SUPABASE_URL="",
    STORAGE_BACKEND="local",
    LOCAL_STORAGE_DIR=tempfile.mkdtemp(prefix="cold-email-test-"),
)

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config as AlembicConfig  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _create_database_if_missing(url: str) -> None:
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"),
                             {"n": target.database})
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def migrated_db():
    """Fresh schema built by running the real Alembic migrations."""
    try:
        _create_database_if_missing(TEST_DATABASE_URL)
    except OperationalError as exc:
        pytest.skip(f"Postgres not reachable ({exc.orig}); run `docker compose up -d`")

    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["database_url"] = TEST_DATABASE_URL
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db(migrated_db):
    with migrated_db.begin() as conn:
        conn.execute(text(
            "TRUNCATE companies, domain_aliases, contacts, templates, send_events, settings "
            "RESTART IDENTITY CASCADE"
        ))
    from app.db import get_sessionmaker

    with get_sessionmaker()() as session:
        yield session


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
