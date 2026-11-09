"""The firm's licence, who is held to it, and what it bills (the owner, 8 Nov 2026).

Alice bills Invest's subscriptions from 1 January 2027, on the number of investors. These
tests were written FIRST, against origin/main, and each one failed there:

  * a colleague of the firm (a manager whose `firm_id` names the subscriber) was asked for
    a licence of their own, which Alice does not hold: 403 « Aucun abonnement » where the
    subscriber met the plan's ceiling and its 402;
  * a firm whose licence was blocked went on working through its colleagues: nothing read
    the licence at sign-in or on a request, only `/block` switched the subscriber off;
  * `/block` answered `user_ids` where Alice reads `blocked_user_ids`: she kept an empty
    list, and `/unblock` with that empty list left the subscriber switched off for good;
  * every account of the firm reported the firm's whole count to Alice, colleagues included;
  * the 402 wrote the price as `12.5 €/mois`, not in the account's currency and decimals;
  * a billing call Alice refused on her key relayed her own sentence (« Clé interne
    invalide »), and paying the plan in place checked no terms of sale.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.core import kyc
from app.core.security import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.models.investor import Investor
from app.models.user import INVESTOR, MANAGER, User
from app.services import alice_client, license_service, licence_state
from tests.conftest import TEST_FIRM

INTERNAL_KEY = "cle-interne-de-test"


@pytest.fixture
async def client(db):
    get_settings.cache_clear()
    settings = get_settings()
    previous = settings.ALICE_INTERNAL_KEY
    settings.ALICE_INTERNAL_KEY = INTERNAL_KEY

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://invest.test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    settings.ALICE_INTERNAL_KEY = previous


async def _account(db, *, role: str = MANAGER, firm: uuid.UUID | None = None, **kw):
    user = User(
        id=kw.pop("id", uuid.uuid4()),
        email=f"{role}-{uuid.uuid4().hex[:8]}@fonds.fr",
        hashed_password=hash_password("Motdepasse-1234"),
        account_name="Meridian Capital",
        role=role,
        firm_id=firm,
        **kw,
    )
    db.add(user)
    await db.flush()
    return user


async def _subscriber(db) -> User:
    """The account that IS the firm: `firm_of` points at itself, and the suite's rows are
    stamped with its id."""
    return await _account(db, id=TEST_FIRM)


async def _colleague(db) -> User:
    return await _account(db, firm=TEST_FIRM)


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}


async def _register(db, *, status: str = kyc.PENDING) -> Investor:
    investor = Investor(
        kind="personne",
        first_name="Ada",
        last_name=f"Lovelace-{uuid.uuid4().hex[:6]}",
        kyc_status=status,
    )
    db.add(investor)
    await db.flush()
    return investor


def _licence(**over) -> dict:
    base = {
        "managed_limit": 2,
        "overage_price": 12.5,
        "overage_allowed": True,
        "plan_name": "Fonds 50",
        "monthly_price": 49.0,
        "is_blocked": False,
    }
    return {**base, **over}


def _console(monkeypatch, licence: dict) -> list[uuid.UUID]:
    """Alice holds ONE licence, the subscriber's (`TEST_FIRM`); any other id is a 404."""
    asked: list[uuid.UUID] = []

    async def _get(user_id, *, strict: bool = False):
        asked.append(user_id)
        return licence if user_id == TEST_FIRM else None

    monkeypatch.setattr(alice_client, "console_configured", lambda: True)
    monkeypatch.setattr(alice_client, "get_license", _get)
    return asked


def _body() -> dict:
    return {"kind": "personne", "first_name": "Grace", "last_name": "Hopper"}


# ── The ceiling, for the whole team ──────────────────────────────────────────────


async def test_a_colleague_meets_the_firms_ceiling_and_its_402(client, db, monkeypatch):
    asked = _console(monkeypatch, _licence())
    await _subscriber(db)
    colleague = await _colleague(db)
    await _register(db)
    await _register(db)

    first = await client.post(
        "/api/v1/investors", json=_body(), headers=_auth(colleague)
    )
    assert first.status_code == 402, first.text
    assert set(asked) == {TEST_FIRM}, (
        "the licence read is the subscriber's, never theirs"
    )
    # The account's currency, with its decimals: never « 12.5 € ».
    assert "12,50 €" in first.json()["detail"]

    yes = await client.post(
        "/api/v1/investors?accept_overage=true", json=_body(), headers=_auth(colleague)
    )
    assert yes.status_code == 201


