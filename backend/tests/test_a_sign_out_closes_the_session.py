"""« Déconnexion » closes the session on the server, not only in the browser.

Measured on 30 Sept 2026: signing out removed the token from the browser and nothing else.
The token stayed good for the rest of its twelve hours, so a copy of it (a shared computer,
a stolen browser profile) kept opening the account after the person had signed out.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import get_settings
from app.core.security import hash_password
from app.database import get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.user import MANAGER, User

PASSWORD = "un-mot-de-passe-long"


@pytest.fixture
async def client(db, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "SECRET_KEY", settings.SECRET_KEY or "tests-only-key")

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://invest.test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


async def _holder(db, email: str) -> User:
    user = User(
        email=email,
        hashed_password=hash_password(PASSWORD),
        account_name="Cabinet",
        role=MANAGER,
        must_change_password=False,
    )
    db.add(user)
    await db.flush()
    return user


async def _sign_in(client, email: str) -> dict:
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_the_token_stops_working_once_signed_out(client, db):
    user = await _holder(db, "sortie@cabinet.fr")
    session = await _sign_in(client, user.email)
    assert (await client.get("/api/v1/auth/me", headers=session)).status_code == 200

    r = await client.post("/api/v1/auth/logout", headers=session)
    assert r.status_code == 204, r.text
    assert (await client.get("/api/v1/auth/me", headers=session)).status_code == 401


async def test_another_device_stays_signed_in(client, db):
    user = await _holder(db, "deux@cabinet.fr")
    laptop = await _sign_in(client, user.email)
    phone = await _sign_in(client, user.email)

    await client.post("/api/v1/auth/logout", headers=phone)
    assert (await client.get("/api/v1/auth/me", headers=laptop)).status_code == 200


async def test_an_unreadable_or_missing_token_closes_nothing_and_is_not_an_error(
    client,
):
    bad = {"Authorization": "Bearer pas.un.jeton"}
    assert (await client.post("/api/v1/auth/logout", headers=bad)).status_code == 204
    assert (await client.post("/api/v1/auth/logout")).status_code == 204


async def test_the_journal_says_who_signed_out(client, db):
    user = await _holder(db, "journal@cabinet.fr")
    session = await _sign_in(client, user.email)
    await client.post("/api/v1/auth/logout", headers=session)
    rows = (
        (
            await db.execute(
                select(AuditLog).where(AuditLog.entity_type == "revoked_sessions")
            )
        )
        .scalars()
        .all()
    )
    assert [row.user_email for row in rows] == [user.email]
