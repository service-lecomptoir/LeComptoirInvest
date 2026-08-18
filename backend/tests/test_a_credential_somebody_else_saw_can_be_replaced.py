"""Changer son mot de passe — la route qui manquait.

🔴 CE TROU ÉTAIT LE PIRE DU PRODUIT, et il ne ressemblait pas à une panne. `must_change_password`
était posé à trois endroits — l'amorçage, la création par Alice, chaque réinitialisation —
et fidèlement renvoyé à la connexion. Mais aucune route ne permettait d'y répondre. On
exigeait d'un utilisateur qu'il remplace un identifiant qu'un autre avait vu, sans lui en
donner le moyen. Un contrôle qu'on ne peut pas satisfaire n'est pas un contrôle : c'est un
panneau.

Ce que ces gardes tiennent immobile, c'est surtout le refus : le mot de passe ACTUEL reste
exigé même quand le changement est imposé.
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
        """🔴 LE POINT. Sans cette exigence, un jeton volé suffirait à s'approprier le
        compte DÉFINITIVEMENT : la victime perd l'accès, l'attaquant le garde. Et c'est
        précisément quand `must_change_password` est vrai qu'on serait tenté de l'assouplir,
        « puisque de toute façon il doit changer »."""
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
        """Le remettre ne le rend pas inconnu de qui l'a transmis."""
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
        """Un rechargement ne garde que le jeton : l'écran doit pouvoir redemander qui il
        sert, et surtout si le changement de mot de passe est encore dû."""
        await _account(db)
        token = await _token(client)
        body = (await client.get("/api/v1/auth/me", headers=bearer(token))).json()
        assert body["email"] == "gestion@fonds.fr"
        assert body["sees_whole_fund"] is True
        assert body["must_change_password"] is True

    async def test_me_refuses_without_a_token(self, client):
        assert (await client.get("/api/v1/auth/me")).status_code == 401
