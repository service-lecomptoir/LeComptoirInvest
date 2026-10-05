"""The terms of use and of sale are asked, accepted and read back through Alice.

The manager, 2 Oct 2026: every account that signs in accepts the terms of use for itself,
the subscriber alone accepts the terms of sale, and Alice holds the texts and the proof.
This product relays, with its OUTBOUND key, and keeps nothing.

🔴 WHAT IS GUARDED HERE:
  * the sign-up hands Alice the versions ticked, with the BROWSER's address and user agent,
    and a form sent without the box is refused with Alice's own sentence;
  * an acceptance names this account, the document, the version shown, the language, the
    browser, `method=update`; the terms of sale are refused to anyone but the subscriber;
    Alice's 409 reaches the screen;
  * the status says `pending` from Alice's answer, asks the terms of sale for the
    subscriber only, and asks under the role's own word;
  * 🔴 AN ALICE OUTAGE LOCKS NOBODY OUT (status `unavailable`, nothing pending), and
    refuses a new sign-up (503): fail open for the accounts, closed for the door;
  * the platform's operator is never asked;
  * a plan change accepts the terms of sale first, and is stopped by a refusal.
"""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1 import public
from app.config import get_settings
from app.core.security import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.models.user import ADMIN, INVESTOR, MANAGER, User
from app.services import alice_client

OUTBOUND = "cle-sortante-de-test"
TERMS = "/api/v1/terms"
LEADS = "/api/v1/internal/leads"
BROWSER = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)"
#: The edge proxy appends the address it saw: the last hop is the person's.
FORWARDED = {"X-Forwarded-For": "203.0.113.9", "User-Agent": BROWSER}


@pytest.fixture
async def client(db):
    async def _db():
        yield db

    public._window.clear()
    app.dependency_overrides[get_db] = _db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://invest.test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    public._window.clear()


@pytest.fixture
def alice(monkeypatch):
    """Answer in Alice's place: `answers[path]` is a response, or an exception to raise."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ALICE_URL", "http://alice.test/")
    monkeypatch.setattr(settings, "ALICE_API_KEY", OUTBOUND)
    seen: list[httpx.Request] = []
    answers: dict[str, httpx.Response | Exception] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        answer = answers.get(request.url.path, httpx.Response(404, json={}))
        if isinstance(answer, Exception):
            raise answer
        return answer

    real = httpx.AsyncClient

    def _client(*args, **kwargs):
        return real(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(alice_client.httpx, "AsyncClient", _client)
    return seen, answers


async def _user(db, role: str, firm_id: uuid.UUID | None = None) -> User:
    user = User(
        id=uuid.uuid4(),
        firm_id=firm_id,
        email=f"{role}-{uuid.uuid4().hex[:8]}@fonds.test",
        hashed_password=hash_password("Motdepasse-1234"),
        account_name="Meridian Capital",
        role=role,
    )
    db.add(user)
    await db.flush()
    return user


def _auth(user: User) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(str(user.id), user.role)}",
        **FORWARDED,
    }


def _status_path(user: User) -> str:
    return f"{TERMS}/accounts/invest/{user.id}/status"


def _document(version: str, *, up_to_date: bool, accepted: str | None = None) -> dict:
    return {
        "version": version,
        "product": "invest",
        "audience": "manager",
        "effective_from": "2026-10-01",
        "accepted_version": accepted,
        "accepted_at": "2026-09-02T08:15:00+00:00" if accepted else None,
        "up_to_date": up_to_date,
        "anything_to_accept": True,
    }


_SIGNUP = {
    "first_name": "Sandrine",
    "last_name": "Louis",
    "email": "sandrine@club-louis.fr",
    "plan_id": "plan-club",
    "phone": "04 78 00 00 00",
    "street": "3 rue des Lilas",
    "zip_code": "69003",
    "city": "Lyon",
}


def _lead(seen: list[httpx.Request]) -> httpx.Request:
    """The request that reached Alice's leads route, not the sentence lookup that may follow."""
    return next(r for r in reversed(seen) if r.url.path == LEADS)


# ── 1. The sign-up ─────────────────────────────────────────────────────────────────────


async def test_the_sign_up_hands_alice_the_ticks_and_the_browser(client, alice):
    seen, answers = alice
    answers[LEADS] = httpx.Response(201, json={"status": "confirmation_sent"})
    resp = await client.post(
        "/api/v1/public/access-request",
        json={
            **_SIGNUP,
            "terms": {"cgu": "2026-10", "cgv": "2026-09", "language": "en"},
        },
        headers=FORWARDED,
    )
    assert resp.status_code == 201, resp.text
    lead = _lead(seen)
    sent = json.loads(lead.content)
    assert lead.headers["X-Internal-Key"] == OUTBOUND
    assert sent["terms"] == {
        "language": "en",
        "audience": "manager",
        "account_kind": "manager",
        "cgu": "2026-10",
        "cgv": "2026-09",
        "ip": "203.0.113.9",
        "user_agent": BROWSER,
    }


