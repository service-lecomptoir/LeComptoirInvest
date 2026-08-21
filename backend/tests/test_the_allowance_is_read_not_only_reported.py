"""The plan's investor ceiling, and the two doors a register grows through.

🔴 WHAT THIS FILE EXISTS FOR. Until now this product REPORTED `managed_count` to the console
and DISPLAYED `managed_limit` on the subscription screen, and nothing in between ever
compared the two numbers. A fund on a plan of fifty could register five hundred investors,
and the only trace was on the invoice. A rule written down and applied nowhere is the defect
this repository keeps paying for; a guard with no test is the same defect one step later.

WHAT IS GUARDED HERE, none of which looks wrong on screen when it goes the other way:

  * the guard and the invoice count THE SAME THING, because they call the same function;
  * an unreachable console is not an unlimited plan;
  * a fund with NO console at all is not blocked — that is a legitimate way to run this;
  * the 402 announces the COUNT and the PRICE, so nobody meets a supplement on an invoice;
  * and un-refusing a KYC file is the SECOND door: it makes a free investor billable, and a
    guard that only watched registration would have left it wide open.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.core import kyc
from app.core.security import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.models.investor import Investor
from app.models.user import MANAGER, User
from tests.conftest import TEST_FIRM
from app.services import alice_client, license_service

#: The console's shared key, set for the duration of the fixture: one test here reads the
#: `/internal` contract to prove the guard and the invoice count the same thing.
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


async def _manager(db) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"gerant-{uuid.uuid4().hex[:8]}@fonds.fr",
        hashed_password=hash_password("Motdepasse-1234"),
        account_name="Meridian Capital",
        # ⚠️ THE ACCOUNT BELONGS TO THE SUITE'S FIRM, and it has to be said out loud.
        # `firm_of()` reads `COALESCE(firm_id, id)`, so an account left without a firm
        # points at ITSELF -- a firm of one, which owns none of the rows this file creates
        # under `TEST_FIRM`. The screens would then answer 404 for data sitting right
        # there, and the failure would look like the route rather than the fixture.
        firm_id=TEST_FIRM,
        role=MANAGER,
    )
    db.add(user)
    await db.flush()
    return user


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


def _licence(*, limit: int | None, overage: float | None = None) -> dict:
    """A licence exactly as Alice's `/internal/license/{id}` sends one."""
    return {
        "managed_limit": limit,
        "overage_price": overage,
        "overage_allowed": bool(overage),
        "plan_name": "Fonds 50",
        "is_blocked": False,
    }


def _console(monkeypatch, licence: dict | None, *, configured: bool = True) -> None:
    async def _get(_user_id, *, strict: bool = False):
        return licence

    monkeypatch.setattr(alice_client, "console_configured", lambda: configured)
    monkeypatch.setattr(alice_client, "get_license", _get)


def _body(kind: str = "personne") -> dict:
    return {"kind": kind, "first_name": "Grace", "last_name": "Hopper"}


# ── The quantity ─────────────────────────────────────────────────────────────────


async def test_the_guard_and_the_invoice_count_the_same_thing(client, db, monkeypatch):
    """🔴 ONE FUNCTION, TWO READERS. The console reads the count through
    `/internal/managers`; the guard reads it through `license_service`. They used to be two
    `select(count())` in two files, which is right on the day it is written and wrong at the
    first change to either — a fund refused at forty-nine while billed for fifty-one, each
    number defensible on its own.
    """
    await _register(db)
    await _register(db)
    await _register(db, status=kyc.REFUSED)
    manager = await _manager(db)

    counted = await license_service.count_investors(db)
    assert counted == 2, "a refused file is not an investor under management"

    key = {"X-Internal-Key": INTERNAL_KEY}
    listing = await client.get("/internal/managers", headers=key)
    assert listing.status_code == 200
    reported = {row["managed_count"] for row in listing.json()}
    assert reported == {counted}

    # 🔴 AND THE SINGLE-MANAGER ROUTE TOO. It answered 0 for every account — the default of
    # a Pydantic field, in the exact shape of a real answer. Only the listing is read for
    # billing today; a second reader would have been billed on nothing.
    one = await client.get(f"/internal/managers/{manager.id}", headers=key)
    assert one.status_code == 200
    assert one.json()["managed_count"] == counted


# ── The ceiling ──────────────────────────────────────────────────────────────────


async def test_within_the_allowance_nothing_is_asked(client, db, monkeypatch):
    _console(monkeypatch, _licence(limit=5))
    manager = await _manager(db)
    resp = await client.post("/api/v1/investors", json=_body(), headers=_auth(manager))
    assert resp.status_code == 201


