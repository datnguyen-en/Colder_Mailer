from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from app.config import get_config
from app.models import Base

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    # Tests pass their own URL via `config.attributes`; otherwise the app config
    # (MIGRATIONS_DATABASE_URL, for Supabase's session pooler, if set).
    config = get_config()
    return (context.config.attributes.get("database_url")
            or config.migrations_database_url or config.database_url)


def run_migrations_offline() -> None:
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
