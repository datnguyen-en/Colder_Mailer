import pytest
from pydantic import ValidationError
from sqlalchemy.pool import NullPool

from app import db
from app.config import Config
from app.db import make_engine

POOLER = "postgresql://postgres.abc:pw@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
SESSION = "postgres://postgres.abc:pw@aws-0-us-east-1.pooler.supabase.com:5432/postgres"


def config(**kw):
    return Config(_env_file=None, auth_disabled=True, **kw)


def test_supabase_urls_get_the_psycopg_driver():
    c = config(database_url=POOLER, migrations_database_url=SESSION)
    assert c.database_url.startswith("postgresql+psycopg://postgres.abc:pw@")
    assert c.migrations_database_url.startswith("postgresql+psycopg://")


def test_transaction_pooler_gets_no_pool_and_no_prepared_statements(monkeypatch):
    captured = {}
    monkeypatch.setattr(db, "create_engine", lambda url, **kw: captured.update(kw))
    make_engine(config(database_url=POOLER).database_url)
    assert captured == {"poolclass": NullPool, "connect_args": {"prepare_threshold": None}}


def test_regular_database_keeps_a_pool():
    engine = make_engine("postgresql+psycopg://u:p@localhost:5433/db")
    assert not isinstance(engine.pool, NullPool)


def test_supabase_storage_needs_url_and_key():
    with pytest.raises(ValidationError, match="SUPABASE_SECRET_KEY"):
        config(storage_backend="supabase", supabase_url="https://x.supabase.co")
    config(storage_backend="supabase", supabase_url="https://x.supabase.co", supabase_secret_key="sb_secret_x")


def test_prod_refuses_the_auth_bypass():
    with pytest.raises(ValidationError, match="AUTH_DISABLED"):
        config(env="prod")