async def test_a_quotation_carries_no_terms_of_sale(client, alice):
    seen, answers = alice
    answers[LEADS] = httpx.Response(201, json={"status": "received"})
    await client.post(
        "/api/v1/public/access-request",
        json={
            **_SIGNUP,
            "profile": public.MANAGEMENT_COMPANY,
            "message": "Quatre véhicules.",
            "terms": {"cgu": "2026-10", "cgv": "2026-09", "language": "fr"},
        },
        headers=FORWARDED,
    )
    sent = json.loads(_lead(seen).content)
    assert sent["terms"]["cgu"] == "2026-10"
    assert sent["terms"]["cgv"] is None, "a quotation takes no licence"


async def test_a_sign_up_without_the_box_is_refused_in_alices_words(client, alice):
    seen, answers = alice
    refusal = "Acceptez les conditions générales d'utilisation pour créer votre compte."
    answers[LEADS] = httpx.Response(422, json={"detail": refusal})
    resp = await client.post(
        "/api/v1/public/access-request", json=_SIGNUP, headers=FORWARDED
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == refusal
    sent = json.loads(_lead(seen).content)
    assert sent["terms"]["cgu"] is None and sent["terms"]["cgv"] is None


async def test_terms_changed_during_the_sign_up_are_a_409(client, alice):
    _, answers = alice
    stale = "Les conditions ont changé pendant votre saisie : rechargez la page."
    answers[LEADS] = httpx.Response(409, json={"detail": stale})
    resp = await client.post(
        "/api/v1/public/access-request",
        json={**_SIGNUP, "terms": {"cgu": "2026-01", "language": "fr"}},
        headers=FORWARDED,
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == stale


async def test_the_form_reads_the_text_a_newcomer_is_asked(client, alice):
    seen, answers = alice
    answers[f"{TERMS}/current"] = httpx.Response(
        200,
        json={
            "kind": "cgu",
            "version": "2026-10",
            "title": "Conditions générales d'utilisation",
            "body": "Article 1",
            "fell_back": False,
        },
    )
    resp = await client.get(
        "/api/v1/public/terms", params={"kind": "cgu", "language": "en"}
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == "2026-10"
    asked = seen[-1].url.params
    assert (asked["kind"], asked["audience"], asked["newcomer"], asked["language"]) == (
        "cgu",
        "manager",
        "true",
        "en",
    )
    await client.get("/api/v1/public/terms", params={"kind": "cgv"})
    assert seen[-1].url.params["audience"] == "all", (
        "one text of sale for every account"
    )


async def test_nothing_published_is_no_box(client, alice):
    _, answers = alice
    answers[f"{TERMS}/current"] = httpx.Response(404, json={"detail": "Aucune version"})
    resp = await client.get("/api/v1/public/terms", params={"kind": "cgv"})
    assert resp.status_code == 404


# ── 2. Accepting ───────────────────────────────────────────────────────────────────────


async def test_an_acceptance_names_the_account_the_version_and_the_browser(
    client, db, alice
):
    seen, answers = alice
    investor = await _user(db, INVESTOR)
    answers[f"{TERMS}/accept"] = httpx.Response(
        201,
        json={"recorded": True, "already": False, "kind": "cgu", "version": "2026-10"},
    )
    resp = await client.post(
        "/api/v1/terms/accept",
        json={"kind": "cgu", "version": "2026-10", "language": "en"},
        headers=_auth(investor),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["version"] == "2026-10"
    assert seen[-1].headers["X-Internal-Key"] == OUTBOUND
    assert json.loads(seen[-1].content) == {
        "account_product": "invest",
        "account_id": str(investor.id),
        "account_kind": "investor",
        "account_email": investor.email,
        "kind": "cgu",
        "audience": "investor",
        "version": "2026-10",
        "language": "en",
        "method": "update",
        "ip_address": "203.0.113.9",
        "user_agent": BROWSER,
    }


async def test_the_terms_of_sale_are_the_subscribers_alone(client, db, alice):
    seen, answers = alice
    answers[f"{TERMS}/accept"] = httpx.Response(201, json={"recorded": True})
    subscriber = await _user(db, MANAGER)
    colleague = await _user(db, MANAGER, firm_id=subscriber.id)
    investor = await _user(db, INVESTOR, firm_id=subscriber.id)
    body = {"kind": "cgv", "version": "2026-09", "language": "fr"}
    for somebody_else in (colleague, investor):
        resp = await client.post(
            "/api/v1/terms/accept", json=body, headers=_auth(somebody_else)
        )
        assert resp.status_code == 403, somebody_else.role
    assert not seen, "nothing reaches Alice for an account that does not pay"

    resp = await client.post(
        "/api/v1/terms/accept", json=body, headers=_auth(subscriber)
    )
    assert resp.status_code == 201
    sent = json.loads(seen[-1].content)
    assert (sent["kind"], sent["audience"], sent["account_kind"]) == (
        "cgv",
        "all",
        "manager",
    )


async def test_a_stale_page_is_told_in_alices_words(client, db, alice):
    _, answers = alice
    manager = await _user(db, MANAGER)
    stale = "Les conditions ont changé : la version à accepter est « 2026-11 »."
    answers[f"{TERMS}/accept"] = httpx.Response(409, json={"detail": stale})
    resp = await client.post(
        "/api/v1/terms/accept",
        json={"kind": "cgu", "version": "2026-10", "language": "fr"},
        headers=_auth(manager),
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == stale.replace(" :", " :")


async def test_an_acceptance_alice_did_not_record_is_said(client, db, alice):
    _, answers = alice
    manager = await _user(db, MANAGER)
    answers[f"{TERMS}/accept"] = httpx.ConnectError("refused")
    resp = await client.post(
        "/api/v1/terms/accept",
        json={"kind": "cgu", "version": "2026-10", "language": "fr"},
        headers=_auth(manager),
    )
    assert resp.status_code == 502
    assert "n'a pas pu être enregistrée" in resp.json()["detail"]


# ── 3. The status ──────────────────────────────────────────────────────────────────────


async def test_a_new_version_is_pending_and_accepting_it_unblocks(client, db, alice):
    seen, answers = alice
    manager = await _user(db, MANAGER)
    answers[_status_path(manager)] = httpx.Response(
        200,
        json={
            "cgu": _document("2026-11", up_to_date=False, accepted="2026-10"),
            "cgv": _document("2026-09", up_to_date=True, accepted="2026-09"),
        },
    )
    body = (await client.get("/api/v1/terms/status", headers=_auth(manager))).json()
    assert body["unavailable"] is False
    assert body["cgu"]["pending"] is True and body["cgu"]["version"] == "2026-11"
    assert body["cgu"]["accepted_version"] == "2026-10"
    assert body["cgv"]["pending"] is False
    assert body["subscriber"] is True
    assert seen[-1].url.params["subscriber"] == "true"
    assert seen[-1].url.params["audience"] == "manager"

    answers[_status_path(manager)] = httpx.Response(
        200,
        json={
            "cgu": _document("2026-11", up_to_date=True, accepted="2026-11"),
            "cgv": _document("2026-09", up_to_date=True, accepted="2026-09"),
        },
    )
    body = (await client.get("/api/v1/terms/status", headers=_auth(manager))).json()
    assert body["cgu"]["pending"] is False


async def test_only_the_subscriber_is_asked_the_terms_of_sale(client, db, alice):
    seen, answers = alice
    subscriber = await _user(db, MANAGER)
    colleague = await _user(db, MANAGER, firm_id=subscriber.id)
    investor = await _user(db, INVESTOR, firm_id=subscriber.id)
    for account in (colleague, investor):
        answers[_status_path(account)] = httpx.Response(
            200, json={"cgu": _document("2026-10", up_to_date=False), "cgv": None}
        )
        body = (await client.get("/api/v1/terms/status", headers=_auth(account))).json()
        assert body["cgv"] is None and body["subscriber"] is False
        assert body["cgu"]["pending"] is True
        assert seen[-1].url.params["subscriber"] == "false"
    assert seen[-1].url.params["audience"] == "investor", "the word follows the role"


# ── 4. An Alice outage ─────────────────────────────────────────────────────────────────


async def test_an_outage_locks_nobody_out(client, db, alice):
    _, answers = alice
    manager = await _user(db, MANAGER)
    answers[_status_path(manager)] = httpx.ConnectError("down")
    body = (await client.get("/api/v1/terms/status", headers=_auth(manager))).json()
    assert body == {"cgu": None, "cgv": None, "unavailable": True, "subscriber": True}

    answers[f"{TERMS}/accounts/invest/{manager.id}/history"] = httpx.Response(503)
    body = (await client.get("/api/v1/terms/history", headers=_auth(manager))).json()
    assert body == {"entries": [], "unavailable": True}


async def test_an_outage_closes_the_door_to_a_new_sign_up(client, alice):
    _, answers = alice
    answers[f"{TERMS}/current"] = httpx.ConnectError("down")
    resp = await client.get("/api/v1/public/terms", params={"kind": "cgu"})
    assert resp.status_code == 503
    answers[LEADS] = httpx.ConnectError("down")
    resp = await client.post(
        "/api/v1/public/access-request",
        json={**_SIGNUP, "terms": {"cgu": "2026-10", "language": "fr"}},
        headers=FORWARDED,
    )
    assert resp.status_code == 503, "no account opens without its acceptance recorded"


# ── 5. The operator ────────────────────────────────────────────────────────────────────


async def test_the_operator_is_never_asked(client, db, alice):
    seen, _ = alice
    admin = await _user(db, ADMIN)
    body = (await client.get("/api/v1/terms/status", headers=_auth(admin))).json()
    assert body == {"cgu": None, "cgv": None, "unavailable": False, "subscriber": False}
    resp = await client.post(
        "/api/v1/terms/accept",
        json={"kind": "cgu", "version": "2026-10", "language": "fr"},
        headers=_auth(admin),
    )
    assert resp.status_code == 403
    assert not seen, "Alice is not even asked"


# ── The history ────────────────────────────────────────────────────────────────────────


async def test_the_history_is_this_accounts(client, db, alice):
    seen, answers = alice
    investor = await _user(db, INVESTOR)
    entry = {
        "kind": "cgu",
        "product": "invest",
        "audience": "investor",
        "version": "2026-10",
        "language": "fr",
        "title": "Conditions générales d'utilisation",
        "effective_from": "2026-10-01",
        "method": "update",
        "accepted_at": "2026-10-02T07:30:00+00:00",
    }
    answers[f"{TERMS}/accounts/invest/{investor.id}/history"] = httpx.Response(
        200, json=[entry]
    )
    body = (await client.get("/api/v1/terms/history", headers=_auth(investor))).json()
    assert body == {"entries": [entry], "unavailable": False}
    assert seen[-1].url.path.endswith(f"/{investor.id}/history")


# ── A plan change ──────────────────────────────────────────────────────────────────────


async def test_a_plan_change_accepts_the_terms_of_sale_first(client, db, alice):
    seen, answers = alice
    subscriber = await _user(db, MANAGER)
    change = f"/api/v1/internal/billing/change-plan/{subscriber.id}"
    answers[f"{TERMS}/accept"] = httpx.Response(201, json={"recorded": True})
    answers[change] = httpx.Response(200, json={"changed": True})
    resp = await client.post(
        "/api/v1/billing/change-plan",
        json={"plan_id": "plan-pro", "cgv": "2026-09", "language": "fr"},
        headers=_auth(subscriber),
    )
    assert resp.status_code == 200, resp.text
    paths = [r.url.path for r in seen]
    assert paths == [f"{TERMS}/accept", change], "the acceptance before the change"
    sent = json.loads(seen[0].content)
    assert (sent["kind"], sent["version"], sent["method"]) == ("cgv", "2026-09", "plan")
    assert sent["ip_address"] == "203.0.113.9"


async def test_a_plan_change_is_stopped_by_a_refusal_or_a_missing_tick(
    client, db, alice
):
    seen, answers = alice
    subscriber = await _user(db, MANAGER)
    change = f"/api/v1/internal/billing/change-plan/{subscriber.id}"
    answers[change] = httpx.Response(200, json={"changed": True})
    answers[f"{TERMS}/accept"] = httpx.Response(
        409, json={"detail": "Rechargez la page."}
    )
    resp = await client.post(
        "/api/v1/billing/change-plan",
        json={"plan_id": "plan-pro", "cgv": "2026-01", "language": "fr"},
        headers=_auth(subscriber),
    )
    assert resp.status_code == 409

    answers[_status_path(subscriber)] = httpx.Response(
        200,
        json={
            "cgu": _document("2026-10", up_to_date=True, accepted="2026-10"),
            "cgv": _document("2026-09", up_to_date=True, accepted="2026-09"),
        },
    )
    resp = await client.post(
        "/api/v1/billing/change-plan",
        json={"plan_id": "plan-pro"},
        headers=_auth(subscriber),
    )
    assert resp.status_code == 422, "terms of sale published: the tick is required"
    assert change not in [r.url.path for r in seen], "the plan never changed"