async def test_a_colleague_meets_a_closed_ceiling(client, db, monkeypatch):
    _console(monkeypatch, _licence(overage_price=None, overage_allowed=False))
    await _subscriber(db)
    colleague = await _colleague(db)
    await _register(db)
    await _register(db)
    resp = await client.post(
        "/api/v1/investors", json=_body(), headers=_auth(colleague)
    )
    assert resp.status_code == 400
    assert "2/2" in resp.json()["detail"]


async def test_reversing_a_refusal_asks_the_place_back_for_a_colleague_too(
    client, db, monkeypatch
):
    _console(monkeypatch, _licence())
    await _subscriber(db)
    colleague = await _colleague(db)
    await _register(db)
    await _register(db)
    refused = await _register(db, status=kyc.REFUSED)
    resp = await client.post(
        f"/api/v1/investors/{refused.id}/kyc",
        json={"status": kyc.PENDING},
        headers=_auth(colleague),
    )
    assert resp.status_code == 402


async def test_the_402_speaks_english_to_an_english_reader(client, db, monkeypatch):
    _console(monkeypatch, _licence())
    subscriber = await _subscriber(db)
    await _register(db)
    await _register(db)
    resp = await client.post(
        "/api/v1/investors",
        json=_body(),
        headers={**_auth(subscriber), "Accept-Language": "en"},
    )
    assert resp.status_code == 402
    assert "€12.50" in resp.json()["detail"]


# ── One count, on the account that holds the licence ────────────────────────────


async def test_the_count_is_reported_once_on_the_subscriber(client, db, monkeypatch):
    subscriber = await _subscriber(db)
    colleague = await _colleague(db)
    await _register(db)
    await _register(db)
    await _register(db, status=kyc.REFUSED)

    counted = await license_service.billable_investor_counts(db, TEST_FIRM)
    assert counted == {TEST_FIRM: 2}

    listing = await client.get(
        "/internal/managers", headers={"X-Internal-Key": INTERNAL_KEY}
    )
    reported = {row["id"]: row["managed_count"] for row in listing.json()}
    assert reported[str(subscriber.id)] == 2
    assert reported[str(colleague.id)] == 0, "a colleague holds no licence to bill"


# ── A blocked licence ───────────────────────────────────────────────────────────


async def test_a_suspended_firm_refuses_its_team_and_keeps_its_investors(
    client, db, monkeypatch
):
    _console(monkeypatch, _licence(is_blocked=True))
    subscriber = await _subscriber(db)
    colleague = await _colleague(db)
    holder_of_units = await _account(db, role=INVESTOR, firm=TEST_FIRM)
    investor = await _register(db)
    investor.user_id = holder_of_units.id
    await db.flush()

    team = await client.get("/api/v1/investors", headers=_auth(colleague))
    assert team.status_code == 401
    assert team.headers.get("X-Error-Code") == licence_state.AGENCY_SUSPENDED

    # The subscriber comes in, reaches « Mon abonnement » and nothing else.
    elsewhere = await client.get("/api/v1/investors", headers=_auth(subscriber))
    assert elsewhere.status_code == 403
    assert elsewhere.headers.get("X-Error-Code") == licence_state.SUBSCRIPTION_SUSPENDED
    assert (
        await client.get("/api/v1/billing", headers=_auth(subscriber))
    ).status_code == 200
    me = await client.get("/api/v1/auth/me", headers=_auth(subscriber))
    assert me.status_code == 200 and me.json()["subscription_suspended"] is True

    # The investors keep their space.
    own = await client.get("/api/v1/investors/me", headers=_auth(holder_of_units))
    assert own.status_code == 200

    # And the colleague's sign-in says why, in a sentence.
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": colleague.email, "password": "Motdepasse-1234"},
    )
    assert login.status_code == 401
    assert login.headers.get("X-Error-Code") == licence_state.AGENCY_SUSPENDED
    assert "suspendu" in login.json()["detail"]


