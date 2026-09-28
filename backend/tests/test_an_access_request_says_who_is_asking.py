"""An access request says who is asking, in the console's own words, and carries a plan.

The product owner, 28-29 Sept 2026: every Le Comptoir has a public pricing page and a
sign-up with a catalogue plan, identical to Le Comptoir RH. A club or a fund takes a
catalogue plan; a management company running several vehicles for clients is quoted. The
console already knows those notions on every product (`quote_only`, `owner_kind`,
`owner_account_name`, `owner_company_number`): this product speaks them.

🔴 WHAT IS GUARDED HERE, beyond the payload: the OUTBOUND key on every call, Alice's
answer relayed rather than a fixed « c'est enregistré », Alice's refusal said as it is, a
real failure answered 503 and never a fake success, and a limit counted per visitor.
"""

from __future__ import annotations

import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1 import public
from app.api.v1.public import AccessRequest, lead_payload
from app.config import get_settings
from app.main import app
from app.services import alice_client

OUTBOUND = "cle-sortante-de-test"
INBOUND = "cle-entrante-de-test"
LEADS = "/api/v1/internal/leads"
PLANS = "/api/v1/internal/plans"

#: What every sign-up carries, whoever asks: a phone and the whole address.
_REACHABLE = {
    "phone": "04 78 00 00 00",
    "street": "3 rue des Lilas",
    "zip_code": "69003",
    "city": "Lyon",
}


@pytest.fixture
async def client():
    public._window.clear()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://invest.test"
    ) as c:
        yield c
    public._window.clear()


