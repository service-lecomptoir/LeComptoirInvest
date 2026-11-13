"""The erasure of a firm reaches every table of the schema it should, leaves first.

🔴 A TABLE ADDED TOMORROW IS ERASED WITH THE REST, OR KEPT ON PURPOSE (the owner, 13 Nov
2026, the space of an ended subscription is erased after its thirty days to export): the
purge's order (`firm_purge.PURGE_ORDER`), its account tables and the tables it keeps are
compared to the whole schema the models declare, and to their foreign keys, so that a row
is always deleted before the row it points to and every purged table reaches the firm. One
rule per test.
"""

from __future__ import annotations

import app.models  # noqa: F401 - every table known to the metadata
from app.core.firm_scope import SCOPED_TABLES
from app.models.base import Base
from app.services.firm_purge import ACCOUNT_TABLES, KEPT, PURGE_ORDER, owned


def test_every_table_is_purged_kept_or_an_account_table():
    said = [*PURGE_ORDER, *ACCOUNT_TABLES, *KEPT]
    assert sorted(said) == sorted(Base.metadata.tables)


def test_each_table_is_said_once():
    said = [*PURGE_ORDER, *ACCOUNT_TABLES, *KEPT]
    assert len(said) == len(set(said))


def test_every_table_that_carries_a_firm_is_purged():
    assert set(SCOPED_TABLES) <= set(PURGE_ORDER)


def test_a_row_goes_before_the_row_it_points_to():
    place = {name: i for i, name in enumerate(PURGE_ORDER)}
    late = [
        f"{child} -> {fk.column.table.name}"
        for child in PURGE_ORDER
        for fk in Base.metadata.tables[child].foreign_keys
        if fk.column.table.name in place
        and fk.column.table.name != child
        and place[child] > place[fk.column.table.name]
    ]
    assert not late, late


def test_every_purged_table_reaches_the_firm():
    for name in PURGE_ORDER:
        assert ":f" in owned(name), name


def test_no_purged_table_points_to_a_kept_one():
    """A purged row pointing to a kept table would leave the kept row orphaned or refuse."""
    wrong = [
        f"{child} -> {fk.column.table.name}"
        for child in PURGE_ORDER
        for fk in Base.metadata.tables[child].foreign_keys
        if fk.column.table.name in KEPT
    ]
    assert not wrong, wrong
