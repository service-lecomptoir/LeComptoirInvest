"""The subscription to the SOFTWARE, not to be confused with commitments to the FUNDS.

🔴 WHAT IS GUARDED HERE. Four decisions, none of which is visible on screen when taken the
wrong way round:

  * an investor has no subscription to this product and must be able to read nothing of it;
  * the payer's identity comes from the SESSION, never from a request parameter: an invoice
    would otherwise be read by changing an id in the address;
  * an absent console yields « not managed », NEVER a free plan: turning « I do not know »
    into « it is free » grants an entitlement nobody gave;
  * a PAYMENT action that fails raises an error, whereas a READ that fails degrades. A
    manager convinced they have paid when they have not is a support case; an amount shown
    as « unknown » is merely an incomplete screen.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1 import billing as billing_api
from app.core.security import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.models.user import INVESTOR, MANAGER, User
from app.services import alice_client


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


async def _user(db, role: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"{role}-{uuid.uuid4().hex[:8]}@fonds.test",
        hashed_password=hash_password("Motdepasse-1234"),
        account_name="Meridian Capital",
        role=role,
    )
    db.add(user)
    await db.flush()
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}


async def test_an_investor_has_no_subscription_to_read(client, db):
    """A unit holder pays for THEIR fund, not for the software. The screen is not theirs."""
    investor = await _user(db, INVESTOR)
    for path in (
        "/api/v1/billing",
        "/api/v1/billing/invoices",
        "/api/v1/billing/plans",
    ):
        resp = await client.get(path, headers=_auth(investor))
        assert resp.status_code == 403, f"{path} a répondu {resp.status_code}"


async def test_no_console_means_unknown_and_never_free(client, db, monkeypatch):
    """🔴 « No answer » does not translate to « free plan ».

    With no console, the screen must say it is not managed. The trap would be to return an
    empty `plan_name` with a price of zero: the user would read a free subscription there,
    and nobody granted them one.
    """

    async def _absent(_user_id):
        return None

    monkeypatch.setattr(alice_client, "get_license", _absent)
    manager = await _user(db, MANAGER)
    body = (await client.get("/api/v1/billing", headers=_auth(manager))).json()
    assert body["managed"] is False
    assert body["plan_name"] is None
    assert body["monthly_price"] is None


async def test_the_payer_is_the_session_never_a_parameter(client, db, monkeypatch):
    """The id handed to the console is the token holder's.

    ⚠️ The guard checks the ARGUMENT THE CLIENT RECEIVED, not merely the status code: an
    endpoint accepting a `user_id` from the query would answer 200 just the same, while
    reading another fund's invoice.
    """
    seen: list[uuid.UUID] = []

    async def _capture(user_id):
        seen.append(user_id)
        return []

    monkeypatch.setattr(alice_client, "invoices", _capture)
    manager = await _user(db, MANAGER)
    other = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/billing/invoices?user_id={other}", headers=_auth(manager)
    )
    assert resp.status_code == 200
    assert seen == [manager.id], "l'identifiant du payeur ne vient pas de la session"


async def test_a_read_degrades_but_a_payment_refuses(client, db, monkeypatch):
    """The console goes down: reading returns an empty list, paying returns an error."""

    async def _down(method, action, user_id, *, json=None, strict=True):
        if strict:
            raise alice_client.AliceUnavailable(
                "Le service d'abonnement est indisponible."
            )
        return None

    monkeypatch.setattr(alice_client, "billing", _down)
    manager = await _user(db, MANAGER)

    lecture = await client.get("/api/v1/billing/plans", headers=_auth(manager))
    assert lecture.status_code == 200 and lecture.json() == []

    paiement = await client.post(
        "/api/v1/billing/checkout", headers=_auth(manager), json={}
    )
    assert paiement.status_code == 503
    # Never a bare « Erreur »: the message is the one the user will read.
    assert "indisponible" in paiement.json()["detail"].lower()


async def test_the_fund_limit_reads_alices_shared_field_name(monkeypatch):
    """⚠️ Alice names this limit `property_limit` FOR EVERY PRODUCT.

    It is the cross-product contract. Renaming it on the console side would break the other
    three; reading it under another name here would always leave it empty, and a limited
    plan would pass for an unlimited one.
    """
    info = billing_api._as_info(
        {"plan_name": "Fonds Pro", "monthly_price": 149.0, "property_limit": 3}
    )
    assert info.fund_limit == 3
    assert info.managed is True
