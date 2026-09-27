"""How long the audit journal is kept, and the daily pass that enforces it.

🔴 THE SAME RETENTION AS THE REST OF THE HOUSE. The manager, 27 Sept 2026: the audit
journal is purged like in every other product of the house. Immo and Séjour keep it ninety days
(`AUDIT_RETENTION_DAYS`), purged every day; this product kept every line for ever, so the
one table nobody reads on a screen was the one growing fastest.

⚠️ ONLY THE JOURNAL. Nothing here touches the register, a commitment, a movement or a
distribution: they follow the fund's own legal retention (anti-money-laundering files
for five years at least), which is the fund's and not this pass's. The statement names
`audit_logs` and nothing else.

⚠️ `0` DISABLES THE PURGE and is not the same as « zero days », which would empty the
table. The two are one keystroke apart in a configuration file, hence the early return
rather than an interval of zero.

🔴 A BULK DELETE IS INVISIBLE TO THE JOURNAL'S LISTENERS, so the pass writes its own line
(`retention.purge`, with the count) in the same transaction, the way Le Comptoir SI does:
a purge rolled back leaves no line claiming it happened. A pass that removed nothing
writes nothing, or a line a day saying « 0 » would bury the ones that matter.

⚠️ TWO WORKERS, ONE PURGE. uvicorn runs two processes and each lifespan starts the loop; a
transaction-level advisory lock lets the first one work and the second one skip.

The cut-off is computed by the DATABASE (`now()`), so both sides of the comparison are
read on the same clock.

Run by hand: `python -m app.services.audit_retention`.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import func, insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

#: Retention used when the setting says nothing: the house's ninety days.
DEFAULT_RETENTION_DAYS = 90

#: The action of the line the pass writes about itself. Same name as Le Comptoir SI's,
#: so the supervision reads one word for one event across products.
PURGE = "retention.purge"

#: Any fixed number: it names this job's lock among the database's advisory locks.
_LOCK_KEY = 27_092_030

#: How long between two passes. A day: the retention is counted in days.
SWEEP_SECONDS = 24 * 3600

#: The first pass waits a minute after start, so a restart loop never hammers the table.
FIRST_DELAY_SECONDS = 60

#: Who the line says did it. Not an account: the scheduled pass itself.
ACTOR = "audit-retention (scheduled)"


def configured_retention_days() -> int:
    """The retention in force. `0` (or negative) means « keep everything, for ever »."""
    return int(
        getattr(get_settings(), "AUDIT_RETENTION_DAYS", DEFAULT_RETENTION_DAYS) or 0
    )


async def purge_audit_logs(db: AsyncSession, days: int) -> int | None:
    """Delete the journal lines older than `days`. Returns how many went, or None when
    another process holds the lock. The caller commits."""
    if days <= 0:
        return 0
    locked = (
        await db.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": _LOCK_KEY}
        )
    ).scalar()
    if not locked:
        return None
    result = await db.execute(
        text(
            "DELETE FROM audit_logs WHERE created_at < now() - make_interval(days => :d)"
        ),
        {"d": days},
    )
    removed = int(result.rowcount or 0)
    if removed:
        # ⚠️ A DIRECT INSERT, not `session.add`: the line is about the journal, written by
        # nobody, and it must not wait for a flush the caller may never trigger.
        await db.execute(
            insert(AuditLog).values(
                id=uuid.uuid4(),
                created_at=func.now(),
                user_id=None,
                user_email=ACTOR,
                action=PURGE,
                entity_type="audit_logs",
                entity_id=None,
                details={"removed": removed, "retention_days": days},
                ip_address=None,
            )
        )
        logger.info("Audit journal purge: %s line(s) older than %s days", removed, days)
    return removed


async def run_once() -> int | None:
    """One pass, in a session of its own, committed."""
    from app.database import AsyncSessionLocal

    days = configured_retention_days()
    if days <= 0:
        return 0
    async with AsyncSessionLocal() as db:
        removed = await purge_audit_logs(db, days)
        await db.commit()
        return removed


async def run_forever() -> None:
    """The in-process schedule: a first pass a minute after start, then one a day. A
    failed pass is logged and the loop carries on: the next one removes what this one
    could not."""
    await asyncio.sleep(FIRST_DELAY_SECONDS)
    while True:
        try:
            await run_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - logged, retried at the next pass
            logger.exception("Audit journal purge failed")
        await asyncio.sleep(SWEEP_SECONDS)


if __name__ == "__main__":  # pragma: no cover - the manual door
    logging.basicConfig(level=logging.INFO)
    print(asyncio.run(run_once()))
