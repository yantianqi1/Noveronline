"""Alembic environment for the unified backend database."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import Settings
from app.tables import metadata

config = context.config
target_metadata = metadata

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def database_url() -> str:
    """Resolve the target database URL.

    Prefer an explicit ``sqlalchemy.url`` set on the Alembic ``Config``
    (used by programmatic invocations such as ``init_db(..., use_alembic=True)``
    and the Phase D upgrade/downgrade tests) before falling back to
    ``Settings().DATABASE_URL``. This lets callers run migrations against a
    one-off database without mutating process-wide environment variables.
    """
    explicit = config.get_main_option("sqlalchemy.url")
    if explicit and explicit != "sqlite:///./data/mirofish.db":
        return explicit
    return Settings().DATABASE_URL


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
