"""A password is chosen through a link: after « Mot de passe oublié », and for a new account.

🔴 THE HOLE (customer recipe, 30 Sept 2026): the sign-in page had no way back for a
forgotten password, and an account opened by the console received a temporary password
written in clear in an e-mail. What is held here: the same answer whether the address holds
an account or not, a letter in the holder's language and company look whose link is a
button, a link that opens the session once and dies with the password it replaced, and the
console's door (`POST /internal/managers/{id}/password-link`) for an account born without
a password.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt

from app.api.v1 import auth as auth_routes
from app.config import get_settings
from app.core.security import hash_password
from app.database import get_db
from app.main import app
from app.models.user import MANAGER, User
from app.services import mailer, password_link_service

KEY = "cle-interne-de-test"
OLD = "ancien-mot-de-passe"
NEW = "celui-que-je-choisis"


@pytest.fixture
async def client(db):
    settings = get_settings()
    previous = settings.ALICE_INTERNAL_KEY
    settings.ALICE_INTERNAL_KEY = KEY
    auth_routes._forgot_window.clear()

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://invest.test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    settings.ALICE_INTERNAL_KEY = previous
    auth_routes._forgot_window.clear()


@pytest.fixture
def outbox(monkeypatch):
    sent: list[dict] = []

    async def _send(**letter):
        sent.append(letter)

    monkeypatch.setattr(mailer, "send", _send)
    return sent


async def _account(db, *, locale: str = "fr", active: bool = True) -> User:
    user = User(
        email="gestion@fonds.fr",
        hashed_password=hash_password(OLD),
        account_name="Gestion Rivoli",
        role=MANAGER,
        locale=locale,
        is_active=active,
        last_login_at=datetime.now(UTC),
    )
    db.add(user)
    await db.flush()
    return user


def _token_of(letter: dict) -> str:
    link = get_settings().PUBLIC_APP_URL.rstrip("/") + password_link_service.LINK_PATH
    text = letter["body"]
    start = text.index(link) + len(link)
    return text[start:].split()[0]


async def test_the_answer_is_the_same_whether_the_address_holds_an_account_or_not(
    client, db, outbox
):
    await _account(db)
    known = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "gestion@fonds.fr"}
    )
    unknown = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "personne@ailleurs.fr"}
    )
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert [letter["to"] for letter in outbox] == ["gestion@fonds.fr"]


async def test_the_letter_carries_a_button_in_the_holders_language(client, db, outbox):
    await _account(db, locale="en")
    await client.post(
        "/api/v1/auth/forgot-password", json={"email": "gestion@fonds.fr"}
    )
    (letter,) = outbox
    url = get_settings().PUBLIC_APP_URL.rstrip("/") + password_link_service.LINK_PATH
    assert letter["subject"].startswith("A new password")
    assert "Hello Gestion Rivoli," in letter["body"]
    assert url in letter["body"], "the plain text keeps the address"
    assert f'href="{url}' in letter["html"], "the HTML part is a button"
    assert ">Choose a new password</a>" in letter["html"]
    assert 'lang="en"' in letter["html"]
    assert letter["html"].count("Kind regards,") == 1, "signed once"


async def test_the_link_opens_the_session_once_and_dies_with_the_old_password(
    client, db, outbox
):
    user = await _account(db)
    await client.post(
        "/api/v1/auth/forgot-password", json={"email": "gestion@fonds.fr"}
    )
    token = _token_of(outbox[0])

    info = await client.get(f"/api/v1/auth/password-link/{token}")
    assert info.json() == {"email": "gestion@fonds.fr", "purpose": "reset"}

    short = await client.post(
        f"/api/v1/auth/password-link/{token}", json={"new_password": "court"}
    )
    assert short.status_code == 422

    done = await client.post(
        f"/api/v1/auth/password-link/{token}", json={"new_password": NEW}
    )
    assert done.status_code == 200
    assert done.json()["access_token"] and done.json()["must_change_password"] is False
    assert user.must_change_password is False

    again = await client.post(
        f"/api/v1/auth/password-link/{token}", json={"new_password": "encore-un-autre"}
    )
    assert again.status_code == 410
    assert again.json()["detail"].startswith("Ce lien a déjà servi")

    signed_in = await client.post(
        "/api/v1/auth/login", json={"email": "gestion@fonds.fr", "password": NEW}
    )
    assert signed_in.status_code == 200


async def test_an_expired_or_forged_link_says_what_to_do(client, db):
    user = await _account(db)
    stale = jwt.encode(
        {
            "sub": str(user.id),
            "type": password_link_service.TOKEN_TYPE,
            "purpose": "reset",
            "fp": password_link_service.fingerprint(user),
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        get_settings().SECRET_KEY,
        algorithm="HS256",
    )
    expired = await client.get(f"/api/v1/auth/password-link/{stale}")
    assert expired.status_code == 410
    assert "Mot de passe oublié" in expired.json()["detail"]
    forged = await client.get("/api/v1/auth/password-link/pas-un-jeton")
    assert forged.status_code == 404


async def test_a_blocked_account_gets_no_link(client, db, outbox):
    await _account(db, active=False)
    out = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "gestion@fonds.fr"}
    )
    assert out.status_code == 200
    assert outbox == []


async def test_the_console_opens_an_account_without_a_password_and_asks_for_the_link(
    client, db, outbox
):
    created = await client.post(
        "/internal/managers",
        json={"email": "nouveau@fonds.fr", "full_name": "Camille Recette"},
        headers={"X-Internal-Key": KEY},
    )
    assert created.status_code == 201, created.text
    user = await db.get(User, uuid.UUID(created.json()["id"]))
    assert user.must_change_password is False, "nothing handed over, nothing to change"
    signed_in = await client.post(
        "/api/v1/auth/login", json={"email": "nouveau@fonds.fr", "password": ""}
    )
    assert signed_in.status_code in (401, 422), "an account born unusable"

    asked = await client.post(
        f"/internal/managers/{user.id}/password-link", headers={"X-Internal-Key": KEY}
    )
    assert asked.json() == {
        "email_sent": True,
        "to": "nouveau@fonds.fr",
        "purpose": "welcome",
    }
    (letter,) = outbox
    assert letter["subject"].startswith("Choisissez votre mot de passe")
    assert "une semaine" in letter["body"]
    assert ">Choisir mon mot de passe</a>" in letter["html"]
    token = _token_of(letter)
    done = await client.post(
        f"/api/v1/auth/password-link/{token}", json={"new_password": NEW}
    )
    assert done.status_code == 200


async def test_the_console_door_is_closed_without_its_key(client, db):
    user = await _account(db)
    out = await client.post(f"/internal/managers/{user.id}/password-link")
    assert out.status_code in (401, 403)