async def test_an_unlimited_plan_is_a_null_ceiling_not_a_zero(client, db, monkeypatch):
    """⚠️ `None` IS A VALUE ON THIS WIRE. « Unlimited » travels as null, and a reader that
    treated null as « nothing allowed » would block every fund on the largest plan."""
    _console(monkeypatch, _licence(limit=None))
    manager = await _manager(db)
    for _ in range(3):
        await _register(db)
    resp = await client.post("/api/v1/investors", json=_body(), headers=_auth(manager))
    assert resp.status_code == 201


async def test_the_ceiling_reached_without_overage_refuses_and_says_where_to_go(
    client, db, monkeypatch
):
    """A plan that forbids the overage refuses in 400 — and names the way out. A bare
    refusal would leave a manager retrying the same form."""
    _console(monkeypatch, _licence(limit=2))
    await _register(db)
    await _register(db)
    manager = await _manager(db)

    resp = await client.post("/api/v1/investors", json=_body(), headers=_auth(manager))
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "2/2" in detail
    assert "offre" in detail.lower()


async def test_the_ceiling_reached_with_overage_asks_and_announces_the_price(
    client, db, monkeypatch
):
    """🔴 402 IS A QUESTION, NOT A FAILURE, and the price is in it.

    The fund pays for the right to exceed its plan; refusing outright would deny something
    it bought. But adding an investor that silently costs 12 €/month more is the one
    outcome this module exists to prevent, so the count AND the price are announced before
    anybody consents.
    """
    _console(monkeypatch, _licence(limit=2, overage=12.0))
    await _register(db)
    await _register(db)
    manager = await _manager(db)

    asked = await client.post("/api/v1/investors", json=_body(), headers=_auth(manager))
    assert asked.status_code == 402
    detail = asked.json()["detail"]
    assert "2/2" in detail
    assert "12" in detail, "the price must be in the sentence, not only in the plan"

    # Nothing was written while the question was pending.
    assert await license_service.count_investors(db) == 2

    said_yes = await client.post(
        "/api/v1/investors?accept_overage=true", json=_body(), headers=_auth(manager)
    )
    assert said_yes.status_code == 201
    assert await license_service.count_investors(db) == 3


# ── The console ──────────────────────────────────────────────────────────────────


async def test_no_console_at_all_is_not_a_ceiling_of_zero(client, db, monkeypatch):
    """⚠️ A FUND HOSTED ON ITS OWN IS A LEGITIMATE STATE. There is no console, no plan and
    no ceiling: the register must work. This is decided on CONFIGURATION, never on a call
    that failed."""
    _console(monkeypatch, None, configured=False)
    manager = await _manager(db)
    for _ in range(9):
        await _register(db)
    resp = await client.post("/api/v1/investors", json=_body(), headers=_auth(manager))
    assert resp.status_code == 201


async def test_an_unreachable_console_is_not_an_unlimited_plan(client, db, monkeypatch):
    """🔴 THE FAILURE MODE THAT WOULD NEVER HAVE BEEN NOTICED.

    Everything else in `alice_client` degrades softly, on purpose: a subscription panel that
    cannot reach the console shows « unknown » and the fund keeps running. A QUOTA that
    degrades softly answers « fine » to every request for as long as the outage lasts, and
    every capped plan becomes uncapped without one line in a log.
    """

    async def _down(_user_id, *, strict: bool = False):
        if strict:
            raise alice_client.AliceUnavailable(
                "Le service d'abonnement est momentanément indisponible."
            )
        return None

    monkeypatch.setattr(alice_client, "console_configured", lambda: True)
    monkeypatch.setattr(alice_client, "get_license", _down)
    manager = await _manager(db)

    resp = await client.post("/api/v1/investors", json=_body(), headers=_auth(manager))
    assert resp.status_code == 503
    assert "indisponible" in resp.json()["detail"].lower()


async def test_a_console_that_knows_no_such_account_refuses(client, db, monkeypatch):
    """A configured console answering 404 means nobody sold this account a plan. Letting it
    through would be an entitlement granted by an absence."""
    _console(monkeypatch, None, configured=True)
    manager = await _manager(db)
    resp = await client.post("/api/v1/investors", json=_body(), headers=_auth(manager))
    assert resp.status_code == 403


# ── The second door ──────────────────────────────────────────────────────────────


