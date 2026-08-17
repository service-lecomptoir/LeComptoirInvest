"""Fixtures for the database suite.

🔴 THE TEST SCHEMA IS BUILT BY THE MIGRATIONS, NEVER BY `create_all`. This is the single
most expensive lesson the sister product taught, and it is applied here from the first test
rather than retrofitted.

Le Comptoir Immo built its test schema with `Base.metadata.create_all` plus a hand-written
list of `ALTER TABLE … ADD COLUMN IF NOT EXISTS` replaying, by hand, what its migrations
did. The consequences, measured on 17 August 2026:

  * a thousand-odd lines of conftest whose only job was to imitate the migrations;
  * a hundred and twenty-one migrations, ninety-three of them carrying SQL or data, and NOT
    ONE ever executed by a test — a migration was code with no coverage at all, in the one
    place where a mistake is a container that will not start;
  * and a chain that had been unable to reach head for FIFTY-TWO revisions without anything
    saying so, because nothing ever replayed it.

Building the test schema the way production builds its own costs nothing here and removes
all three. Every migration is exercised on every run; adding a column means writing a
migration, and nothing else.

ISOLATION BY SCHEMA, not by database: creating a database needs a privilege the application
role does not have, and a dedicated schema isolates tables just as well.

⚠️ `search_path` HOLDS THE TEST SCHEMA AND NOTHING ELSE. With `test_suite,public` as a
« safe » fallback, everything resolves against `public` — the sister product ran twenty-two
green tests against ZERO tables in its test schema before noticing. A fallback that silently
reaches the development data is not prudence, it is the absence of isolation wearing its
clothes.
"""

from __future__ import annotations

import os
import subprocess
import sys

import psycopg2
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DB_USER = os.getenv("INVEST_TEST_USER", "lecomptoirimmo_user")
_DB_PASS = os.getenv("INVEST_TEST_PASSWORD", "devpassword123")
_DB_HOST = os.getenv("INVEST_TEST_HOST", "localhost")
_DB_PORT = int(os.getenv("INVEST_TEST_PORT", "5432"))
_DB_NAME = os.getenv("INVEST_TEST_DB", "lecomptoirimmo")

#: Overridable so parallel runs and CI can each have their own.
TEST_SCHEMA = os.getenv("INVEST_TEST_SCHEMA", "invest_test")

_ASYNC_URL = (
    f"postgresql+asyncpg://{_DB_USER}:{_DB_PASS}@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}"
)
_SYNC_URL = (
    f"postgresql+psycopg2://{_DB_USER}:{_DB_PASS}@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}"
)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _drop_schema(name: str) -> None:
    conn = psycopg2.connect(
        dbname=_DB_NAME, user=_DB_USER, password=_DB_PASS, host=_DB_HOST, port=_DB_PORT
    )
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
    finally:
        conn.close()


@pytest.fixture(scope="session", autouse=True)
def migrated_schema() -> str:
    """Build the test schema by REPLAYING the whole chain, exactly as a deployment does.

    Dropped and rebuilt each session rather than kept: a persistent schema is what forces
    the hand-written catch-up lists elsewhere, because `create_all` never alters an existing
    table and a migration never runs twice. Rebuilding costs a second and makes the schema
    unambiguously the migrations' output.
    """
    _drop_schema(TEST_SCHEMA)
    env = {
        **os.environ,
        "DATABASE_URL": _ASYNC_URL,
        # The suite must never depend on a key someone forgot to export; the value is
        # irrelevant as long as it is stable within the run.
        "SECRET_KEY": os.environ.get("SECRET_KEY") or "tests-only-not-a-real-key",
    }
    proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
        [
            sys.executable,
            "-m",
            "alembic",
            "-x",
            f"schema={TEST_SCHEMA}",
            "upgrade",
            "head",
        ],
        cwd=_BACKEND_DIR,
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )
    if proc.returncode != 0:
        pytest.fail(
            "`alembic upgrade head` does not reach head against an EMPTY schema. That is "
            "how a new deployment builds its database, so the suite refuses to run on a "
            "schema production could not obtain.\n"
            f"--- stderr ---\n{proc.stderr[-4000:]}"
        )
    yield TEST_SCHEMA
    _drop_schema(TEST_SCHEMA)


@pytest.fixture(scope="session")
def sync_url() -> str:
    """For the guard that compares the migrated schema to the models."""
    return _SYNC_URL


@pytest_asyncio.fixture
async def db(migrated_schema: str) -> AsyncSession:
    """A session whose writes never survive the test.

    `commit` is replaced by `flush`, so data is visible inside the test and a final rollback
    undoes all of it. The schema stays; the rows do not.
    """
    engine = create_async_engine(
        _ASYNC_URL,
        connect_args={"server_settings": {"search_path": migrated_schema}},
        poolclass=None,
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        original_commit = session.commit
        session.commit = session.flush  # type: ignore[method-assign]
        try:
            yield session
        finally:
            session.commit = original_commit  # type: ignore[method-assign]
            await session.rollback()
            await session.close()
    await engine.dispose()
