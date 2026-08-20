"""The annual statement as a PDF: the document an investor FILES, not the manager's screen.

🔴 WHY THIS FILE EXISTS. Everything else this product renders is read by somebody who is
signed in, on a page that can be reloaded. This one leaves: it is attached to a tax return,
forwarded to an accountant, kept for seven years. It is read by people who will never touch
the product, months after the year it describes, and it cannot be corrected in place.

🔴 HENCE THE GUARD A SINGLE-LANGUAGE TEST CANNOT SEE. The caller reads one language, the
investor chose another, and the document must follow the INVESTOR. Rendered from the
caller's `Accept-Language` it would carry French headings on a British investor's return,
and nothing would look wrong: the figures are identical either way.

🔴 AND THE SEPARATORS MATTER AS MUCH AS THE WORDS. A figure grouped one way is a
thousand and grouped the other way it is one. On a document somebody files with a tax
authority, that is not a cosmetic difference.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import i18n, instruments, kyc
from app.core.landlord_kind_values import PERSON
from app.core.security import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.models.fund import Fund
from app.models.investor import Investor
from app.models.subscription import Subscription
from app.models.treasury import Distribution
from app.models.user import MANAGER, User
from app.services import statement_pdf, statement_service

CURRENCY = "EUR"
YEAR = 2026


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


async def _manager(db) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"gerant-{uuid.uuid4().hex[:8]}@fonds.fr",
        hashed_password=hash_password("Motdepasse-1234"),
        account_name="Meridian Capital",
        role=MANAGER,
    )
    db.add(user)
    await db.flush()
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}


async def _investor_paid(db, *, locale: str | None, name: str = "Bernard") -> Investor:
    """One investor, one subscription, and one distribution PAID inside the year."""
    fund = Fund(id=uuid.uuid4(), name="Le Comptoir Un", currency=CURRENCY)
    db.add(fund)
    investor = Investor(
        id=uuid.uuid4(),
        kind=PERSON,
        last_name=name,
        email=f"{uuid.uuid4().hex[:6]}@investisseur.fr",
        kyc_status=kyc.ACCEPTED,
        locale=locale,
    )
    db.add(investor)
    await db.flush()

    subscription = Subscription(
        id=uuid.uuid4(),
        fund_id=fund.id,
        investor_id=investor.id,
        instrument=instruments.EQUITY,
        amount=Decimal("50000"),
        currency=CURRENCY,
        signed_on=date(YEAR, 1, 5),
    )
    db.add(subscription)
    await db.flush()

    db.add(
        Distribution(
            id=uuid.uuid4(),
            subscription_id=subscription.id,
            capital_amount=Decimal("1000.00"),
            income_amount=Decimal("1234.56"),
            withholding_amount=Decimal("234.56"),
            currency=CURRENCY,
            decided_on=date(YEAR, 6, 1),
            paid_on=date(YEAR, 6, 15),
        )
    )
    await db.flush()
    return investor


# ── The language ────────────────────────────────────────────────────────────────────


async def test_the_document_follows_the_investor_and_not_the_manager_who_clicked(db):
    """🔴 THE ONE A SINGLE-LANGUAGE TEST CANNOT SEE.

    The caller is reading French, which is what the middleware would have set from their
    browser. The investor chose English. The document is English.
    """
    investor = await _investor_paid(db, locale="en")
    built = await statement_service.statement_for(
        db, investor_id=investor.id, year=YEAR
    )

    with i18n.use_lang("fr"):  # the manager's own language, as the middleware sets it
        with i18n.use_lang("en"):  # the one the route opens for the reader
            html = statement_pdf.render_html(
                built, statement_service.labels(YEAR), issuer="Meridian Capital"
            )

    assert "Annual statement 2026" in html
    assert "Gross income" in html
    assert "Relevé annuel" not in html
    assert "Produit brut" not in html


async def test_the_separators_follow_the_reader_too(db):
    """🔴 THE SAME FIGURE IS A THOUSAND OR IT IS ONE, depending on the convention it is
    read under.

    Translated headings with French-formatted figures give a document that looks carefully
    made and reads wrong by a factor of a thousand. The amount is the same in both
    renderings: only the formatting changes, which is exactly what nobody notices.
    """
    investor = await _investor_paid(db, locale="en")
    built = await statement_service.statement_for(
        db, investor_id=investor.id, year=YEAR
    )

    with i18n.use_lang("en"):
        english = statement_pdf.render_html(built, statement_service.labels(YEAR))
    with i18n.use_lang("fr"):
        french = statement_pdf.render_html(built, statement_service.labels(YEAR))

    assert "1,234.56" in english
    assert "1,234.56" not in french
    assert "234,56" in french


async def test_the_caller_s_language_comes_back_afterwards(client, db):
    """⚠️ `use_lang` RESTORES. The document must not leave the caller in the investor's
    language: the very next refusal on the same request would come back in it."""
    investor = await _investor_paid(db, locale="en")
    manager = await _manager(db)

    with i18n.use_lang("fr"):
        await client.get(
            f"/api/v1/statements/{YEAR}/pdf?investor_id={investor.id}",
            headers=_auth(manager),
        )
        assert i18n.current_lang() == "fr"


# ── The document ──────────────────────────────────────────────────────────────────


async def test_the_route_serves_a_real_pdf(client, db):
    """A PDF, recognisable by its first bytes, and never an empty document.

    🔴 A PDF THAT FAILED TO BUILD MUST NOT GO OUT AT ZERO BYTES. The browser would
    download it, the reader would open nothing, and they would conclude the fund paid them
    nothing that year.
    """
    investor = await _investor_paid(db, locale="fr")
    manager = await _manager(db)

    resp = await client.get(
        f"/api/v1/statements/{YEAR}/pdf?investor_id={investor.id}",
        headers=_auth(manager),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF-")
    assert len(resp.content) > 1000


async def test_money_still_at_the_fund_is_shown_apart_and_never_added(db):
    """🔴 DECIDED IS NOT RECEIVED. Money voted and still on the fund's account is shown
    apart, with its note. Adding it in would make this document the evidence for a return
    the investor should never have filed."""
    investor = await _investor_paid(db, locale="fr")
    subscription = (
        await db.execute(
            select(Subscription).where(Subscription.investor_id == investor.id)
        )
    ).scalar_one()
    db.add(
        Distribution(
            id=uuid.uuid4(),
            subscription_id=subscription.id,
            capital_amount=Decimal("0"),
            income_amount=Decimal("7777.00"),
            currency=CURRENCY,
            decided_on=date(YEAR, 12, 28),
            paid_on=None,
        )
    )
    await db.flush()

    built = await statement_service.statement_for(
        db, investor_id=investor.id, year=YEAR
    )
    with i18n.use_lang("fr"):
        html = statement_pdf.render_html(built, statement_service.labels(YEAR))

    assert "7 777,00".replace(" ", " ") in html
    # The total received stays the one of the actual payments: 1000 + (1234.56 - 234.56).
    assert "2 000,00".replace(" ", " ") in html
    assert "9 777,00".replace(" ", " ") not in html


async def test_a_name_carrying_markup_cannot_break_the_document(db):
    """⚠️ A NAME IS TYPED BY SOMEBODY. A company name carrying `&` or `<` would silently
    break the layout of a document that leaves the fund."""
    investor = await _investor_paid(db, locale="fr", name="Durand & <Fils>")
    built = await statement_service.statement_for(
        db, investor_id=investor.id, year=YEAR
    )
    with i18n.use_lang("fr"):
        html = statement_pdf.render_html(built, statement_service.labels(YEAR))

    assert "&amp;" in html
    assert "&lt;Fils&gt;" in html
    assert "<Fils>" not in html


# ── The scope ────────────────────────────────────────────────────────────────────


async def test_an_investor_never_reads_somebody_elses_statement(client, db):
    """🔴 THE SECOND ROUTE HAS THE FIRST ONE'S SCOPE, because both read it in one place.

    A scope a parameter can widen is not a scope. Here an investor's `investor_id` query
    parameter is IGNORED rather than refused: they get their own, never a refusal, never
    the neighbour's. That is exactly the weakness a second copy of the check would have
    introduced eventually.
    """
    mine = await _investor_paid(db, locale="fr", name="Mine")
    theirs = await _investor_paid(db, locale="fr", name="Theirs")

    account = User(
        id=uuid.uuid4(),
        email=f"lecteur-{uuid.uuid4().hex[:6]}@investisseur.fr",
        hashed_password=hash_password("Motdepasse-1234"),
        account_name="Mine",
        role="investor",
    )
    db.add(account)
    await db.flush()
    mine.user_id = account.id
    await db.flush()

    resp = await client.get(
        f"/api/v1/statements/{YEAR}/pdf?investor_id={theirs.id}",
        headers=_auth(account),
    )
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].endswith(f'{mine.id}.pdf"')
    assert str(theirs.id) not in resp.headers["content-disposition"]


async def test_an_impossible_year_is_refused_on_both_routes(client, db):
    """Both routes refuse in the same place, therefore in the same way."""
    investor = await _investor_paid(db, locale="fr")
    manager = await _manager(db)

    for path in ("/api/v1/statements/1200", "/api/v1/statements/1200/pdf"):
        resp = await client.get(
            f"{path}?investor_id={investor.id}", headers=_auth(manager)
        )
        assert resp.status_code == 422, path
