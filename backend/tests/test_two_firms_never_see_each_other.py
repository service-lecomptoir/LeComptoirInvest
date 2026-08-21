"""Two management companies on one installation, and nothing crosses between them.

🔴 WHAT THIS FILE ANSWERS FOR. Until 21 August 2026 this product had NO owner column
anywhere: every manager account of an installation read the whole register — every
investor's KYC file, IBAN and subscriptions. It was not a defect of the code, it WAS the
model, and it surfaced only when a second manager account recognised somebody else's
projects on their screen.

🔴 AND THE FIX IS STRUCTURAL, WHICH IS EXACTLY WHY IT NEEDS A GUARD LIKE THIS ONE. The
filter is injected by SQLAlchemy on every query touching a scoped table, so no endpoint
has to remember it. That is what makes it safe — and also what makes it invisible: nothing
in the routes shows the isolation, so nothing in the routes will show it disappearing. A
single wrong line in `core.firm_scope` would silently reopen the whole register.

⚠️ SO THE GUARD BUYS FROM THE OUTSIDE, THROUGH THE ROUTES. Asserting that
`with_loader_criteria` was added would test the implementation; asking one firm's manager
for the other's data tests what the customer would experience.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import instruments, kyc
from app.core.landlord_kind_values import PERSON
from app.core.security import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.models.fund import Fund
from app.models.investor import Investor
from app.models.project import Project
from app.models.subscription import Subscription
from app.models.treasury import BankMovement, IN
from app.models.user import MANAGER, User

CURRENCY = "EUR"


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


class Firm:
    """One management company: its manager account, and the rows it owns."""

    def __init__(self, manager, fund, project, investor, movement):
        self.manager = manager
        self.fund = fund
        self.project = project
        self.investor = investor
        self.movement = movement

    @property
    def auth(self) -> dict[str, str]:
        return {
            "Authorization": (
                f"Bearer {create_access_token(str(self.manager.id), self.manager.role)}"
            )
        }


async def _firm(db, label: str) -> Firm:
    """A firm with one of everything, stamped by hand.

    ⚠️ STAMPED BY HAND HERE, ON PURPOSE. In the product the stamp is automatic; a fixture
    that relied on the automatic stamp would be testing the guard with the guard.
    """
    manager = User(
        id=uuid.uuid4(),
        email=f"gerant-{label}@fonds.fr",
        hashed_password=hash_password("Motdepasse-1234"),
        account_name=f"Societe {label}",
        role=MANAGER,
    )
    db.add(manager)
    await db.flush()
    firm_id = manager.id  # firm_id is NULL: this account IS the firm.

    fund = Fund(
        id=uuid.uuid4(),
        name=f"Fonds {label}",
        currency=CURRENCY,
        firm_id=firm_id,
    )
    db.add(fund)
    project = Project(
        id=uuid.uuid4(),
        fund_id=fund.id,
        name=f"Projet {label}",
        currency=CURRENCY,
        firm_id=firm_id,
    )
    investor = Investor(
        id=uuid.uuid4(),
        kind=PERSON,
        last_name=f"Investisseur-{label}",
        email=f"investisseur-{label}@exemple.fr",
        kyc_status=kyc.ACCEPTED,
        firm_id=firm_id,
    )
    db.add_all([project, investor])
    await db.flush()

    db.add(
        Subscription(
            id=uuid.uuid4(),
            fund_id=fund.id,
            investor_id=investor.id,
            instrument=instruments.EQUITY,
            amount=Decimal("50000"),
            currency=CURRENCY,
            signed_on=date(2026, 1, 5),
        )
    )
    movement = BankMovement(
        id=uuid.uuid4(),
        account_iban=f"FR76300060000{label}1111111111",
        direction=IN,
        amount=Decimal("10000"),
        currency=CURRENCY,
        value_date=date(2026, 1, 10),
        firm_id=firm_id,
    )
    db.add(movement)
    await db.flush()
    return Firm(manager, fund, project, investor, movement)


@pytest.fixture
async def two_firms(db):
    return await _firm(db, "a"), await _firm(db, "b")


def _names(payload) -> set[str]:
    """Every name-ish string in a response, whatever shape it has."""
    found: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in {
                "name",
                "display_name",
                "investor_name",
                "boutique_name",
            } and isinstance(value, str):
                found.add(value)
            found |= _names(value)
    elif isinstance(payload, list):
        for item in payload:
            found |= _names(item)
    return found


# ── What one firm sees, and what it does not ────────────────────────────


async def test_a_manager_sees_only_their_own_funds(client, two_firms):
    a, b = two_firms
    body = (await client.get("/api/v1/funds", headers=a.auth)).json()
    seen = _names(body)
    assert "Fonds a" in seen
    assert "Fonds b" not in seen, "another firm's fund is visible"


async def test_a_manager_sees_only_their_own_projects(client, two_firms):
    a, b = two_firms
    body = (await client.get("/api/v1/projects", headers=a.auth)).json()
    seen = _names(body)
    assert "Projet a" in seen
    assert "Projet b" not in seen, "another firm's project is visible"


async def test_a_manager_sees_only_their_own_register(client, two_firms):
    """🔴 THE ONE THAT MATTERS MOST: the register carries KYC files and IBANs."""
    a, b = two_firms
    body = (await client.get("/api/v1/investors", headers=a.auth)).json()
    seen = _names(body)
    assert any("Investisseur-a" in name for name in seen)
    assert not any("Investisseur-b" in name for name in seen), (
        "another management company's register is visible"
    )


async def test_naming_another_firms_investor_finds_nothing(client, two_firms):
    """⚠️ AND NOT ONLY IN THE LISTINGS. An identifier guessed, or read somewhere else,
    must open nothing: that is the door an isolation applied only to listings leaves."""
    a, b = two_firms
    response = await client.get(
        f"/api/v1/statements/2026?investor_id={b.investor.id}", headers=a.auth
    )
    assert response.status_code == 404, response.text


async def test_the_treasury_of_another_firm_is_invisible(client, two_firms):
    """Bank movements have no parent at all: without a column of their own they would have
    stayed common to everybody. This one is the money."""
    a, b = two_firms
    body = (await client.get("/api/v1/treasury/movements", headers=a.auth)).json()
    ibans = {
        item.get("account_iban")
        for item in (body if isinstance(body, list) else body.get("items", []))
        if isinstance(item, dict)
    }
    assert b.movement.account_iban not in ibans


# ── What the console keeps the right to see ─────────────────────────────────────


async def test_the_console_still_counts_every_firm(client, db, two_firms):
    """🔴 THE NAMED EXCEPTION. Alice bills what the installation manages, so it must see
    both registers. If the isolation cut the console off too, the managers' accounts and
    allowances would vanish from its screen, and the breakage would look like the
    neighbour's."""
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    previous = settings.ALICE_INTERNAL_KEY
    settings.ALICE_INTERNAL_KEY = "cle-interne-de-test"
    try:
        response = await client.get(
            "/internal/managers", headers={"X-Internal-Key": "cle-interne-de-test"}
        )
        assert response.status_code == 200, response.text
        counted = {row["managed_count"] for row in response.json()}
        # Both investors, seen by the console despite the isolation.
        assert counted == {2}, counted
    finally:
        settings.ALICE_INTERNAL_KEY = previous


