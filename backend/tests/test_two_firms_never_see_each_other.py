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


async def test_the_console_sees_both_firms_and_bills_each_for_its_own(
    client, db, two_firms
):
    """🔴 THE NAMED EXCEPTION, AND THE LIMIT OF IT.

    Alice bills what the installation manages, so the console must SEE both registers: if
    the isolation cut it off too, the managers' accounts and allowances would vanish from
    its screen and the breakage would look like the neighbour's.

    🔴 BUT IT MUST COUNT THEM APART, AND THIS ONE IS MONEY. Before the isolation this
    product had a single register, so the console reported the SAME quantity to every
    manager account -- correct then, and silently wrong the day two firms shared an
    installation: each would have been invoiced for the other's investors, with nothing
    anywhere looking broken.
    """
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
        billed = {row["email"]: row["managed_count"] for row in response.json()}
    finally:
        settings.ALICE_INTERNAL_KEY = previous

    a, b = two_firms
    # Both accounts are listed: the console is not cut off by the isolation.
    assert set(billed) == {a.manager.email, b.manager.email}, billed
    # And each is billed for ONE investor: its own.
    assert billed[a.manager.email] == 1, billed
    assert billed[b.manager.email] == 1, billed


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


# ── The rows that carry no firm of their own ───────────────────────────────────


class Children:
    """What hangs under one firm's investor: a subscription, a call, a distribution and a
    request, none of which carries a `firm_id` of its own."""

    def __init__(self, subscription, call, distribution, request):
        self.subscription = subscription
        self.call = call
        self.distribution = distribution
        self.request = request


async def _children(db, firm: Firm, label: str) -> Children:
    from app.models.subscription import SubscriptionRequest
    from app.models.treasury import CapitalCall, Distribution

    from sqlalchemy import select

    from app.core import firm_scope

    # Read across firms: the fixture stamped the roots by hand, under no firm in force.
    with firm_scope.all_firms():
        subscription = (
            (
                await db.execute(
                    select(Subscription).where(
                        Subscription.investor_id == firm.investor.id
                    )
                )
            )
            .scalars()
            .one()
        )
    call = CapitalCall(
        id=uuid.uuid4(),
        subscription_id=subscription.id,
        reference=f"APPEL-{label}",
        amount=Decimal("5000"),
        currency=CURRENCY,
        called_on=date(2026, 2, 1),
        due_on=date(2026, 3, 1),
    )
    distribution = Distribution(
        id=uuid.uuid4(),
        subscription_id=subscription.id,
        capital_amount=Decimal("0"),
        income_amount=Decimal("700"),
        currency=CURRENCY,
        decided_on=date(2026, 4, 1),
    )
    request = SubscriptionRequest(
        id=uuid.uuid4(),
        investor_id=firm.investor.id,
        instrument=instruments.EQUITY,
        amount=Decimal("20000"),
        currency=CURRENCY,
        requested_on=date(2026, 1, 2),
    )
    db.add_all([call, distribution, request])
    await db.flush()
    return Children(subscription, call, distribution, request)


@pytest.fixture
async def two_firms_and_their_children(db, two_firms):
    """⚠️ THE SESSION IS EMPTIED AFTERWARDS, because a real request opens its own. Rows
    left in the identity map are handed back by `Session.get()` without any query, so a
    test that kept them would be testing the fixture's memory, not the scope."""
    a, b = two_firms
    children = await _children(db, a, "a"), await _children(db, b, "b")
    db.expunge_all()
    return two_firms, children


def _ids(payload) -> set[str]:
    return {item["id"] for item in payload if isinstance(item, dict) and "id" in item}


async def test_another_firms_distributions_are_not_listed(
    client, two_firms_and_their_children
):
    """🔴 A DISTRIBUTION CARRIES NO FIRM, ONLY A SUBSCRIPTION. Scoping the four roots
    scoped nothing that is queried directly below them: the list of distributions was the
    whole installation's."""
    (a, _), (mine, theirs) = two_firms_and_their_children
    response = await client.get("/api/v1/distributions", headers=a.auth)
    assert response.status_code == 200, response.text
    seen = _ids(response.json())
    assert str(mine.distribution.id) in seen
    assert str(theirs.distribution.id) not in seen, (
        "another firm's distribution is listed"
    )