@pytest.fixture
def console(monkeypatch):
    """Configure a console and answer in its place; returns the requests it received."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ALICE_URL", "http://alice.test/")
    monkeypatch.setattr(settings, "ALICE_API_KEY", OUTBOUND)
    monkeypatch.setattr(settings, "ALICE_INTERNAL_KEY", INBOUND)
    seen: list[httpx.Request] = []
    answers: dict[str, httpx.Response] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        answer = answers.get(request.url.path, httpx.Response(404))
        if isinstance(answer, Exception):
            raise answer
        return answer

    real = httpx.AsyncClient

    def _client(*args, **kwargs):
        return real(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(alice_client.httpx, "AsyncClient", _client)
    return seen, answers


@pytest.fixture
def no_console(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ALICE_URL", "")
    monkeypatch.setattr(settings, "ALICE_API_KEY", "")


def _body(**kwargs) -> dict:
    base = {
        "first_name": "Sandrine",
        "last_name": "Louis",
        "email": "sandrine@club-louis.fr",
        "plan_id": "plan-club",
        **_REACHABLE,
    }
    base.update(kwargs)
    return base


def test_a_management_company_is_a_quotation_and_a_fund_is_not():
    firm = AccessRequest(
        first_name="Camille",
        last_name="Roux",
        email="camille@roux-gestion.fr",
        profile=public.MANAGEMENT_COMPANY,
        requester_kind=public.PERSON,
        company="Roux Gestion",
        message="Quatre véhicules, trois cents investisseurs.",
        plan_id="plan-fonds",
    )
    sent = lead_payload(firm, "Roux Gestion")
    assert sent["quote_only"] is True, "several vehicles for clients: quoted"
    assert sent["plan_id"] is None, "never a catalogue price for a quotation"
    assert sent["owner_kind"] == "personne"
    assert sent["owner_account_name"] == "Camille Roux"
    assert sent["message"].startswith("Société de gestion"), "the profile is read first"
    assert sent["message"].endswith("Quatre véhicules, trois cents investisseurs.")
    assert sent["product"] == "invest" and sent["source"] == "invest_login"

    club = AccessRequest(
        email="contact@club-lyon.fr",
        profile=public.SINGLE_FUND,
        requester_kind=public.COMPANY,
        company="Club Lyon Invest",
        company_number="552 032 534",
        plan_id="plan-club",
        **_REACHABLE,
    )
    sent = lead_payload(club, "Club Lyon Invest")
    assert sent["quote_only"] is False, "a club or a fund: a catalogue plan"
    assert sent["plan_id"] == "plan-club"
    assert sent["owner_kind"] == "societe"
    assert sent["owner_account_name"] == "Club Lyon Invest"
    assert sent["owner_company"] == "Club Lyon Invest"
    assert sent["owner_company_number"] == "552 032 534"
    assert sent["message"] == "Un club ou un fonds."
    assert (sent["street"], sent["zip_code"], sent["city"]) == (
        "3 rue des Lilas",
        "69003",
        "Lyon",
    )


def test_the_sign_up_says_it_is_one_and_carries_names_region_and_country():
    person = AccessRequest(
        first_name="Sandrine",
        last_name="Louis",
        email="s@example.be",
        region="Bruxelles-Capitale",
        country="BE",
        **_REACHABLE,
    )
    sent = lead_payload(person, "")
    assert sent["kind"] == "signup"
    assert (sent["first_name"], sent["last_name"], sent["full_name"]) == (
        "Sandrine",
        "Louis",
        "Sandrine Louis",
    )
    assert (sent["region"], sent["country"]) == ("Bruxelles-Capitale", "BE")


async def test_the_plans_are_the_consoles_counted_in_investors(client, console):
    seen, answers = console
    answers[PLANS] = httpx.Response(
        200,
        json=[
            {"id": "a", "name": "Club", "managed_limit": 20, "monthly_price": 49},
            {"id": "b", "name": "Fonds", "managed_limit": 100, "monthly_price": 149},
            {"id": "c", "name": "Sur devis", "managed_limit": None, "sur_devis": True},
            {"name": "sans identifiant"},
        ],
    )
    found = (await client.get("/api/v1/public/plans")).json()

    assert [(p["name"], p["investor_limit"], p["sur_devis"]) for p in found] == [
        ("Club", 20, False),
        ("Fonds", 100, False),
        ("Sur devis", None, True),
    ], (
        "the ceiling is Alice's managed_limit, in investors; a row without an id is dropped"
    )
    assert seen[-1].url.params["product"] == "invest", "never another product's prices"
    assert seen[-1].headers["X-Internal-Key"] == OUTBOUND


async def test_a_silent_console_shows_no_plan(client, console, no_console):
    assert (await client.get("/api/v1/public/plans")).json() == []


async def test_a_broken_catalogue_shows_no_plan(client, console):
    _seen, answers = console
    answers[PLANS] = httpx.Response(200, content=b"<html>not json</html>")
    assert (await client.get("/api/v1/public/plans")).json() == []


async def test_the_screen_says_what_the_console_answered(client, console):
    """⚠️ Never a fixed « c'est enregistré »: an account that already exists must say so,
    with the way to it, or the prospect waits for an e-mail that will never come."""
    seen, answers = console
    answers[LEADS] = httpx.Response(
        201,
        json={
            "status": "account_exists",
            "message": "Un compte existe déjà avec cet e-mail sur Le Comptoir Invest.",
            "login_url": "https://invest.example/login",
            "subscription_url": "https://invest.example/billing",
        },
    )
    out = await client.post("/api/v1/public/access-request", json=_body())
    assert out.status_code == 201
    said = out.json()
    assert said["status"] == "account_exists"
    assert said["message"].startswith("Un compte existe déjà")
    assert said["login_url"] == "https://invest.example/login"
    assert said["subscription_url"] == "https://invest.example/billing"

    sent = json.loads(seen[-1].content)
    assert seen[-1].headers["X-Internal-Key"] == OUTBOUND, "the OUTBOUND key"
    assert sent["plan_id"] == "plan-club" and sent["product"] == "invest"

    answers[LEADS] = httpx.Response(201, json={"status": "confirmation_sent"})
    said = (await client.post("/api/v1/public/access-request", json=_body())).json()
    assert said["status"] == "confirmation_sent"
    assert "confirmation" in said["message"], "a status without its sentence gets ours"


async def test_an_english_reader_is_not_handed_the_consoles_french(client, console):
    _seen, answers = console
    answers[LEADS] = httpx.Response(
        201,
        json={"status": "confirmation_sent", "message": "Un e-mail vient de partir."},
    )
    said = (
        await client.post(
            "/api/v1/public/access-request",
            json=_body(),
            headers={"Accept-Language": "en"},
        )
    ).json()
    assert said["status"] == "confirmation_sent"
    assert said["message"].startswith("A confirmation e-mail")


async def test_the_consoles_refusal_is_said_as_it_is(client, console):
    """« Indiquez votre prénom et votre nom. » comes from the console, for every product."""
    _seen, answers = console
    answers[LEADS] = httpx.Response(
        422, json={"detail": "Indiquez votre prénom et votre nom."}
    )
    out = await client.post("/api/v1/public/access-request", json=_body(last_name=""))
    assert out.status_code == 400
    assert out.json()["detail"] == "Indiquez votre prénom et votre nom."


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(500, json={"detail": "boom"}),
        httpx.Response(422, json={"detail": [{"msg": "field required"}]}),
        httpx.ConnectError("down"),
    ],
)
async def test_a_failure_is_never_a_fake_success(client, console, failure):
    _seen, answers = console
    answers[LEADS] = failure
    out = await client.post("/api/v1/public/access-request", json=_body())
    assert out.status_code == 503
    assert "contact@lecomptoir.services" in out.json()["detail"]


async def test_without_a_console_the_request_is_refused_and_says_where_to_write(
    client, no_console
):
    out = await client.post("/api/v1/public/access-request", json=_body())
    assert out.status_code == 503
    assert "contact@lecomptoir.services" in out.json()["detail"]


async def test_an_unknown_profile_is_refused_before_the_console_is_asked(
    client, console
):
    seen, _answers = console
    out = await client.post(
        "/api/v1/public/access-request", json=_body(profile="autre")
    )
    assert out.status_code == 400
    assert seen == [], "nothing reached the console"


async def test_the_limit_counts_each_visitor_not_the_gateway(client, no_console):
    """Behind the edge proxy every request comes from the proxy: counted on the socket,
    all visitors shared one window. The last `X-Forwarded-For` hop is the visitor."""
    robot = {"X-Forwarded-For": "203.0.113.7"}
    for _ in range(public.SIGNUPS_PER_MINUTE):
        out = await client.post(
            "/api/v1/public/access-request", json=_body(), headers=robot
        )
        assert out.status_code == 503  # admitted, then refused for want of a console
    stopped = await client.post(
        "/api/v1/public/access-request", json=_body(), headers=robot
    )
    assert stopped.status_code == 429

    neighbour = await client.post(
        "/api/v1/public/access-request",
        json=_body(),
        headers={"X-Forwarded-For": "198.51.100.9"},
    )
    assert neighbour.status_code == 503, "another visitor behind the same proxy"
