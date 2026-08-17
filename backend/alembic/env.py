"""Alembic environment.

The application runs ASYNC (asyncpg); Alembic runs SYNC (psycopg2). The sync URL is derived
from `DATABASE_URL` rather than configured twice — two spellings of one connection string is
how a migration ends up applied to the wrong database.

`-x schema=NNN` targets a throwaway schema, so the chain can be replayed against an EMPTY
database without touching a populated one. The sister product learned the hard way that a
mechanism nobody exercises rots: its chain had been unable to reach head for fifty-two
revisions and nothing said so. Here the guard exists from the first migration.
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine, pool, text

from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.models  # noqa: E402,F401  — registers every table on Base.metadata
from app.config import get_settings  # noqa: E402
from app.models.base import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_url() -> str:
    url = get_settings().DATABASE_URL
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _target_schema() -> str | None:
    return context.get_x_argument(as_dictionary=True).get("schema") or None


def _include_name(name, type_, parent_names):
    # `alembic_version` is Alembic's own bookkeeping and belongs in no script.
    return not (type_ == "table" and name == "alembic_version")


def run_migrations_online() -> None:
    schema = _target_schema()
    engine = create_engine(_sync_url(), poolclass=pool.NullPool, future=True)
    with engine.connect() as connection:
        if schema:
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            connection.execute(text(f'SET search_path TO "{schema}"'))
            connection.commit()
        # Revision identifiers here are DESCRIPTIVE and longer than Alembic's default
        # VARCHAR(32). The sister product took three products down in a restart loop over
        # exactly this: a revision applies, fails to write its own name, the transactional
        # DDL rolls back, and the container restarts for ever. Widened before anything runs.
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version ("
                "version_num VARCHAR(128) NOT NULL, "
                "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
            )
        )
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            version_table_schema=schema,
            include_schemas=False,
            include_name=_include_name,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        version_table_schema=_target_schema(),
        include_name=_include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
