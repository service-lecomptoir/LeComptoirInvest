"""The password of the sign-in has a ceiling (5 Nov 2026).

Until then `/auth/login` could be tried without limit, while the forgotten password and the
second step already had one. Ten attempts a minute per visitor, read from the last hop of
`X-Forwarded-For` (`audit.client_address`): behind the proxy the socket's peer is the proxy
itself, and counted on it every visitor would share one window.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1 import auth as auth_routes
from app.core.security import hash_password
from app.database import get_db
from app.main import app
from app.models.user import MANAGER, User

PASSWORD = "mot-de-passe-du-gerant"


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


async def _account(db) -> User:
    user = User(
        email=f"gerant-{uuid.uuid4().hex[:6]}@example.org",
        hashed_password=hash_password(PASSWORD),
        account_name="Gestion Rivoli",
        role=MANAGER,
        locale="fr",
        is_active=True,
        last_login_at=datetime.now(UTC),
    )
    db.add(user)
    await db.flush()
    return user


async def _login(client, email: str, password: str, visitor: str = "203.0.113.7"):
    return await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={"X-Forwarded-For": visitor},
    )


async def test_the_eleventh_attempt_of_a_minute_is_refused_in_one_sentence(client):
    statuses = [
        (await _login(client, "personne@example.org", "pas-le-bon")).status_code
        for _ in range(auth_routes.LOGIN_PER_MINUTE)
    ]
    assert statuses == [401] * 10
    refused = await _login(client, "personne@example.org", "pas-le-bon")
    assert refused.status_code == 429
    assert refused.json()["detail"].startswith("Trop de tentatives")


async def test_the_refusal_speaks_the_reader_s_language(client):
    for _ in range(auth_routes.LOGIN_PER_MINUTE):
        await _login(client, "personne@example.org", "pas-le-bon")
    refused = await client.post(
        "/api/v1/auth/login",
        json={"email": "personne@example.org", "password": "pas-le-bon"},
        headers={"X-Forwarded-For": "203.0.113.7", "Accept-Language": "en"},
    )
    assert refused.status_code == 429
    assert (
        refused.json()["detail"] == "Too many attempts at once: try again in a minute."
    )


async def test_the_right_password_waits_too_once_the_ceiling_is_reached(client, db):
    """Otherwise the ceiling would only slow down whoever already fails."""
    user = await _account(db)
    for _ in range(auth_routes.LOGIN_PER_MINUTE):
        await _login(client, user.email, "pas-le-bon")
    assert (await _login(client, user.email, PASSWORD)).status_code == 429


async def test_another_visitor_is_not_locked_out(client, db):
    user = await _account(db)
    for _ in range(auth_routes.LOGIN_PER_MINUTE + 1):
        await _login(client, user.email, "pas-le-bon", visitor="203.0.113.7")
    answer = await _login(client, user.email, PASSWORD, visitor="198.51.100.9")
    assert answer.status_code == 200, answer.text
