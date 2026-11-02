"""The contact address is the one Alice holds, never one written here (3 Oct 2026).

The manager asked, on 3 Oct 2026, for one place to change it, with a view of it. The
address lives on Alice's Communication screen (tab Alice); this product reads it on the door
it already calls (`/internal/comm-config`) and relays it to its pages (`/public/contact`).

* a sentence names the address Alice gave, in the reader's language, the last one known
  when Alice does not answer, and none when none is known -- never an invented one;
* no contact mailbox of the platform is written in this product's code any more.
"""

from __future__ import annotations

import pathlib

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.i18n import use_lang
from app.main import app
from app.services import platform_contact
from app.services.platform_contact import OR_WRITE, WRITE

ROOT = pathlib.Path(__file__).resolve().parents[2]
#: Both names of the platform: the old one and the new one. Literal, not a pattern.
MAILBOXES = ("contact@lecomptoir" + ".services", "contact@lecomptoir-services" + ".com")


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(platform_contact, "_known", {"value": "", "next": 0.0})


def _alice_answers(monkeypatch, *answers):
    queue = list(answers)

    async def _fetch():
        return queue.pop(0) if queue else None

    monkeypatch.setattr(platform_contact, "_fetch", _fetch)


async def test_a_sentence_names_the_address_in_the_readers_language(monkeypatch):
    _alice_answers(monkeypatch, "contact@example.org")
    assert await platform_contact.said("Réessayez dans un instant" + OR_WRITE) == (
        "Réessayez dans un instant, ou écrivez-nous à contact@example.org."
    )
    with use_lang("en"):
        assert await platform_contact.said("Not configured. " + WRITE) == (
            "Not configured. Write to us at contact@example.org."
        )


async def test_alice_silent_keeps_the_last_address_known(monkeypatch):
    _alice_answers(monkeypatch, "contact@example.org", None)
    assert await platform_contact.contact_email() == "contact@example.org"
    platform_contact._known["next"] = 0.0  # the cache expired, and Alice is silent
    assert await platform_contact.contact_email() == "contact@example.org"


async def test_none_known_says_none(monkeypatch):
    _alice_answers(monkeypatch)
    assert await platform_contact.said("Réessayez dans un instant" + OR_WRITE) == (
        "Réessayez dans un instant."
    )
    assert await platform_contact.said("Pas configuré. " + WRITE) == "Pas configuré."


async def test_the_pages_ask_the_server():
    platform_contact._known.update(value="contact@example.org", next=float("inf"))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://invest.test"
    ) as c:
        r = await c.get("/api/v1/public/contact")
    assert r.status_code == 200, r.text
    assert r.json() == {"contact_email": "contact@example.org"}


def test_no_contact_mailbox_is_written_in_the_code():
    found = []
    for base, suffixes in (
        (ROOT / "backend" / "app", {".py"}),
        (ROOT / "frontend" / "src", {".ts", ".tsx", ".json"}),
    ):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in suffixes or "node_modules" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            found += [f"{path.relative_to(ROOT)}: {m}" for m in MAILBOXES if m in text]
    assert not found, (
        "the contact address is Alice's (platform_contact):\n" + "\n".join(found)
    )


#: What `/internal/comm-config` may carry beside the contact address: none of it is public.
FULL_COMM_CONFIG = {
    "contact_email": "contact@lecomptoir-services.test",
    "leads_notify_email": "equipe@lecomptoir-services.test",
    "smtp_from_email": "no-reply@lecomptoir-services.test",
    "smtp_password": "secret",
}


async def test_the_public_route_gives_the_contact_address_and_nothing_else(monkeypatch):
    """The owner, 2 Nov 2026: Immo printed the TEAM's inbox (`leads_notify_email`, the
    internal alerts) on its public pages. The public reads `contact_email` only; the
    team's inbox and every other value of the e-mail settings never leave, and an empty
    contact never falls back on another address."""
    from app.services import alice_client

    for answer, expected in (
        (FULL_COMM_CONFIG, "contact@lecomptoir-services.test"),
        ({**FULL_COMM_CONFIG, "contact_email": ""}, ""),
    ):

        async def _call(method, path, *args, a=answer, **kwargs):
            return a

        monkeypatch.setattr(alice_client, "_call", _call)
        monkeypatch.setattr(platform_contact, "_known", {"value": "", "next": 0.0})
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://invest.test"
        ) as c:
            r = await c.get("/api/v1/public/contact")
        assert r.status_code == 200, r.text
        assert r.json() == {"contact_email": expected}
        assert "equipe@" not in r.text and "secret" not in r.text
