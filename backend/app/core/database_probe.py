"""Whether the database answers, asked at most once every few seconds.

🔴 THE DATABASE IS PROBED, NOT ASSUMED (the owner, 14 Nov 2026: « un besoin, un code »).
Since 14 Nov 2026 the base lives on the database server, reached through a WireGuard tunnel
at its service address 10.66.0.10: a cut of the tunnel leaves this container running and
answering, over a base it cannot reach. A `/health` answering « ok » then is a green light
over a closed road, and the deployment, Docker and Portail360's supervision all believe it.
The model is the one of Le Comptoir PDF, BTP, Syndic and Compta, and every product now
probes the same way.

⚠️ A CONNECTION OF ITS OWN, OUTSIDE THE POOL: a pooled connection only says the pool held
one, not that the road is open to a new one (authentication included). `SELECT 1`, five
seconds at most, so the probe never hangs the supervision.

🔴 ONE PROBE AT A TIME, ITS VERDICT REUSED FOR A FEW SECONDS. asyncpg authenticates a new
connection (SCRAM: four thousand HMACs in Python) ON THE EVENT LOOP; Le Comptoir BTP, asked
every 100 ms with one connection per call, held its worker 30 s (30 Sept 2026). However
often it is asked, the database is probed at most once every `PROBE_REUSE_SECONDS`, and
callers arriving during a probe wait for that one (shielded: a caller that gives up does
not cancel it for the others). A verdict five seconds old is still the road's state for a
supervision that looks every thirty.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

#: How long one answer of the database is reused by `/health`, in seconds.
PROBE_REUSE_SECONDS = 5.0

#: A probe never takes longer than this: Docker gives a health check ten seconds.
PROBE_TIMEOUT_SECONDS = 5.0


@dataclass
class _Probe:
    """The last verdict on the database, when it was given, and the probe under way."""

    at: float | None = None
    error: Exception | None = None
    running: asyncio.Task | None = None


_PROBE = _Probe()


async def _probe_database() -> None:
    """One connection of its own, outside the pool, and `SELECT 1`."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import get_settings

    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


async def _probe_once() -> Exception | None:
    try:
        await asyncio.wait_for(_probe_database(), timeout=PROBE_TIMEOUT_SECONDS)
        error = None
    except Exception as exc:  # noqa: BLE001 - whatever the reason, the road is closed
        error = exc
    _PROBE.at, _PROBE.error = time.monotonic(), error
    return error


async def database_error() -> Exception | None:
    """What keeps the database from answering, or None; a verdict at most a few seconds old."""
    if _PROBE.at is not None and time.monotonic() - _PROBE.at < PROBE_REUSE_SECONDS:
        return _PROBE.error
    loop = asyncio.get_running_loop()
    running = _PROBE.running
    if running is None or running.done() or running.get_loop() is not loop:
        running = _PROBE.running = loop.create_task(_probe_once())
    return await asyncio.shield(running)


def forget() -> None:
    """Drop the verdict held (tests: each one asks the database afresh)."""
    _PROBE.at = None
    _PROBE.running = None
