"""Changing one's own password — the route that was missing.

🔴 THIS HOLE WAS THE PRODUCT'S WORST, and it did not look like a breakdown.
`must_change_password` was set in three places — the bootstrap, creation by Alice, every
reset — and faithfully reported at login. But no route let anybody answer it. A user was
required to replace a credential somebody else had seen, with no means of doing so. A
control that cannot be satisfied is not a control: it is a sign.

What these guards hold still is above all the refusal: the CURRENT password stays required
even when the change is imposed.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import hash_password, verify_password
from app.database import get_db
from app.main import app
from app.models.user import MANAGER, User

ANCIEN = "mot-de-passe-transmis"
NOUVEAU = "celui-que-je-choisis"


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


async def _account(db, *, must_change: bool = True) -> User:
    user = User(
        email="gestion@fonds.fr",
        hashed_password=hash_password(ANCIEN),
        account_name="Gestion",
        role=MANAGER,
        must_change_password=must_change,
    )
    db.add(user)
    await db.flush()
    return user


async def _token(client, password: str = ANCIEN) -> str:
    r = await client.post(
        "/api/v1/auth/login", json={"email": "gestion@fonds.fr", "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestTheHolderCanFinallyReplaceIt:
    async def test_the_change_goes_through_and_clears_the_obligation(self, client, db):
        user = await _account(db)
        token = await _token(client)

        r = await client.post(
            "/api/v1/auth/change-password",
            headers=bearer(token),
            json={"current_password": ANCIEN, "new_password": NOUVEAU},
        )
        assert r.status_code == 204, r.text

        await db.refresh(user)
        assert verify_password(NOUVEAU, user.hashed_password)
        assert user.must_change_password is False

    async def test_the_new_password_is_the_one_that_signs_in(self, client, db):
        await _account(db)
        token = await _token(client)
        await client.post(
            "/api/v1/auth/change-password",
            headers=bearer(token),
            json={"current_password": ANCIEN, "new_password": NOUVEAU},
        )
        assert (
            await client.post(
                "/api/v1/auth/login",
                json={"email": "gestion@fonds.fr", "password": NOUVEAU},
            )
        ).status_code == 200
        assert (
            await client.post(
                "/api/v1/auth/login",
                json={"email": "gestion@fonds.fr", "password": ANCIEN},
            )
        ).status_code == 401


class TestATokenProvesEntryNeverOwnership:
    async def test_the_current_password_is_required_even_when_the_change_is_imposed(
        self, client, db
    ):
        """🔴 THE POINT. Without this requirement a stolen token would be enough to take the
        account FOR GOOD: the victim loses access, the attacker keeps it. And it is exactly
        when `must_change_password` is true that one would be tempted to relax it, « since
        they have to change it anyway »."""
        await _account(db, must_change=True)
        token = await _token(client)
        r = await client.post(
            "/api/v1/auth/change-password",
            headers=bearer(token),
            json={"current_password": "au-hasard", "new_password": NOUVEAU},
        )
        assert r.status_code == 400
        assert "actuel" in r.json()["detail"]

    async def test_without_a_token_there_is_nothing_to_change(self, client, db):
        await _account(db)
        r = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": ANCIEN, "new_password": NOUVEAU},
        )
        assert r.status_code == 401


class TestTheReplacementMustActuallyReplace:
    async def test_reusing_the_same_password_is_refused(self, client, db):
        """Setting it back does not make it unknown to whoever handed it over."""
        await _account(db)
        token = await _token(client)
        r = await client.post(
            "/api/v1/auth/change-password",
            headers=bearer(token),
            json={"current_password": ANCIEN, "new_password": ANCIEN},
        )
        assert r.status_code == 400

    async def test_a_short_password_is_refused(self, client, db):
        await _account(db)
        token = await _token(client)
        r = await client.post(
            "/api/v1/auth/change-password",
            headers=bearer(token),
            json={"current_password": ANCIEN, "new_password": "court"},
        )
        assert r.status_code == 422


class TestWhoAmI:
    async def test_me_says_what_the_front_needs_after_a_refresh(self, client, db):
        """A reload keeps only the token: the screen must be able to ask again who it
        serves, and above all whether the password change is still due."""
        await _account(db)
        token = await _token(client)
        body = (await client.get("/api/v1/auth/me", headers=bearer(token))).json()
        assert body["email"] == "gestion@fonds.fr"
        assert body["sees_whole_fund"] is True
        assert body["must_change_password"] is True

    async def test_me_refuses_without_a_token(self, client):
        assert (await client.get("/api/v1/auth/me")).status_code == 401
