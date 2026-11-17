"""The list of scoped tables, the columns that exist, and the filter actually installed.

🔴 THREE THINGS THAT MUST AGREE, AND NOTHING MAKES THEM AGREE BY ITSELF.

`SCOPED_TABLES` is prose. The `firm_id` columns are schema. The tuple handed to
`install()` is what SQLAlchemy really filters. A new table given a `firm_id` and forgotten
in the install call would be a table nobody filters: every firm would read it, and the
screen showing it would look exactly right. That is this repository's most expensive
defect written down twice already -- a rule stated in one place and applied in another.

⚠️ AND THE OPPOSITE FAILS LOUDER BUT STILL DESERVES A GUARD: a table named in the tuple
without the column raises on the first query touching it.

⚠️ `users` IS DELIBERATELY OUT. It carries `firm_id` too, and it means something ELSE
there: NULL is « this account IS the firm ». Filtering the account table by the firm in
force would make signing in impossible before a firm is established.
"""

from __future__ import annotations

import app.models  # noqa: F401  (imports every model, and installs the scope)
from app.core.firm_scope import (
    DERIVED_TABLES,
    SCOPED_TABLES,
    installed_derived_tables,
    installed_tables,
)
from app.models.base import Base

#: The account table carries the column but is scoped by nobody. See the module docstring.
NOT_A_ROOT = {"users"}


def _tables_with_a_firm_column() -> set[str]:
    return {
        table.name
        for table in Base.metadata.tables.values()
        if "firm_id" in table.columns
    }


def test_every_table_carrying_a_firm_is_a_declared_root():
    carried = _tables_with_a_firm_column() - NOT_A_ROOT
    assert carried == set(SCOPED_TABLES), (
        "a table carries firm_id without being scoped, or the other way round: "
        f"columns={sorted(carried)} declared={sorted(SCOPED_TABLES)}"
    )


def test_the_filter_is_installed_on_exactly_the_declared_roots():
    assert set(installed_tables()) == set(SCOPED_TABLES), (
        "the scope installed at import does not match the declared roots: "
        f"installed={list(installed_tables())} declared={sorted(SCOPED_TABLES)}"
    )


#: The tables that hold no firm's data: accounts and what hangs on an account, the journal
#: (read by the console across firms), and the record of a deletion.
NOT_FIRM_DATA = {
    "users",
    "revoked_sessions",
    "user_two_factors",
    "audit_logs",
    "account_deletions",
}


def test_every_other_table_reaches_a_firm_or_is_named_as_holding_none():
    """🔴 A TABLE THAT IS NEITHER A ROOT NOR DERIVED IS READ BY EVERY FIRM.

    Until 17 Nov 2026 the ten tables below the roots were filtered by nobody, on the
    belief that « the rest derives it by join »: a direct `select(Distribution)` names no
    root, and listed every firm's distributions. A new table must say which it is."""
    every = set(Base.metadata.tables)
    classified = set(SCOPED_TABLES) | set(DERIVED_TABLES) | NOT_FIRM_DATA
    assert every - classified == set(), (
        f"tables neither scoped, derived nor named as holding no firm's data: "
        f"{sorted(every - classified)}"
    )


def test_each_derived_table_follows_a_mandatory_key_to_its_declared_parent():
    """The key must exist, point at the parent named, and never be NULL: a NULL would be
    a row belonging to nobody, which the filter would hide from its own firm."""
    for name, (column, parent) in DERIVED_TABLES.items():
        table = Base.metadata.tables[name]
        assert column in table.columns, (name, column)
        targets = {fk.column.table.name for fk in table.columns[column].foreign_keys}
        assert targets == {parent}, (name, column, targets)
        assert not table.columns[column].nullable, (name, column)
        assert parent in SCOPED_TABLES or parent in DERIVED_TABLES, (name, parent)


def test_the_derived_filter_is_installed_on_exactly_the_declared_tables():
    assert set(installed_derived_tables()) == set(DERIVED_TABLES), (
        "the derived scope installed at import does not match the declaration: "
        f"installed={list(installed_derived_tables())} "
        f"declared={sorted(DERIVED_TABLES)}"
    )
