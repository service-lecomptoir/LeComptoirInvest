"""Countries, company numbers and addresses are asked to the console, through this server.

🔴 WHAT IS GUARDED HERE. The gateway's security policy is `connect-src 'self'`: a screen
that called a register from the browser would be blocked, silently. So the screen asks
`/api/v1/public/lookups/*`, and this server relays to Alice with the OUTBOUND key -- the
one `alice_client` presents everywhere. Presenting the inbound key is the mistake this
repository already made once (`comm_config`): Alice answers 401 and nothing fails loudly.

⚠️ AND A SILENT CONSOLE IS NEVER AN ERROR ON A FORM: France alone, « unreachable », an
empty list. The form is typed by hand, it is never blocked.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1 import lookups
from app.config import get_settings
from app.main import app
from app.services import alice_client

OUTBOUND = "cle-sortante-de-test"
INBOUND = "cle-entrante-de-test"


@pytest.fixture
async def client():
    lookups._recent.clear()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://invest.test"
    ) as c:
        yield c
    lookups._recent.clear()


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
        return answers.get(request.url.path, httpx.Response(404))

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


async def test_without_a_console_every_form_still_opens(client, no_console):
    countries = await client.get("/api/v1/public/lookups/countries")
    assert countries.status_code == 200
    assert countries.json() == [
        {"code": "FR", "name": "France", "number_label": "SIREN / SIRET"}
    ]

    company = await client.get(
        "/api/v1/public/lookups/company", params={"number": "552032534"}
    )
    # « unreachable », never « not_found »: nobody looked.
    assert company.json() == {"status": "unreachable"}

    for path in ("address", "town"):
        resp = await client.get(f"/api/v1/public/lookups/{path}", params={"q": "Lyon"})
        assert resp.status_code == 200
        assert resp.json() == []


async def test_the_consoles_answer_is_passed_through_with_the_outbound_key(
    client, console
):
    seen, answers = console
    row = {
        "street": "10 Rue de la Paix",
        "zip_code": "75002",
        "city": "Paris",
        "region": "Île-de-France",
        "department": "75",
        "country": "FR",
        "label": "10 Rue de la Paix 75002 Paris",
    }
    found = {
        "status": "found",
        "name": "Meridian Capital",
        "street": "1 Quai",
        "zip_code": "69002",
        "city": "Lyon",
        "country": "FR",
        "siret": "55203253400703",
        "ape": "64.30Z",
        "legal_form": "5710",
    }
    base = "/api/v1/internal/lookups"
    answers[f"{base}/address"] = httpx.Response(200, json=[row])
    answers[f"{base}/company"] = httpx.Response(200, json=found)
    answers[f"{base}/countries"] = httpx.Response(
        200, json=[{"code": "BE", "name": "Belgique", "number_label": "BCE"}]
    )

    address = await client.get(
        "/api/v1/public/lookups/address",
        params={"q": "rue de la paix", "country": "BE"},
    )
    company = await client.get(
        "/api/v1/public/lookups/company", params={"number": "55203253400703"}
    )
    countries = await client.get("/api/v1/public/lookups/countries")

    assert address.json() == [row]
    assert company.json() == found
    assert countries.json()[0]["number_label"] == "BCE"

    by_path = {r.url.path: r for r in seen}
    assert by_path[f"{base}/address"].url.params["country"] == "BE"
    assert by_path[f"{base}/address"].url.params["q"] == "rue de la paix"
    assert by_path[f"{base}/company"].url.params["number"] == "55203253400703"
    for request in seen:
        assert request.url.host == "alice.test"
        # 🔴 The OUTBOUND key. The inbound one is what Alice shows HERE.
        assert request.headers["X-Internal-Key"] == OUTBOUND


async def test_a_town_search_defaults_to_france(client, console):
    seen, answers = console
    answers["/api/v1/internal/lookups/town"] = httpx.Response(200, json=[])
    await client.get("/api/v1/public/lookups/town", params={"q": "Annecy"})
    assert seen[-1].url.params["country"] == "FR"


@pytest.mark.parametrize(
    "for_company, for_address",
    [
        (httpx.Response(500, json={"detail": "boom"}),) * 2,
        (httpx.Response(200, content=b"<html>not json</html>"),) * 2,
        # The wrong shape: each gets what the other one should have had.
        (
            httpx.Response(200, json=[{"status": "found"}]),
            httpx.Response(200, json={"street": "1 Quai"}),
        ),
    ],
)
async def test_a_broken_answer_degrades_like_silence(
    client, console, for_company, for_address
):
    _seen, answers = console
    answers["/api/v1/internal/lookups/company"] = for_company
    answers["/api/v1/internal/lookups/address"] = for_address

    company = await client.get(
        "/api/v1/public/lookups/company", params={"number": "552032534"}
    )
    address = await client.get("/api/v1/public/lookups/address", params={"q": "Lyon"})

    assert company.status_code == 200
    assert company.json() == {"status": "unreachable"}
    assert address.status_code == 200
    assert address.json() == []


async def test_a_robot_is_stopped_and_a_neighbour_is_not(client, no_console):
    """The window is per caller, read from the edge proxy's hop: behind the proxy every
    socket has the same peer, and a per-socket window would throttle everybody at once."""
    robot = {"X-Forwarded-For": "203.0.113.7"}
    for _ in range(lookups.LOOKUPS_PER_MINUTE):
        ok = await client.get("/api/v1/public/lookups/countries", headers=robot)
        assert ok.status_code == 200

    stopped = await client.get("/api/v1/public/lookups/countries", headers=robot)
    assert stopped.status_code == 429
    assert "patientez" in stopped.json()["detail"]

    neighbour = await client.get(
        "/api/v1/public/lookups/countries", headers={"X-Forwarded-For": "198.51.100.2"}
    )
    assert neighbour.status_code == 200
