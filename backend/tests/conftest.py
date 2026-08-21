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

🔴 ITS OWN DATABASE, AND A SCHEMA INSIDE IT. Two levels, and both matter: the DATABASE
separates this product from every other one — a fund's investor register does not share a
backup, a restore or a mis-scoped dump with a property-management tool — and the SCHEMA
separates a test run from the development data inside it.

The suite refuses to start if that database is missing, rather than falling back on
another's. A run that quietly describes the wrong place is worse than a run that does not
happen.

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
import uuid

import psycopg2
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

#: 🔴 THIS PRODUCT HAS ITS OWN DATABASE, and the default says so. It was briefly tested in a
#: schema of a sister product's database, for the only reason that the development role
#: holds no CREATEDB right — a workaround that must never become the arrangement:
#:
#:   * a fund's investor register, its bank movements and another product's tenants would
#:     share a backup, a restore and a mis-scoped dump;
#:   * « isolated by schema » inside somebody else's database is one `search_path` away from
#:     not being isolated at all, and this repository already records a suite that ran
#:     twenty-two green tests against the wrong schema without noticing;
#:   * and an auditor asking « where does the investors' data live » deserves an answer that
#:     is not « in the property-management database ».
#:
#: `INVEST_TEST_DB` overrides it for a machine that genuinely cannot create one — knowingly,
#: and never by default.
_DB_USER = os.getenv("INVEST_TEST_USER", "invest_user")
_DB_PASS = os.getenv("INVEST_TEST_PASSWORD", "devpassword123")
_DB_HOST = os.getenv("INVEST_TEST_HOST", "localhost")
_DB_PORT = int(os.getenv("INVEST_TEST_PORT", "5432"))
_DB_NAME = os.getenv("INVEST_TEST_DB", "lecomptoirinvest")

#: Overridable so parallel runs and CI can each have their own.
TEST_SCHEMA = os.getenv("INVEST_TEST_SCHEMA", "invest_test")

_ASYNC_URL = (
    f"postgresql+asyncpg://{_DB_USER}:{_DB_PASS}@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}"
)
_SYNC_URL = (
    f"postgresql+psycopg2://{_DB_USER}:{_DB_PASS}@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}"
)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _require_database() -> None:
    """Refuse to run against a database that does not exist, and say how to make it.

    A suite that quietly falls back on another product's database is a suite whose results
    describe the wrong place. Failing here costs one command; not failing costs the belief
    that the fund's data is isolated when it is not.
    """
    try:
        psycopg2.connect(
            dbname=_DB_NAME,
            user=_DB_USER,
            password=_DB_PASS,
            host=_DB_HOST,
            port=_DB_PORT,
        ).close()
    except Exception as exc:  # noqa: BLE001
        # ⚠️ EVERY exception, not `psycopg2.OperationalError`. A Postgres server running
        # under a non-English locale answers « la base n'existe pas » in its own encoding,
        # and psycopg2 raises `UnicodeDecodeError` while reading the very message that
        # explains the failure. Catching the narrow type turned a missing database into an
        # INTERNALERROR with a stack trace and no instructions — which is exactly the
        # opposite of what this function exists to produce.
        try:
            detail = str(exc)
        except Exception:  # noqa: BLE001
            detail = ""
        pytest.exit(
            "\n".join(
                [
                    f"La base « {_DB_NAME} » (rôle « {_DB_USER} ») est inaccessible.",
                    "",
                    "Le Comptoir Invest a SA PROPRE base : ni un schéma, ni celle d'un",
                    "autre produit. À créer une fois, avec un rôle qui en a le droit :",
                    "",
                    f"    CREATE ROLE {_DB_USER} LOGIN PASSWORD '...';",
                    f"    CREATE DATABASE {_DB_NAME} OWNER {_DB_USER};",
                    "",
                    f"Détail : {detail or type(exc).__name__}",
                ]
            ),
            returncode=1,
        )


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


def pytest_sessionstart(session) -> None:
    """Checked BEFORE collection, so a missing database gives one message and not one error
    per test. Thirty-two identical errors bury the single line that says what to do."""
    _require_database()


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


@pytest.fixture(autouse=True)
def the_language_never_survives_one_test():
    """🔴 THE LEAK THIS PRODUCT'S OWN GUARD WARNS ABOUT, CAUGHT BY ITS OWN TEST SUITE.

    The reader's language is a `ContextVar`, which is what lets a refusal built deep in a
    pure function know who is reading it. A test that sets it and does not put it back leaves
    every later test reading English - and the first version of
    `test_the_reader_is_refused_in_their_own_language` did exactly that, turning three
    unrelated assertions on French sentences red.

    Resetting here rather than in each test is deliberate: a rule that every author has to
    remember is a rule that one of them will not.
    """
    from app.core import i18n

    with i18n.use_lang(i18n.DEFAULT):
        yield


#: The management company every test runs on behalf of, unless it says otherwise.
#:
#: 🔴 FIXED, AND SHARED BY THE WHOLE SUITE. Rows created by a test are stamped with the
#: firm in force, and queries are filtered by it: a suite where each test invented its own
#: firm would still pass, and would stop proving that the isolation is what makes the
#: neighbour invisible rather than the fixture.
TEST_FIRM = uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture(autouse=True)
def a_firm_is_always_established():
    """🔴 WITHOUT THIS, EVERY TEST SEES NOTHING, and that is the isolation working.

    `core.firm_scope` filters every query on a fund, a project, an investor or a bank
    movement, and its default when no firm is established is a scope matching NO row -- a
    protection whose failure mode leans towards « none » rather than « everything ». A
    suite that created rows outside any firm therefore read back an empty database, which
    is exactly what happened when the isolation landed: 82 tests turned red at once, and
    every one of them was right.

    ⚠️ IT RESTORES ON THE WAY OUT. This product has already paid for a leaked ContextVar
    once, on the reader's language, and the fix was a fixture exactly like this one: a rule
    every author has to remember is a rule one of them will not.
    """
    from app.core import firm_scope

    with firm_scope.use_firm(TEST_FIRM):
        yield