async def test_a_terminated_licence_keeps_the_subscriber_on_his_subscription(
    client, db, monkeypatch
):
    """The owner, 9 Nov 2026 (« oui fais le »): once the termination has run out, the
    subscriber keeps « Mon abonnement », and that screen alone, exactly as the subscriber of
    a suspended firm: his invoices and credit notes, what is still due, subscribing again.
    He signs in; anywhere else he is refused with `licence_ended`, so the screen tells an
    ended subscription from a suspension. The team stays refused."""
    ended = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    _console(monkeypatch, _licence(is_blocked=True, access_until=ended))
    subscriber = await _subscriber(db)
    colleague = await _colleague(db)

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": subscriber.email, "password": "Motdepasse-1234"},
    )
    assert login.status_code == 200, login.text

    billing = await client.get("/api/v1/billing", headers=_auth(subscriber))
    assert billing.status_code == 200, billing.text
    assert billing.json()["ended"] is True
    assert billing.json()["suspended"] is False
    me = await client.get("/api/v1/auth/me", headers=_auth(subscriber))
    assert me.status_code == 200
    assert me.json()["subscription_ended"] is True
    assert me.json()["subscription_suspended"] is False

    elsewhere = await client.get("/api/v1/investors", headers=_auth(subscriber))
    assert elsewhere.status_code == 403
    assert elsewhere.headers.get("X-Error-Code") == licence_state.LICENCE_ENDED
    assert "pris fin" in elsewhere.json()["detail"]

    team = await client.get("/api/v1/billing", headers=_auth(colleague))
    assert team.status_code == 401
    assert team.headers.get("X-Error-Code") == licence_state.LICENCE_ENDED
    refused = await client.post(
        "/api/v1/auth/login",
        json={"email": colleague.email, "password": "Motdepasse-1234"},
    )
    assert refused.status_code == 401
    assert refused.headers.get("X-Error-Code") == licence_state.LICENCE_ENDED


async def test_the_suspended_and_the_ended_subscriber_share_one_rule():
    """ONE rule holds the subscriber to « Mon abonnement », whatever the reason."""
    import inspect

    from app.api import deps

    source = inspect.getsource(deps.current_user)
    assert source.count("licence_state.held_subscriber_may_reach") == 1
    assert not hasattr(licence_state, "suspended_subscriber_may_reach")


async def test_a_terminated_licence_keeps_its_investors(client, db, monkeypatch):
    """The owner, 9 Nov 2026: a closed licence leaves the end users their access, in every
    tool, exactly as a suspension does. The investors sign in and keep their space; the
    team stays refused."""
    ended = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    _console(monkeypatch, _licence(is_blocked=True, access_until=ended))
    colleague = await _colleague(db)
    holder_of_units = await _account(db, role=INVESTOR, firm=TEST_FIRM)
    investor = await _register(db)
    investor.user_id = holder_of_units.id
    await db.flush()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": holder_of_units.email, "password": "Motdepasse-1234"},
    )
    assert login.status_code == 200, login.text
    own = await client.get("/api/v1/investors/me", headers=_auth(holder_of_units))
    assert own.status_code == 200
    me = await client.get("/api/v1/auth/me", headers=_auth(holder_of_units))
    assert me.status_code == 200

    team = await client.get("/api/v1/investors", headers=_auth(colleague))
    assert team.status_code == 401
    assert team.headers.get("X-Error-Code") == licence_state.LICENCE_ENDED


async def test_block_switches_nobody_off_and_speaks_alices_key(client, db):
    subscriber = await _subscriber(db)
    await _colleague(db)
    key = {"X-Internal-Key": INTERNAL_KEY}
    resp = await client.post(f"/internal/managers/{subscriber.id}/block", headers=key)
    assert resp.status_code == 200
    assert resp.json()["blocked_user_ids"] == []
    await db.refresh(subscriber)
    assert subscriber.is_active is True


async def test_unblock_brings_back_a_subscriber_an_old_block_switched_off(client, db):
    """Before 8 Nov the block switched the subscriber off and answered under a key Alice
    did not read: her unblock came with an empty list and the account stayed off."""
    subscriber = await _account(db, id=TEST_FIRM, is_active=False)
    await _colleague(db)
    resp = await client.post(
        f"/internal/managers/{subscriber.id}/unblock",
        headers={"X-Internal-Key": INTERNAL_KEY},
        json={"user_ids": []},
    )
    assert resp.status_code == 204
    await db.refresh(subscriber)
    assert subscriber.is_active is True


