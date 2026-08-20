"""What one investor received in one year, in the shape a tax return needs.

🔴 THIS IS WHAT THE CAPITAL / INCOME SPLIT WAS FOR. Every distribution has carried two
amounts since the first migration, and this module is the reason: getting your own money
back is not income, and a fund that reported one figure would overstate every investor's
taxable income by the whole of their capital repayments. None of them could detect it from
the amount they received.

🔴 THE YEAR IS THE YEAR OF PAYMENT, NEVER OF DECISION. A distribution decided on
28 December and paid on 4 January belongs to the second year, because that is when the
investor had the money. Using `decided_on` would put income on a return the investor had
already filed — and the fund's own statement would be the evidence against them.

⚠️ ONE BLOCK PER CURRENCY, and per instrument inside it. Interest on a loan and a gain on a
subscription are not the same income in any country this fund will meet, and a single total
is a figure the investor has to take apart again by hand — from data only the fund holds.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import instruments
from app.models.investor import Investor
from app.models.subscription import Subscription
from app.models.treasury import BankMovement, Contribution, Distribution
from app.core.i18n import pick


@dataclass
class Line:
    """One instrument, one currency: what it paid this investor this year."""

    instrument: str
    currency: str
    #: Taxable in most places, and under different headings by instrument.
    income_gross: Decimal = Decimal("0")
    #: Already paid to a tax authority on the investor's behalf. Usually creditable.
    withholding: Decimal = Decimal("0")
    #: Their own money coming back. Not income anywhere.
    capital_repaid: Decimal = Decimal("0")

    @property
    def income_net(self) -> Decimal:
        """What reached their account out of the income. Gross less withholding."""
        return self.income_gross - self.withholding

    @property
    def received(self) -> Decimal:
        """Everything that reached them, capital included."""
        return self.capital_repaid + self.income_net


@dataclass
class Statement:
    """One investor, one year. Nothing is stored: it is recomputed from the payments."""

    investor_id: uuid.UUID
    investor_name: str
    year: int
    lines: list[Line] = field(default_factory=list)
    #: Money still at work at the end of the year, per currency. Not a tax figure, and the
    #: first thing an investor checks before reading anything else.
    capital_at_work: dict[str, Decimal] = field(default_factory=dict)
    #: Distributions decided in this year and NOT yet paid, per currency. Shown apart and
    #: never added: an investor told they received money still sitting in the fund's account
    #: would declare income they never got.
    decided_not_paid: dict[str, Decimal] = field(default_factory=dict)

    def totals_by_currency(self) -> dict[str, dict[str, Decimal]]:
        out: dict[str, dict[str, Decimal]] = {}
        for line in self.lines:
            block = out.setdefault(
                line.currency,
                {
                    "income_gross": Decimal("0"),
                    "withholding": Decimal("0"),
                    "capital_repaid": Decimal("0"),
                    "received": Decimal("0"),
                },
            )
            block["income_gross"] += line.income_gross
            block["withholding"] += line.withholding
            block["capital_repaid"] += line.capital_repaid
            block["received"] += line.received
        return out


def labels(year: int) -> dict[str, str]:
    """The headings of a statement, in whatever language is in force RIGHT NOW.

    🔴 THE CALLER OPENS `i18n.use_lang(...)` AROUND THIS, and it is not a detail: these
    headings belong to the INVESTOR who reads the document, never to the manager who asked
    for it. A manager may pull any investor's statement and send it on, or attach it to a
    tax file; rendering the headings from the caller's `Accept-Language` would put French
    column titles on a British investor's return, and nothing in the product would look
    wrong, because the figures are identical either way.

    🔴 ONE DICTIONARY FOR THE SCREEN AND FOR THE PDF. They used to be one, because the
    PDF did not exist; the moment it did, a second copy would have drifted at the first
    correction — and the drift would live in a document that LEAVES, read by somebody who
    cannot compare it to anything.
    """
    return {
        "title": pick(f"Relevé annuel {year}", f"Annual statement {year}"),
        "instrument": pick("Instrument", "Instrument"),
        "currency": pick("Devise", "Currency"),
        "income_gross": pick("Produit brut", "Gross income"),
        "withholding": pick("Retenue à la source", "Withholding at source"),
        "income_net": pick("Produit net", "Net income"),
        "capital_repaid": pick("Capital remboursé", "Capital repaid"),
        "received": pick("Total reçu", "Total received"),
        "capital_at_work": pick("Capital au travail", "Capital at work"),
        "decided_not_paid": pick(
            "Décidé et non encore versé", "Decided and not yet paid"
        ),
        "decided_not_paid_note": pick(
            "Montré à part et jamais additionné : un investisseur à qui l'on annonce "
            "une somme encore sur le compte du fonds déclarerait un revenu qu'il n'a "
            "pas reçu.",
            "Shown apart and never added in: an investor told about money still sitting "
            "in the fund's account would declare income they never received.",
        ),
        # ⚠️ ONLY THE PDF NEEDS THESE FOUR, and they live here anyway. A second dictionary
        # << just for the document >> is exactly the copy this comment refuses.
        "totals": pick("Totaux", "Totals"),
        "nothing": pick(
            "Aucun versement sur cette année.", "No payment in this year."
        ),
        "issued_by": pick("Émis par", "Issued by"),
        "for_investor": pick("Investisseur", "Investor"),
    }


async def statement_for(
    db: AsyncSession, *, investor_id: uuid.UUID, year: int
) -> Statement:
    """Everything one investor was PAID in one calendar year, split as a return needs it."""
    investor = await db.get(Investor, investor_id)
    if investor is None:
        raise ValueError(pick("Investisseur introuvable.", "Investor not found."))

    subscriptions = (
        (
            await db.execute(
                select(Subscription).where(Subscription.investor_id == investor_id)
            )
        )
        .scalars()
        .all()
    )
    statement = Statement(
        investor_id=investor_id, investor_name=investor.display_name, year=year
    )
    if not subscriptions:
        return statement
    by_id = {s.id: s for s in subscriptions}
    ids = list(by_id)

    first = date(year, 1, 1)
    last = date(year, 12, 31)
    lines: dict[tuple[str, str], Line] = {}

    for sub_id, capital, income, withheld, paid_on, decided_on, currency in (
        await db.execute(
            select(
                Distribution.subscription_id,
                Distribution.capital_amount,
                Distribution.income_amount,
                Distribution.withholding_amount,
                Distribution.paid_on,
                Distribution.decided_on,
                Distribution.currency,
            ).where(Distribution.subscription_id.in_(ids))
        )
    ).all():
        instrument = by_id[sub_id].instrument
        if paid_on is None:
            if first <= decided_on <= last:
                statement.decided_not_paid[currency] = (
                    statement.decided_not_paid.get(currency, Decimal("0"))
                    + (capital or Decimal("0"))
                    + (income or Decimal("0"))
                )
            continue
        if not (first <= paid_on <= last):
            continue
        line = lines.setdefault(
            (instrument, currency), Line(instrument=instrument, currency=currency)
        )
        line.income_gross += income or Decimal("0")
        line.withholding += withheld or Decimal("0")
        line.capital_repaid += capital or Decimal("0")

    statement.lines = sorted(
        lines.values(),
        key=lambda x: (instruments.distribution_rank(x.instrument), x.currency),
    )

    # ⚠️ CAPITAL AT WORK IS MEASURED AT THE END OF THE YEAR, not today. A statement for 2026
    # read in 2028 must say what was at work on 31 December 2026, or it describes a position
    # the investor never held on the date the document claims to cover.
    # A contribution carries no date of its own: the date money arrived is the BANK's, on
    # the movement it was imputed against. Stamping a second one on the contribution would
    # let the two disagree, and the bank's would still be the true one.
    for amount, value_date, currency in (
        await db.execute(
            select(
                Contribution.amount,
                BankMovement.value_date,
                Contribution.currency,
            )
            .join(BankMovement, BankMovement.id == Contribution.bank_movement_id)
            .where(Contribution.subscription_id.in_(ids))
        )
    ).all():
        if value_date > last:
            continue
        statement.capital_at_work[currency] = (
            statement.capital_at_work.get(currency, Decimal("0")) + amount
        )

    for sub_id, capital, paid_on, currency in (
        await db.execute(
            select(
                Distribution.subscription_id,
                Distribution.capital_amount,
                Distribution.paid_on,
                Distribution.currency,
            ).where(Distribution.subscription_id.in_(ids))
        )
    ).all():
        if paid_on is None or paid_on > last:
            continue
        statement.capital_at_work[currency] = statement.capital_at_work.get(
            currency, Decimal("0")
        ) - (capital or Decimal("0"))

    return statement
