"""The chain reaches head against an empty schema, and builds exactly what the models say.

WRITTEN ON DAY ONE, AND THAT IS THE WHOLE POINT. The sister product added this guard after
its chain had already been unable to reach head for fifty-two revisions — a migration
guarded itself against a hard-coded schema name, thirteen renames were skipped in silence,
and the failure surfaced half a hundred revisions later in a migration that was correct.

Nothing said so, because nothing ever replayed the chain. Here it is replayed on every run,
starting from a schema with one migration in it, so the day a second one drifts is the day
somebody hears about it.
"""

from __future__ import annotations

import re
import uuid

import psycopg2
import pytest
from sqlalchemy import create_engine, text


def _drop(sync_url: str, name: str) -> None:
    engine = create_engine(sync_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as c:
            c.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))
    finally:
        engine.dispose()


def _columns(sync_url: str, schema: str) -> dict[tuple[str, str], tuple[str, str]]:
    engine = create_engine(sync_url)
    try:
        with engine.connect() as c:
            rows = c.execute(
                text(
                    "SELECT table_name, column_name, data_type, is_nullable "
                    "FROM information_schema.columns WHERE table_schema = :s"
                ),
                {"s": schema},
            ).all()
    finally:
        engine.dispose()
    return {(t, col): (typ, nul) for t, col, typ, nul in rows if t != "alembic_version"}


def _unique_rules(sync_url: str, schema: str) -> dict[str, set[tuple[str, str | None]]]:
    """Uniqueness by what it CONSTRAINS, never by the index's name.

    Both forms are read together — a UNIQUE constraint and a unique index — because the two
    sides spell the same rule differently: `create_all` emits a constraint where a migration
    emits an index. Reading only `table_constraints` is how the sister product's suite once
    reported that production allowed duplicate rows it had never allowed.
    """
    engine = create_engine(sync_url)
    out: dict[str, set[tuple[str, str | None]]] = {}
    try:
        with engine.connect() as c:
            rows = c.execute(
                text(
                    "SELECT tablename, indexdef FROM pg_indexes "
                    "WHERE schemaname = :s AND indexdef LIKE 'CREATE UNIQUE%'"
                ),
                {"s": schema},
            ).all()
    finally:
        engine.dispose()
    for table, definition in rows:
        if table == "alembic_version":
            continue
        cols = re.search(r"\(([^)]*)\)", definition.split(" USING ")[1]).group(1)
        cols = ",".join(sorted(part.strip() for part in cols.split(",")))
        where = re.search(r"WHERE (.+)$", definition)
        out.setdefault(table, set()).add(
            (cols, where.group(1).strip() if where else None)
        )
    return out


@pytest.fixture(scope="module")
def model_schema(sync_url: str) -> str:
    """A schema built by `create_all`, to compare the migrations against."""
    import app.models  # noqa: F401
    from app.models.base import Base

    name = f"invest_models_{uuid.uuid4().hex[:8]}"
    conn = psycopg2.connect(sync_url.replace("postgresql+psycopg2://", "postgresql://"))
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{name}"')
    finally:
        conn.close()
    engine = create_engine(sync_url, connect_args={"options": f"-csearch_path={name}"})
    try:
        with engine.begin() as c:
            Base.metadata.create_all(bind=c)
    finally:
        engine.dispose()
    yield name
    _drop(sync_url, name)


def test_the_chain_reached_head_and_stamped_itself(
    sync_url: str, migrated_schema: str
) -> None:
    engine = create_engine(sync_url)
    try:
        with engine.connect() as c:
            c.execute(text(f'SET search_path TO "{migrated_schema}"'))
            revision = c.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
    finally:
        engine.dispose()
    assert revision, "The chain ran but stamped no revision."


def test_every_model_column_exists_in_the_migrated_schema(
    sync_url: str, migrated_schema: str
) -> None:
    """Both directions. A column the models declare and the migrations never create breaks
    production; one the migrations create and no model knows is dead weight the next reader
    will take for meaningful."""
    import app.models  # noqa: F401
    from app.models.base import Base

    declared = {
        (table.name, col.name)
        for table in Base.metadata.sorted_tables
        for col in table.columns
    }
    actual = set(_columns(sync_url, migrated_schema))
    assert not (declared - actual), (
        f"Missing from the migrated schema: {sorted(declared - actual)}"
    )
    assert not (actual - declared), (
        f"In the schema and in no model: {sorted(actual - declared)}"
    )


def test_no_type_or_nullability_diverges(
    sync_url: str, migrated_schema: str, model_schema: str
) -> None:
    """No frozen list of tolerated differences, and there must never be one.

    The sister product needed one because thirty-four divergences had already accumulated
    before anybody compared. Here the comparison exists before the second migration, so any
    difference is one that appeared today and can be fixed today.
    """
    migrated, modelled = (
        _columns(sync_url, migrated_schema),
        _columns(sync_url, model_schema),
    )
    divergent = {k for k in set(migrated) & set(modelled) if migrated[k] != modelled[k]}
    assert not divergent, (
        "A column's type or nullability differs between the schema the MIGRATIONS build "
        "(production's) and the one the MODELS build. The suite would pass on a type "
        "production does not have.\n  "
        + "\n  ".join(
            f"{t}.{c}: migrated={migrated[(t, c)]} models={modelled[(t, c)]}"
            for t, c in sorted(divergent)
        )
    )


def test_uniqueness_is_enforced_on_both_sides(
    sync_url: str, migrated_schema: str, model_schema: str
) -> None:
    """A rule production enforces and the tests do not is a suite that green-lights the
    exact write production will refuse — and the reverse hides a rule that does not exist."""
    migrated, modelled = (
        _unique_rules(sync_url, migrated_schema),
        _unique_rules(sync_url, model_schema),
    )
    gaps = {}
    for table in sorted(set(migrated) | set(modelled)):
        only_migrated = migrated.get(table, set()) - modelled.get(table, set())
        only_modelled = modelled.get(table, set()) - migrated.get(table, set())
        if only_migrated or only_modelled:
            gaps[table] = (sorted(only_migrated), sorted(only_modelled))
    assert not gaps, f"Uniqueness known to only one side: {gaps}"