async def test_each_firm_reads_its_own_distributions_one_after_the_other(
    client, two_firms_and_their_children
):
    """⚠️ THE FIRM IS A VALUE OF THE FILTER, NOT PART OF ITS CACHED SHAPE: the second
    caller must not be served the first caller's scope."""
    (a, b), (of_a, of_b) = two_firms_and_their_children
    for firm, own, other in ((a, of_a, of_b), (b, of_b, of_a), (a, of_a, of_b)):
        seen = _ids(
            (await client.get("/api/v1/distributions", headers=firm.auth)).json()
        )
        assert str(own.distribution.id) in seen
        assert str(other.distribution.id) not in seen


async def test_another_firms_calls_are_not_listed(client, two_firms_and_their_children):
    (a, _), (mine, theirs) = two_firms_and_their_children
    response = await client.get("/api/v1/treasury/calls", headers=a.auth)
    assert response.status_code == 200, response.text
    seen = _ids(response.json())
    assert str(mine.call.id) in seen
    assert str(theirs.call.id) not in seen, "another firm's capital call is listed"


async def test_another_firms_requests_are_not_listed(
    client, two_firms_and_their_children
):
    (a, _), (mine, theirs) = two_firms_and_their_children
    response = await client.get("/api/v1/subscription-requests", headers=a.auth)
    assert response.status_code == 200, response.text
    seen = _ids(response.json())
    assert str(mine.request.id) in seen
    assert str(theirs.request.id) not in seen, (
        "another firm's subscription request is listed"
    )


async def test_another_firms_call_letter_cannot_be_read(
    client, two_firms_and_their_children
):
    """The letter names the investor, the amount and the account to pay into."""
    (a, _), (_, theirs) = two_firms_and_their_children
    response = await client.get(
        f"/api/v1/treasury/calls/{theirs.call.id}/notice?as_of=2026-03-10",
        headers=a.auth,
    )
    assert response.status_code == 404, response.text


async def test_another_firms_distribution_cannot_be_paid(
    client, two_firms_and_their_children
):
    (a, _), (_, theirs) = two_firms_and_their_children
    response = await client.post(
        f"/api/v1/distributions/{theirs.distribution.id}/pay",
        json={"bank_movement_id": str(a.movement.id)},
        headers=a.auth,
    )
    assert response.status_code == 404, response.text


async def test_another_firms_request_cannot_be_decided(
    client, two_firms_and_their_children
):
    (a, _), (_, theirs) = two_firms_and_their_children
    response = await client.post(
        f"/api/v1/subscription-requests/{theirs.request.id}/decide",
        json={"accept": False, "reason": "Dossier incomplet"},
        headers=a.auth,
    )
    assert response.status_code == 404, response.text


async def test_another_firms_subscription_cannot_be_converted(
    client, two_firms_and_their_children
):
    (a, _), (_, theirs) = two_firms_and_their_children
    response = await client.post(
        f"/api/v1/subscriptions/{theirs.subscription.id}/convert",
        json={"converted_on": "2026-05-01", "principal_converted": "1000"},
        headers=a.auth,
    )
    assert response.status_code == 404, response.text


async def test_no_call_is_opened_on_another_firms_subscription(
    client, two_firms_and_their_children
):
    (a, _), (_, theirs) = two_firms_and_their_children
    response = await client.post(
        "/api/v1/treasury/calls",
        json={
            "subscription_id": str(theirs.subscription.id),
            "amount": "1000",
            "called_on": "2026-05-01",
            "due_on": "2026-06-01",
        },
        headers=a.auth,
    )
    assert response.status_code == 404, response.text


async def test_ones_money_is_never_attributed_to_another_firms_subscription(
    client, two_firms_and_their_children
):
    (a, _), (_, theirs) = two_firms_and_their_children
    response = await client.post(
        f"/api/v1/treasury/movements/{a.movement.id}/attribute",
        json={"subscription_id": str(theirs.subscription.id), "amount": "1000"},
        headers=a.auth,
    )
    assert response.status_code == 404, response.text