async def test_un_refusing_a_file_goes_through_the_allowance_too(
    client, db, monkeypatch
):
    """🔴 THE DOOR THAT DOES NOT LOOK LIKE ONE.

    A refused file is not billed. Reversing that refusal makes it billable again — so a fund
    at its ceiling could refuse a hundred people and un-refuse them one at a time, for free,
    without ever calling `POST /investors`. Guarding registration alone is this repository's
    oldest defect written once more: a fix placed at one site out of N.
    """
    _console(monkeypatch, _licence(limit=2, overage=12.0))
    await _register(db)
    await _register(db)
    refused = await _register(db, status=kyc.REFUSED)
    manager = await _manager(db)

    verdict = {"status": kyc.ACCEPTED, "reason": "Dossier complet."}
    asked = await client.post(
        f"/api/v1/investors/{refused.id}/kyc", json=verdict, headers=_auth(manager)
    )
    assert asked.status_code == 402, (
        "un-refusing at the ceiling must ask, like creating"
    )
    assert "12" in asked.json()["detail"]

    said_yes = await client.post(
        f"/api/v1/investors/{refused.id}/kyc?accept_overage=true",
        json=verdict,
        headers=_auth(manager),
    )
    assert said_yes.status_code == 200
    assert await license_service.count_investors(db) == 3


async def test_refusing_somebody_never_asks_the_console(client, db, monkeypatch):
    """⚠️ ONLY ONE DIRECTION COSTS ANYTHING.

    A verdict that refuses an investor REMOVES them from the billed quantity, and a verdict
    on a file that already counted changes nothing. Neither may fail on a subscription
    outage: a compliance decision that cannot be recorded because a billing service is down
    is a worse product than one that is billed a month late.
    """
    calls: list[str] = []

    async def _watch(_user_id, *, strict: bool = False):
        calls.append("asked")
        raise alice_client.AliceUnavailable("Indisponible.")

    monkeypatch.setattr(alice_client, "console_configured", lambda: True)
    monkeypatch.setattr(alice_client, "get_license", _watch)

    counted = await _register(db, status=kyc.PENDING)
    manager = await _manager(db)

    refusal = await client.post(
        f"/api/v1/investors/{counted.id}/kyc",
        json={"status": kyc.REFUSED, "reason": "Origine des fonds non établie."},
        headers=_auth(manager),
    )
    assert refusal.status_code == 200
    assert calls == [], "a verdict that adds nothing must not reach the console at all"


# ── The screen ───────────────────────────────────────────────────────────────────


async def test_the_screen_reads_the_guards_own_arithmetic(client, db, monkeypatch):
    """🔴 ONE FUNCTION FOR THE ANNOUNCEMENT AND THE REFUSAL. A panel promising room the
    guard denies, or a price the invoice does not charge, teaches its reader to believe
    neither."""
    _console(monkeypatch, _licence(limit=2, overage=12.0))
    await _register(db)
    await _register(db)
    manager = await _manager(db)

    seen = (await client.get("/api/v1/investors/quota", headers=_auth(manager))).json()
    assert seen["verdict"] == license_service.OVERAGE
    assert (seen["current"], seen["limit"]) == (2, 2)
    assert seen["monthly_cost"] == 12.0

    refused = await client.post(
        "/api/v1/investors", json=_body(), headers=_auth(manager)
    )
    assert refused.status_code == 402


async def test_an_unreadable_allowance_is_unknown_on_screen_never_fine(
    client, db, monkeypatch
):
    """⚠️ THE SCREEN INFORMS, IT DOES NOT ENFORCE — so it degrades where the guard raises.
    But it must degrade to « we cannot read this », never to a comfortable « ok »: the
    difference is whether the manager understands why the next registration is refused."""

    async def _down(_user_id, *, strict: bool = False):
        raise alice_client.AliceUnavailable("Indisponible.")

    monkeypatch.setattr(alice_client, "console_configured", lambda: True)
    monkeypatch.setattr(alice_client, "get_license", _down)
    manager = await _manager(db)

    seen = (await client.get("/api/v1/investors/quota", headers=_auth(manager))).json()
    assert seen["verdict"] == license_service.UNKNOWN


async def test_the_ceiling_is_read_under_alices_shared_name(db):
    """🔴 `managed_limit`, THE KEY FIVE PRODUCTS SPEAK. Read under any other name it comes
    back empty — and an empty ceiling reads as « unlimited », so every check would answer
    « fine » and nothing whatsoever would fail."""
    under_the_contract = license_service.outlook(
        {"managed_limit": 2}, current=2, adding=1
    )
    assert under_the_contract["verdict"] == license_service.BLOCKED

    # The name this platform left behind. It must NOT be understood any more.
    under_the_old_name = license_service.outlook(
        {"property_limit": 2}, current=2, adding=1
    )
    assert under_the_old_name["verdict"] == license_service.OK
    assert under_the_old_name["limit"] is None