# ── What the scope does when nobody established one ────────────────────────────


async def test_with_no_firm_established_nothing_is_visible(db, two_firms):
    """🔴 THE DEFAULT LEANS TOWARDS « NOTHING », NEVER TOWARDS « EVERYTHING ».

    A background job, a code path nobody thought about: with no firm established, the
    scope matches no row at all. A protection whose failure mode leans towards « none » is
    the only kind worth having; the opposite is a leak that looks like a working screen.
    """
    from sqlalchemy import select

    from app.core import firm_scope

    with firm_scope.use_firm(None):
        found = (await db.execute(select(Fund))).scalars().all()
    assert found == [], "with no firm established, funds are still visible"


async def test_a_new_row_is_stamped_without_being_asked(db, two_firms):
    """⚠️ WRITING WITHOUT THE STAMP WOULD LEAVE A ROW BELONGING TO NOBODY, invisible to
    everyone and found again only by reading the table by hand. The screen that created it
    would watch it disappear."""
    from sqlalchemy import select

    from app.core import firm_scope

    a, _ = two_firms
    with firm_scope.use_firm(a.manager.id):
        db.add(Fund(id=uuid.uuid4(), name="Fonds neuf", currency=CURRENCY))
        await db.flush()
        found = (
            (await db.execute(select(Fund).where(Fund.name == "Fonds neuf")))
            .scalars()
            .one()
        )
    assert found.firm_id == a.manager.id