async def test_block_and_unblock_drop_the_licence_kept_in_memory(client, db):
    subscriber = await _subscriber(db)
    alice_client._licence_cache[subscriber.id] = (10**12, {"is_blocked": False})
    await client.post(
        f"/internal/managers/{subscriber.id}/block",
        headers={"X-Internal-Key": INTERNAL_KEY},
    )
    assert subscriber.id not in alice_client._licence_cache


# ── « Mon abonnement » and Alice's refusals ─────────────────────────────────────


@pytest.fixture
def alice(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ALICE_URL", "http://alice.test/")
    monkeypatch.setattr(settings, "ALICE_API_KEY", "cle-sortante-de-test")
    answers: dict[str, httpx.Response] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        return answers.get(request.url.path, httpx.Response(404, json={}))

    real = httpx.AsyncClient

    def _client(*args, **kwargs):
        return real(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(alice_client.httpx, "AsyncClient", _client)
    return answers


async def test_the_subscription_relays_alices_calendar(client, db, alice):
    subscriber = await _subscriber(db)
    alice[f"/api/v1/internal/license/{TEST_FIRM}"] = httpx.Response(
        200,
        json=_licence(
            billing_starts_on="2027-01-01",
            has_payment_method=False,
            payment_failed_on=None,
            suspension_on=None,
        ),
    )
    body = (await client.get("/api/v1/billing", headers=_auth(subscriber))).json()
    assert body["billing_starts_on"] == "2027-01-01"
    assert body["has_payment_method"] is False
    assert body["is_holder"] is True
    assert body["unavailable"] is False


async def test_an_older_alice_without_the_calendar_is_read_as_silence(
    client, db, alice
):
    subscriber = await _subscriber(db)
    alice[f"/api/v1/internal/license/{TEST_FIRM}"] = httpx.Response(
        200, json=_licence()
    )
    body = (await client.get("/api/v1/billing", headers=_auth(subscriber))).json()
    assert body["billing_starts_on"] is None
    assert body["has_payment_method"] is None


async def test_an_alice_that_fails_is_said_unavailable(client, db, alice):
    subscriber = await _subscriber(db)
    alice[f"/api/v1/internal/license/{TEST_FIRM}"] = httpx.Response(500, json={})
    body = (await client.get("/api/v1/billing", headers=_auth(subscriber))).json()
    assert body["unavailable"] is True


async def test_alices_own_sentence_never_reaches_the_subscriber(client, db, alice):
    subscriber = await _subscriber(db)
    alice[f"/api/v1/internal/billing/portal/{TEST_FIRM}"] = httpx.Response(
        401, json={"detail": "Clé interne invalide"}
    )
    resp = await client.post("/api/v1/billing/portal", headers=_auth(subscriber))
    assert resp.status_code == 503
    assert "Clé" not in resp.json()["detail"]
    assert "facturation" in resp.json()["detail"]


async def test_alices_terms_refusal_is_said_clearly(client, db, alice, monkeypatch):
    subscriber = await _subscriber(db)

    async def _nothing_owed(*_a, **_k):
        return {"cgu": None, "cgv": None, "dpa": None}

    monkeypatch.setattr(alice_client, "terms_status", _nothing_owed)
    alice[f"/api/v1/internal/billing/checkout/{TEST_FIRM}"] = httpx.Response(
        409,
        json={"detail": "CGV v3 non acceptées"},
        headers={"X-Refusal": "terms_cgv"},
    )
    resp = await client.post(
        "/api/v1/billing/checkout", headers=_auth(subscriber), json={}
    )
    assert resp.status_code == 409
    assert "conditions générales de vente" in resp.json()["detail"]


async def test_paying_the_plan_in_place_asks_the_terms_still_owed(
    client, db, alice, monkeypatch
):
    subscriber = await _subscriber(db)

    async def _owed(*_a, **_k):
        return {
            "cgv": {"version": "3", "anything_to_accept": True, "up_to_date": False},
            "dpa": None,
        }

    monkeypatch.setattr(alice_client, "terms_status", _owed)
    resp = await client.post(
        "/api/v1/billing/checkout", headers=_auth(subscriber), json={}
    )
    assert resp.status_code == 422
