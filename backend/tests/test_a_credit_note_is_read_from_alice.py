"""The credit notes of the subscription invoices, read in « Mon abonnement ».

The owner, 6 Nov 2026: the credit notes shown in « Mon abonnement » of every product.
Alice lists them under each invoice and serves their PDF; this product relays, as for an
invoice.

🔴 WHAT IS GUARDED HERE:
  * the PDF is asked of Alice under the SESSION's manager, never an id from the request,
    on her credit-note path, and comes back with her filename;
  * an Alice that answers 404 or keeps silent gives the very answer of a missing invoice;
  * an investor is refused the credit note as they are refused the invoice;
  * the invoice list is relayed with the credit notes Alice puts on it.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.core.security import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.models.user import INVESTOR, MANAGER, User
from app.services import alice_client

PDF = b"%PDF-1.7 avoir"
DISPOSITION = 'attachment; filename="avoir-AV-2026-00001.pdf"'


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


@pytest.fixture
def alice(monkeypatch):
    """Answer in Alice's place: `answers[path]` is a response, or an exception to raise."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ALICE_URL", "http://alice.test/")
    monkeypatch.setattr(settings, "ALICE_API_KEY", "cle-sortante-de-test")
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


def _note_path(user_id: uuid.UUID, note_id: uuid.UUID) -> str:
    return f"/api/v1/internal/invoices/{user_id}/credit-notes/{note_id}/pdf"


async def test_the_pdf_is_asked_under_the_session_s_manager(client, db, alice):
    seen, answers = alice
    manager = await _user(db, MANAGER)
    note = uuid.uuid4()
    answers[_note_path(manager.id, note)] = httpx.Response(
        200,
        content=PDF,
        headers={"content-type": "application/pdf", "content-disposition": DISPOSITION},
    )
    resp = await client.get(
        f"/api/v1/billing/invoices/credit-notes/{note}/pdf?user_id={uuid.uuid4()}",
        headers=_auth(manager),
    )
    assert resp.status_code == 200
    assert resp.content == PDF
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["content-disposition"] == DISPOSITION
    assert [r.url.path for r in seen] == [_note_path(manager.id, note)]
    assert seen[0].headers["X-Internal-Key"] == "cle-sortante-de-test"


async def test_a_pdf_without_a_filename_is_still_named(client, db, alice):
    _, answers = alice
    manager = await _user(db, MANAGER)
    note = uuid.uuid4()
    answers[_note_path(manager.id, note)] = httpx.Response(200, content=PDF)
    resp = await client.get(
        f"/api/v1/billing/invoices/credit-notes/{note}/pdf", headers=_auth(manager)
    )
    assert resp.headers["content-disposition"] == 'attachment; filename="AVOIR.pdf"'


async def test_a_refusal_or_a_silence_reads_as_a_missing_invoice(client, db, alice):
    _, answers = alice
    manager = await _user(db, MANAGER)
    note = uuid.uuid4()
    missing_invoice = await client.get(
        "/api/v1/billing/invoices/inconnue/pdf", headers=_auth(manager)
    )
    assert missing_invoice.status_code == 404

    refused = await client.get(
        f"/api/v1/billing/invoices/credit-notes/{note}/pdf", headers=_auth(manager)
    )
    answers[_note_path(manager.id, note)] = httpx.ConnectError("console down")
    silent = await client.get(
        f"/api/v1/billing/invoices/credit-notes/{note}/pdf", headers=_auth(manager)
    )
    for resp in (refused, silent):
        assert resp.status_code == 404
        assert resp.json() == missing_invoice.json()


async def test_an_investor_is_refused_as_for_an_invoice(client, db, alice):
    seen, _ = alice
    investor = await _user(db, INVESTOR)
    invoice = await client.get(
        "/api/v1/billing/invoices/ABO-2026-00001/pdf", headers=_auth(investor)
    )
    note = await client.get(
        f"/api/v1/billing/invoices/credit-notes/{uuid.uuid4()}/pdf",
        headers=_auth(investor),
    )
    assert invoice.status_code == note.status_code == 403
    assert seen == []


async def test_the_invoice_list_carries_alice_s_credit_notes(client, db, alice):
    _, answers = alice
    manager = await _user(db, MANAGER)
    listed = [
        {
            "id": str(uuid.uuid4()),
            "number": "ABO-2026-00001",
            "period_year": 2026,
            "period_month": 10,
            "amount": 25.0,
            "amount_ttc": 30.0,
            "status": "paid",
            "credited_ttc": "6.00",
            "credit_state": "partial",
            "credit_notes": [
                {
                    "id": str(uuid.uuid4()),
                    "number": "AV-2026-00001",
                    "issued_on": "2026-11-06",
                    "amount_ttc": "6.00",
                    "reason": "Geste commercial.",
                    "currency": "EUR",
                }
            ],
        }
    ]
    answers[f"/api/v1/internal/invoices/{manager.id}"] = httpx.Response(
        200, json=listed
    )
    resp = await client.get("/api/v1/billing/invoices", headers=_auth(manager))
    assert resp.status_code == 200
    assert resp.json() == listed
