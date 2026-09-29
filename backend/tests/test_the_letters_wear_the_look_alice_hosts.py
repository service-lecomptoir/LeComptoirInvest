"""The letters wear a look from Alice's catalogue: the company's choice, else the default.

🔴 WHAT IS GUARDED HERE (the manager, 29 Sept 2026: the e-mail looks are hosted by Alice).

  * the catalogue is ASKED with the outbound key, KEPT, and REVALIDATED with its tag;
  * a console out of reach costs nothing: the last copy stays, and with no copy at all the
    letter wears the built-in look. Never an exception, never a naked mail;
  * the envelope lays a letter out in each of the five layouts, readable on a phone;
  * the management company's choice is stored on its own row, checked against the
    catalogue, and the letters sent on its behalf carry its colours;
  * with no choice, the product's default applies.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.core import email_envelope
from app.core.security import create_access_token
from app.database import get_db
from app.main import app
from app.models.user import INVESTOR, MANAGER, User
from app.services import alice_client, email_themes, mailer, notice_service
from tests.conftest import TEST_FIRM
from tests.test_the_letter_speaks_the_investors_language import CALLED_ON, _setup

OUTBOUND = "cle-sortante-de-test"
INBOUND = "cle-entrante-de-test"
TAG = '"catalogue-v1"'

CATALOGUE = {
    "families": [
        {"key": "institutionnel", "name": "Institutionnel", "hint": "Marine et or."},
        {"key": "patrimoine", "name": "Patrimoine", "hint": "Bordeaux et or."},
    ],
    "themes": [
        {
            "key": "marine_center",
            "name": "Marine centré",
            "description": "En-tête marine, filet doré.",
            "family": "institutionnel",
            "layout": "center",
            "ink": "#0D2F5C",
            "accent": "#C9A227",
            "soft": "#a9c2e8",
        },
        {
            "key": "etude_band",
            "name": "Bandeau étude",
            "description": "En-tête bordeaux.",
            "family": "patrimoine",
            "layout": "band",
            "ink": "#6B2233",
            "accent": "#C9A227",
            "soft": "#e8cdd3",
        },
        # Unusable: a colour that is not #rrggbb. Dropped, never rendered.
        {
            "key": "broken",
            "name": "Cassé",
            "description": "",
            "family": "patrimoine",
            "layout": "band",
            "ink": "red;background:url(x)",
            "accent": "#C9A227",
            "soft": "#e8cdd3",
        },
    ],
    "default": "marine_center",
}


@pytest.fixture
def console(monkeypatch):
    """Configure a console and answer in its place; `state` says what it saw and does."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ALICE_URL", "http://alice.test/")
    monkeypatch.setattr(settings, "ALICE_API_KEY", OUTBOUND)
    monkeypatch.setattr(settings, "ALICE_INTERNAL_KEY", INBOUND)
    state: dict = {"seen": [], "down": False, "body": CATALOGUE}

    def handler(request: httpx.Request) -> httpx.Response:
        state["seen"].append(request)
        if state["down"]:
            raise httpx.ConnectError("console down", request=request)
        if request.url.path != "/api/v1/internal/email-themes":
            return httpx.Response(404)
        if request.headers.get("if-none-match") == TAG:
            return httpx.Response(304, headers={"ETag": TAG})
        return httpx.Response(200, json=state["body"], headers={"ETag": TAG})

    real = httpx.AsyncClient

    def _client(*args, **kwargs):
        return real(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(alice_client.httpx, "AsyncClient", _client)
    return state


@pytest.fixture
def no_console(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ALICE_URL", "")
    monkeypatch.setattr(settings, "ALICE_API_KEY", "")


def _age_the_copy() -> None:
    """Make the kept copy older than the console's max-age, without touching the clock."""
    email_themes._cache["checked"] -= 3600


# ── The client: asked, kept, revalidated, and never an exception ─────────────────────


async def test_the_catalogue_is_asked_with_the_outbound_key_for_this_product(console):
    kept = await email_themes.catalogue()

    assert kept is not None and kept.default == "marine_center"
    request = console["seen"][0]
    assert request.headers["X-Internal-Key"] == OUTBOUND
    assert request.url.params["app"] == "invest"
    assert "if-none-match" not in request.headers


async def test_a_fresh_copy_is_used_without_asking_again(console):
    await email_themes.catalogue()
    await email_themes.look_for("etude_band")
    await email_themes.look_for(None)

    assert len(console["seen"]) == 1


async def test_an_old_copy_is_revalidated_and_a_304_keeps_it(console):
    first = await email_themes.catalogue()
    _age_the_copy()

    again = await email_themes.catalogue()

    assert console["seen"][-1].headers["If-None-Match"] == TAG
    assert again is first


async def test_a_console_that_goes_down_leaves_the_last_copy_in_force(console):
    await email_themes.catalogue()
    console["down"] = True
    _age_the_copy()

    look = await email_themes.look_for("etude_band")

    assert look.ink == "#6B2233"


async def test_no_console_and_no_copy_gives_the_built_in_look_never_an_error(
    console,
):
    console["down"] = True

    assert await email_themes.look_for("etude_band") == email_envelope.BUILT_IN


async def test_an_installation_with_no_console_wears_the_built_in_look(no_console):
    assert await email_themes.look_for(None) == email_envelope.BUILT_IN


async def test_an_unknown_key_renders_with_the_default(console):
    look = await email_themes.look_for("nobody_has_this")

    assert look.key == "marine_center"


async def test_an_entry_that_cannot_be_rendered_is_dropped_not_the_catalogue(console):
    kept = await email_themes.catalogue()

    assert [t["key"] for t in kept.themes] == ["marine_center", "etude_band"]
    assert (await email_themes.look_for("broken")).key == "marine_center"


# ── The envelope: five layouts, a phone's width ──────────────────────────────────────


def _letter(**over) -> email_envelope.Letter:
    base = dict(
        title="Appel de fonds LCI-2026-0001",
        brand="Le Comptoir Un",
        body="Bernard,\n\nRéférence : LCI-2026-0001\nCompte : FR76300060000111111",
        signature=("Cordialement,", "Le Comptoir Un"),
        footer="Envoyé par Le Comptoir Invest.",
        lang="fr",
    )
    base.update(over)
    return email_envelope.Letter(**base)


def _look(layout: str) -> email_envelope.Look:
    return email_envelope.Look(
        key=layout, layout=layout, ink="#123456", accent="#abcdef", soft="#fedcba"
    )


@pytest.mark.parametrize("layout", email_envelope.LAYOUTS)
def test_every_layout_is_readable_on_a_phone_and_signed(layout):
    page = email_envelope.render(_look(layout), _letter())

    assert (
        '<meta name="viewport" content="width=device-width, initial-scale=1">' in page
    )
    assert "max-width:600px" in page
    assert "overflow-wrap:anywhere" in page
    assert "Cordialement," in page and "LCI-2026-0001" in page
    assert '<html lang="fr">' in page


def test_each_layout_places_its_colours_where_it_says():
    band = email_envelope.render(_look("band"), _letter())
    center = email_envelope.render(_look("center"), _letter())
    rule = email_envelope.render(_look("rule"), _letter())
    crest = email_envelope.render(_look("crest"), _letter())
    bare = email_envelope.render(_look("none"), _letter())

    # Coloured banners carry the ink as a background, and so does their footer.
    assert "background:#123456;padding:18px" in band
    assert "background:#123456;border-bottom:3px solid #abcdef" in center
    # Light headers: white, the accent as a rule, the ink on the name, a light footer.
    assert "background:#ffffff;border-bottom:3px solid #abcdef" in rule
    assert "text-align:center" in crest and "border-bottom:3px solid #abcdef" in crest
    assert "background:#f4f6fb" in rule and "background:#f4f6fb" in crest
    # Bare: neither header nor footer, the signature only.
    assert "#123456" not in bare and "Envoyé par" not in bare
    assert "Cordialement," in bare


def test_a_name_typed_by_a_person_cannot_inject_markup():
    page = email_envelope.render(
        _look("band"), _letter(brand="<script>alert(1)</script>")
    )

    assert "<script>" not in page
    assert "&lt;script&gt;" in page


def test_the_plain_text_part_carries_the_whole_letter_and_the_signature():
    text = _letter().text()

    assert text.startswith("Bernard,")
    assert "LCI-2026-0001" in text
    assert text.endswith("Cordialement,\nLe Comptoir Un")


# ── The company's choice: stored on its row, checked against the catalogue ──────────


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


async def _account(db, *, role: str = MANAGER, firm_id=None) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"{uuid.uuid4().hex[:8]}@fonds.test",
        hashed_password="h",
        role=role,
        firm_id=firm_id,
    )
    db.add(user)
    await db.flush()
    return user


def _bearer(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}


async def test_the_screen_reads_the_catalogue_and_no_choice_yet(client, db, console):
    manager = await _account(db)

    body = (
        await client.get("/api/v1/account/email-theme", headers=_bearer(manager))
    ).json()

    assert body["email_theme"] is None
    assert body["default"] == "marine_center"
    assert body["catalogue_available"] is True
    assert [f["key"] for f in body["families"]] == ["institutionnel", "patrimoine"]
    assert [t["key"] for t in body["themes"]] == ["marine_center", "etude_band"]


async def test_a_listed_look_is_stored_and_null_goes_back_to_the_default(
    client, db, console
):
    manager = await _account(db)

    chosen = await client.put(
        "/api/v1/account/email-theme",
        headers=_bearer(manager),
        json={"email_theme": "etude_band"},
    )
    assert chosen.status_code == 200 and chosen.json()["email_theme"] == "etude_band"
    assert manager.email_theme == "etude_band"

    back = await client.put(
        "/api/v1/account/email-theme",
        headers=_bearer(manager),
        json={"email_theme": None},
    )
    assert back.status_code == 200 and back.json()["email_theme"] is None
    assert manager.email_theme is None


async def test_a_look_the_catalogue_does_not_list_is_refused_in_a_sentence(
    client, db, console
):
    manager = await _account(db)

    refused = await client.put(
        "/api/v1/account/email-theme",
        headers=_bearer(manager),
        json={"email_theme": "broken"},
    )

    assert refused.status_code == 422
    assert refused.json()["detail"] == (
        "L'apparence « broken » n'existe pas dans le catalogue de la console : "
        "choisissez-en une dans la liste."
    )
    assert manager.email_theme is None


async def test_a_console_down_accepts_a_look_of_the_kept_copy(client, db, console):
    manager = await _account(db)
    await email_themes.catalogue()
    console["down"] = True
    _age_the_copy()

    chosen = await client.put(
        "/api/v1/account/email-theme",
        headers=_bearer(manager),
        json={"email_theme": "etude_band"},
    )

    assert chosen.status_code == 200
    assert manager.email_theme == "etude_band"


async def test_with_no_copy_to_check_against_the_choice_waits(client, db, console):
    manager = await _account(db)
    console["down"] = True

    refused = await client.put(
        "/api/v1/account/email-theme",
        headers=_bearer(manager),
        json={"email_theme": "etude_band"},
    )

    assert refused.status_code == 503
    assert "réessayez dans un instant" in refused.json()["detail"]
    assert manager.email_theme is None


async def test_a_member_of_a_company_sets_the_company_s_look(client, db, console):
    """The letters go out on the company's behalf: the choice lands on ITS row."""
    firm = await _account(db)
    member = await _account(db, firm_id=firm.id)

    await client.put(
        "/api/v1/account/email-theme",
        headers=_bearer(member),
        json={"email_theme": "etude_band"},
    )

    assert firm.email_theme == "etude_band"
    assert member.email_theme is None


async def test_an_investor_s_login_has_no_look_to_choose(client, db, console):
    investor = await _account(db, role=INVESTOR)

    response = await client.get(
        "/api/v1/account/email-theme", headers=_bearer(investor)
    )

    assert response.status_code == 403


# ── What actually goes out ───────────────────────────────────────────────────────────


@pytest.fixture
def relay(monkeypatch) -> list[dict]:
    sent: list[dict] = []

    async def _accept(*, to, subject, body, html):
        sent.append({"to": to, "subject": subject, "body": body, "html": html})

    async def _configured() -> bool:
        return True

    monkeypatch.setattr(mailer, "is_configured", _configured)
    monkeypatch.setattr(mailer, "send", _accept)
    return sent


async def test_a_letter_sent_for_a_company_that_chose_wears_its_colours(
    db, console, relay
):
    db.add(
        User(
            id=TEST_FIRM,
            email="societe@fonds.test",
            hashed_password="h",
            role=MANAGER,
            email_theme="etude_band",
        )
    )
    await db.flush()
    call = await _setup(db)

    await notice_service.send(db, call=call, as_of=CALLED_ON)

    html = relay[0]["html"]
    assert "background:#6B2233" in html
    assert "LCI-2026-0001" in html and "Le Comptoir Un" in html
    assert relay[0]["body"].endswith("Cordialement,\nLe Comptoir Un")


async def test_a_letter_with_no_choice_behind_it_wears_the_default(db, console, relay):
    call = await _setup(db)

    await notice_service.send(db, call=call, as_of=CALLED_ON)

    html = relay[0]["html"]
    assert "background:#0D2F5C;border-bottom:3px solid #C9A227" in html
    assert "#6B2233" not in html


async def test_the_envelope_speaks_the_investor_s_language(db, no_console, relay):
    call = await _setup(db, investor_locale="en")

    await notice_service.send(db, call=call, as_of=CALLED_ON)

    html = relay[0]["html"]
    assert '<html lang="en">' in html
    assert "Kind regards," in html and "Cordialement" not in html
    assert "Sent by Le Comptoir Invest on behalf of Le Comptoir Un." in html
