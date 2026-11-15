"""`/health` says whether the database answers, and never opens one connection per call.

The owner, 14 Nov 2026 (« un besoin, un code »): the base lives on the database server,
through a WireGuard tunnel, and every product's health route probes it, as Le Comptoir PDF,
BTP, Syndic and Compta already did. A container answering « ok » over a base it cannot
reach is a green light over a closed road: the deployment, Docker and Portail360's
supervision all believe it.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import database_probe


@pytest.fixture(autouse=True)
def no_verdict_held():
    """Each test asks the database afresh: a verdict is reused for a few seconds."""
    database_probe.forget()
    yield
    database_probe.forget()


def test_unhealthy_when_the_database_does_not_answer(monkeypatch):
    """A lost database answers 503, and the reason stays a type name."""
    from app.main import app as application

    async def _no_database():
        raise ConnectionRefusedError("no database behind this address")

    monkeypatch.setattr(database_probe, "_probe_database", _no_database)

    async def scenario():
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://health.test"
        ) as client:
            return await client.get("/health")

    r = asyncio.run(scenario())
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "database_unavailable"
    # The reason stays a type name: the address of the database is nobody's business.
    assert body["detail"] == "ConnectionRefusedError"


def test_the_database_is_probed_once_however_often_health_is_asked(monkeypatch):
    """Twenty callers at once, then twenty more: one probe, and the others share it."""
    probes = 0

    async def _probe_database():
        nonlocal probes
        probes += 1
        await asyncio.sleep(0.05)

    monkeypatch.setattr(database_probe, "_probe_database", _probe_database)

    async def scenario():
        verdicts = await asyncio.gather(
            *(database_probe.database_error() for _ in range(20))
        )
        for _ in range(20):
            verdicts.append(await database_probe.database_error())
        assert verdicts == [None] * 40
        assert probes == 1
        assert database_probe._PROBE.at is not None
        database_probe._PROBE.at -= database_probe.PROBE_REUSE_SECONDS
        await database_probe.database_error()
        assert probes == 2, "an old verdict is probed again"

    asyncio.run(scenario())
