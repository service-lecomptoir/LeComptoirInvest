"""The audit journal is kept as long as in the sibling products, and no longer.

The manager, 27 Sept 2026: purge the journal like every other product does. These
tests run THE SHIPPED statement, not a copy of it: a test re-typing the DELETE would
prove its own copy.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text

from app.config import get_settings
from app.models.audit_log import AuditLog
from app.services import audit_retention

MARK = "retention-test"


async def _line(db, age_days: int) -> uuid.UUID:
    identifier = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO audit_logs (id, created_at, action, entity_type) "
            "VALUES (:id, now() - make_interval(days => :d), 'db.update', :mark)"
        ),
        {"id": identifier, "d": age_days, "mark": MARK},
    )
    return identifier


async def _kept(db) -> set[uuid.UUID]:
    rows = await db.execute(select(AuditLog.id).where(AuditLog.entity_type == MARK))
    return set(rows.scalars().all())


def test_the_default_is_the_house_s_ninety_days():
    assert get_settings().AUDIT_RETENTION_DAYS == 90
    assert audit_retention.DEFAULT_RETENTION_DAYS == 90


async def test_older_lines_go_and_newer_ones_stay(db):
    old = await _line(db, 91)
    older = await _line(db, 400)
    recent = await _line(db, 89)
    today = await _line(db, 0)

    removed = await audit_retention.purge_audit_logs(db, 90)

    assert removed is not None and removed >= 2
    kept = await _kept(db)
    assert old not in kept and older not in kept
    assert {recent, today} <= kept


async def test_the_purge_leaves_its_own_line(db):
    await _line(db, 120)
    removed = await audit_retention.purge_audit_logs(db, 90)

    trace = (
        (
            await db.execute(
                select(AuditLog).where(AuditLog.action == audit_retention.PURGE)
            )
        )
        .scalars()
        .all()
    )
    assert len(trace) == 1
    assert trace[0].details == {"removed": removed, "retention_days": 90}
    assert trace[0].user_email == audit_retention.ACTOR


async def _traces(db) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == audit_retention.PURGE)
        )
    ).scalar_one()


async def test_a_pass_with_nothing_to_remove_writes_nothing(db):
    await audit_retention.purge_audit_logs(db, 90)  # whatever was there before
    before = await _traces(db)
    await _line(db, 10)
    assert await audit_retention.purge_audit_logs(db, 90) == 0
    assert await _traces(db) == before, "a pass that removed nothing adds no line"


async def test_zero_keeps_everything(db):
    ancient = await _line(db, 5000)
    assert await audit_retention.purge_audit_logs(db, 0) == 0
    assert ancient in await _kept(db)
