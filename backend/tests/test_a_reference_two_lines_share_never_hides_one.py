"""A statement reference two movements share never hides the second one.

🔴 A LINE WAS RECOGNISED BY ITS REFERENCE ALONE. A bank with no reference to give writes
`NOTPROVIDED` (ISO 20022), and a payer's `EndToEndId` is whatever the payer typed, often the
same every month. The second transfer carrying it was counted « already imported » and
never reached the treasury: money received, attributed to nobody, and missing from every
balance without a word.

⚠️ AND RE-IMPORTING THE SAME FILE STILL CHANGES NOTHING, which is the reason the reference
is read at all.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.models.user import MANAGER, User
from tests.conftest import TEST_FIRM

IBAN = "FR7630006000011234567890189"


@pytest.fixture
async def client(db):
    manager = User(
        id=TEST_FIRM,
        email="gerant@fonds-reference.fr",
        hashed_password=hash_password("Motdepasse-1234"),
        account_name="Fonds Reference",
        role=MANAGER,
    )
    db.add(manager)
    await db.flush()

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://invest.test"
    ) as c:
        c.headers["Authorization"] = (
            f"Bearer {create_access_token(str(manager.id), manager.role)}"
        )
        yield c
    app.dependency_overrides.pop(get_db, None)


def _line(amount: str, day: str, reference: str = "NOTPROVIDED") -> dict:
    return {
        "account_iban": IBAN,
        "external_id": reference,
        "direction": "in",
        "amount": amount,
        "currency": "EUR",
        "value_date": day,
        "counterparty_name": "Raymonde Alphanor",
    }


async def test_two_lines_of_one_file_sharing_a_reference_are_both_recorded(client):
    response = await client.post(
        "/api/v1/treasury/movements",
        json=[_line("1000.00", "2026-03-03"), _line("400.00", "2026-03-03")],
    )
    assert response.status_code == 201, response.text
    assert sorted(m["amount"] for m in response.json()) == ["1000.00", "400.00"]


async def test_a_later_transfer_with_a_reference_already_seen_is_recorded(client):
    first = await client.post(
        "/api/v1/treasury/movements", json=[_line("1000.00", "2026-03-03", "LOYER")]
    )
    assert len(first.json()) == 1
    later = await client.post(
        "/api/v1/treasury/movements", json=[_line("1000.00", "2026-04-03", "LOYER")]
    )
    assert later.status_code == 201, later.text
    assert len(later.json()) == 1, "the April transfer was taken for the March one"


async def test_reimporting_the_same_lines_still_creates_nothing(client):
    lines = [_line("1000.00", "2026-03-03"), _line("400.00", "2026-03-03")]
    assert (
        len((await client.post("/api/v1/treasury/movements", json=lines)).json()) == 2
    )
    again = await client.post("/api/v1/treasury/movements", json=lines)
    assert again.status_code == 201, again.text
    assert again.json() == []


def _camt(entries: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08">'
        f"<BkToCstmrStmt><Stmt><Acct><Id><IBAN>{IBAN}</IBAN></Id></Acct>{entries}"
        "</Stmt></BkToCstmrStmt></Document>"
    ).encode()


def _entry(amount: str) -> str:
    return (
        f"<Ntry><Amt Ccy='EUR'>{amount}</Amt><CdtDbtInd>CRDT</CdtDbtInd>"
        "<ValDt><Dt>2026-03-03</Dt></ValDt><NtryDtls><TxDtls>"
        "<Refs><EndToEndId>NOTPROVIDED</EndToEndId></Refs>"
        "</TxDtls></NtryDtls></Ntry>"
    )


async def test_the_banks_file_keeps_both_transfers_and_knows_them_again(client):
    """The same rule on the bank's own file: one code for both ways in."""
    file = _camt(_entry("1000.00") + _entry("400.00"))
    first = await client.post(
        "/api/v1/treasury/movements/camt",
        files={"file": ("releve.xml", file, "application/xml")},
    )
    assert first.status_code == 201, first.text
    assert len(first.json()["imported"]) == 2
    again = await client.post(
        "/api/v1/treasury/movements/camt",
        files={"file": ("releve.xml", file, "application/xml")},
    )
    assert again.json()["imported"] == []
    assert again.json()["already_known"] == 2


async def test_a_statement_beyond_the_ceiling_is_refused_before_being_read_whole(
    client, monkeypatch
):
    from app.api.v1 import treasury

    monkeypatch.setattr(treasury, "MAX_STATEMENT_BYTES", 1000)
    response = await client.post(
        "/api/v1/treasury/movements/camt",
        files={"file": ("releve.xml", _camt(_entry("1.00") * 20), "application/xml")},
    )
    assert response.status_code == 413, response.text
