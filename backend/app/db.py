from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import get_config


# Supabase's transaction pooler (Supavisor) listens on 6543.
TRANSACTION_POOLER_PORT = 6543


@lru_cache
def get_engine() -> Engine:
    return make_engine(get_config().database_url)


def make_engine(url: str) -> Engine:
    if make_url(url).port == TRANSACTION_POOLER_PORT:
        # The pooler hands each transaction to any server connection, so keep no
        # connections of our own (Lambda freezes between calls anyway) and turn off
        # psycopg's prepared statements, which don't survive the hand-off.
        return create_engine(url, poolclass=NullPool, connect_args={"prepare_threshold": None})
    return create_engine(url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with get_sessionmaker()() as session:
        yield session
