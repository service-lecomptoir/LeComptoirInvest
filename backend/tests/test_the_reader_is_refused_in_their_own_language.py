"""The refusal reaches the reader in the language they asked for, over a real request.

🔴 THE MECHANISM IS A `ContextVar`, AND THAT IS THE WHOLE RISK. A module-level dict freezes
the language at import and gives every reader whatever the first one happened to be - the
sister product paid for that one. A ContextVar avoids it, but it introduces its own failure:
a value set on one request and never cleared would leak into the next, so an English reader
would leave the French one reading English. Both defects look identical from a single test
that only ever asks in one language.

So these guards never check a translation in isolation. They ask TWICE, in two languages,
over the real ASGI stack, and check that the second answer did not inherit the first.

⚠️ AND THE REFUSAL IS CHECKED, NOT A GREETING. Every sentence this product writes on the
server is a refusal - the lenders are not covered, this file is not accepted, that transfer
is an incoming one - and the front end shows `detail` verbatim. A refusal in the wrong
language is the one message a user cannot work around.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import i18n
from app.core.security import hash_password
from app.database import get_db
from app.main import app
from app.models.user import MANAGER, User

EMAIL = "gestion@fonds.fr"
PASSWORD = "le-mot-de-passe"


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
        email=EMAIL,
        hashed_password=hash_password(PASSWORD),
        account_name="Gestion",
        role=MANAGER,
    )
    db.add(user)
    await db.flush()
    return user


async def _wrong_password(client, lang: str | None) -> str:
    headers = {"Accept-Language": lang} if lang is not None else {}
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": EMAIL, "password": "pas-celui-la"},
        headers=headers,
    )
    assert response.status_code == 401, response.text
    return response.json()["detail"]


async def test_the_same_refusal_comes_back_in_the_language_that_was_asked_for(
    client, db
):
    await _account(db)

    assert await _wrong_password(client, "fr") == "Identifiants incorrects."
    assert await _wrong_password(client, "en") == "Wrong credentials."


async def test_a_request_never_inherits_the_previous_reader_s_language(client, db):
    """🔴 THE ONE A SINGLE-LANGUAGE TEST CANNOT SEE.

    An English call followed by a French one has to answer French. If the ContextVar were
    set without ever being reset - or set once at startup - this passes in every test that
    only ever asks in one language, and fails in production the moment two readers share a
    worker.
    """
    await _account(db)

    assert await _wrong_password(client, "en") == "Wrong credentials."
    assert await _wrong_password(client, "fr") == "Identifiants incorrects."
    assert await _wrong_password(client, "en") == "Wrong credentials."


async def test_a_reader_who_says_nothing_is_answered_in_french(client, db):
    """The default is a decision: this fund's operators are French-speaking, and a missing
    header should land on the language the refusals were written in."""
    await _account(db)

    assert await _wrong_password(client, None) == "Identifiants incorrects."


async def test_a_language_this_product_does_not_carry_falls_back_rather_than_failing(
    client, db
):
    """⚠️ A BROWSER ASKING FOR PORTUGUESE MUST GET A READABLE PAGE, NOT A 500. The header is
    written by whoever is calling, and refusing it is a refusal of the whole request."""
    await _account(db)

    assert await _wrong_password(client, "pt-BR") == "Identifiants incorrects."
    assert await _wrong_password(client, "en-GB,en;q=0.9") == "Wrong credentials."


def test_forcing_a_language_for_a_block_puts_back_what_it_found():
    """`use_lang` exists for text addressed to SOMEBODY ELSE - a statement generated for an
    investor rather than for the caller. It has no production caller yet, and it is guarded
    now because the day it gets one, a leak would be attributed to the request instead."""
    i18n.set_current_lang("fr")
    with i18n.use_lang("en"):
        assert i18n.current_lang() == "en"
        with i18n.use_lang("fr"):
            assert i18n.current_lang() == "fr"
        assert i18n.current_lang() == "en"
    assert i18n.current_lang() == "fr"


def test_a_sentence_is_never_chosen_by_a_value_captured_at_import():
    """🔴 THE TRAP THE SISTER PRODUCT PAID FOR, stated as a guard rather than a comment.

    `pick` is a function called per reader. A catalogue built once - `_LABELS = {k: pick(...)}`
    at module level - would answer with whatever language the process started in, for ever.
    """
    fr, en = "Rien à distribuer.", "Nothing to distribute."

    i18n.set_current_lang("fr")
    first = i18n.pick(fr, en)
    i18n.set_current_lang("en")
    second = i18n.pick(fr, en)

    assert (first, second) == (fr, en)
