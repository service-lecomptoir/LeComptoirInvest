"""An ended subscription keeps reading and exporting its data for thirty days.

The terms of sale of Alice, article 7.4: the client has thirty days « pour exporter ses
données » from the end of the subscription. The owner, 12 Nov 2026: make the code say what
the texts say. Until then the subscriber of an ended licence was held to « Mon abonnement »
the very day the paid month ended. One rule now (`licence_state.EXPORT_DAYS`,
`gate(reading=...)`): every read open for thirty days after `access_until`, writes closed,
then « Mon abonnement » alone. The team stays refused from the end. The dates are relative
to now: a day written in full would change meaning within a month.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.models.user import MANAGER, User
from app.services import alice_client, licence_state
from tests.conftest import TEST_FIRM


@pytest.fixture
async def client(db):
    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://invest.test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


async def _account(db, *, firm: uuid.UUID | None = None, **kw) -> User:
    user = User(
        id=kw.pop("id", uuid.uuid4()),
        email=f"gerant-{uuid.uuid4().hex[:8]}@fonds.fr",
        hashed_password=hash_password("Motdepasse-1234"),
        account_name="Meridian Capital",
        role=MANAGER,
        firm_id=firm,
    )
    db.add(user)
    await db.flush()
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}


def _ended(monkeypatch, days_ago: int) -> datetime:
    """The firm's licence ended `days_ago` days ago, as Alice writes it (naive UTC)."""
    ends = datetime.now(UTC) - timedelta(days=days_ago)
    licence = {
        "is_blocked": True,
        "plan_name": "Fonds 50",
        "managed_limit": None,
        "access_until": ends.replace(tzinfo=None).isoformat(),
    }

    async def _get(user_id, *, strict: bool = False):
        return licence if user_id == TEST_FIRM else None

    monkeypatch.setattr(alice_client, "console_configured", lambda: True)
    monkeypatch.setattr(alice_client, "get_license", _get)
    return ends


async def test_the_subscriber_reads_the_register_during_the_thirty_days(
    client, db, monkeypatch
):
    subscriber = await _account(db, id=TEST_FIRM)
    _ended(monkeypatch, days_ago=5)
    r = await client.get("/api/v1/investors", headers=_auth(subscriber))
    assert r.status_code == 200, r.text
    me = await client.get("/api/v1/auth/me", headers=_auth(subscriber))
    assert me.json()["subscription_ended"] is False


async def test_the_subscriber_writes_nothing_during_the_thirty_days(
    client, db, monkeypatch
):
    """Decision A (the owner, 13 Nov 2026): the write is refused WHERE it was tried, under
    its own code and with the last day, JJ/MM/AAAA; the screen keeps the form open."""
    subscriber = await _account(db, id=TEST_FIRM)
    ends = _ended(monkeypatch, days_ago=5)
    r = await client.post(
        "/api/v1/investors",
        headers=_auth(subscriber),
        json={"kind": "personne", "first_name": "Grace", "last_name": "Hopper"},
    )
    assert r.status_code == 403
    assert r.headers.get("X-Error-Code") == licence_state.SUBSCRIPTION_READ_ONLY
    last_day = licence_state.platform_day(ends + timedelta(days=30))
    assert r.json()["detail"] == (
        "Abonnement terminé : lecture et export seulement jusqu'au "
        f"{last_day.strftime('%d/%m/%Y')}."
    )


async def test_the_write_refused_is_said_in_the_reader_s_language(
    client, db, monkeypatch
):
    subscriber = await _account(db, id=TEST_FIRM)
    _ended(monkeypatch, days_ago=5)
    r = await client.post(
        "/api/v1/investors",
        headers={**_auth(subscriber), "Accept-Language": "en"},
        json={"kind": "personne", "first_name": "Grace", "last_name": "Hopper"},
    )
    assert r.status_code == 403
    assert r.json()["detail"].startswith(
        "Subscription ended: reading and export only until "
    )


async def test_mon_abonnement_still_takes_a_write_during_the_thirty_days(
    client, db, monkeypatch
):
    """Subscribing again, or changing one's password, is a write: the doors « Mon
    abonnement » keeps open (`held_subscriber_may_reach`) stay open to it."""
    subscriber = await _account(db, id=TEST_FIRM)
    _ended(monkeypatch, days_ago=5)
    r = await client.post(
        "/api/v1/auth/change-password",
        headers=_auth(subscriber),
        json={
            "current_password": "Motdepasse-1234",
            "new_password": "Un-autre-mot-de-passe-5678",
        },
    )
    assert r.status_code == 204, r.text


async def test_the_team_stays_refused_from_the_end(client, db, monkeypatch):
    await _account(db, id=TEST_FIRM)
    colleague = await _account(db, firm=TEST_FIRM)
    _ended(monkeypatch, days_ago=5)
    r = await client.get("/api/v1/investors", headers=_auth(colleague))
    assert r.status_code == 401
    assert r.headers.get("X-Error-Code") == licence_state.LICENCE_ENDED


async def test_the_subscription_says_until_when(client, db, monkeypatch):
    subscriber = await _account(db, id=TEST_FIRM)
    ends = _ended(monkeypatch, days_ago=5)
    sub = (await client.get("/api/v1/billing", headers=_auth(subscriber))).json()
    assert sub["ended"] is True and sub["exports_open"] is True
    until = datetime.fromisoformat(sub["export_until"])
    assert abs(until - (ends + timedelta(days=30))) < timedelta(seconds=1)


async def test_after_the_thirty_days_mon_abonnement_alone(client, db, monkeypatch):
    subscriber = await _account(db, id=TEST_FIRM)
    _ended(monkeypatch, days_ago=31)
    r = await client.get("/api/v1/investors", headers=_auth(subscriber))
    assert r.status_code == 403
    assert r.headers.get("X-Error-Code") == licence_state.LICENCE_ENDED
    sub = (await client.get("/api/v1/billing", headers=_auth(subscriber))).json()
    assert sub["exports_open"] is False


def test_the_window_is_thirty_days_after_the_end():
    ends = datetime(2026, 10, 31, 23, 59, 59, tzinfo=UTC)
    state = licence_state.read(
        {"is_blocked": True, "access_until": "2026-10-31T23:59:59"}, now=ends
    )
    assert state is not None and state.terminated
    assert licence_state.EXPORT_DAYS == 30
    assert state.export_until == ends + timedelta(days=licence_state.EXPORT_DAYS)
    assert state.exports_open(ends + timedelta(days=29))
    assert not state.exports_open(ends + timedelta(days=30, seconds=1))


def test_a_suspension_opens_no_window():
    """A licence suspended for an unpaid invoice did not end: nothing to export, the
    subscriber settles from « Mon abonnement »."""
    state = licence_state.read({"is_blocked": True, "access_until": None})
    assert state is not None and state.suspended
    assert state.export_until is None and not state.exports_open()
