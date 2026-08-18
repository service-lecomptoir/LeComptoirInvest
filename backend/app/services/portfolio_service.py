"""What an investor holds, derived from what actually happened.

🔴 NOTHING HERE IS STORED. Every figure is recomputed from the contributions and the
distributions, and that is the whole design: a position kept in a column is a second ledger,
and two ledgers disagree — silently, and in the investor's disfavour as often as not.

The sister product records the same rule for its rent arrears: « outstanding is the payment
balance, never rebuilt from the movements ». Here it is the opposite direction and the same
principle — one source, and everything else read from it.

THE SECOND INVARIANT, the one an investor checks first:

    capital still at work = Σ contributions − Σ capital repaid

If that figure is wrong, nothing else on their statement means anything. It is the reason
distributions are split between capital and income at the point they are recorded: a single
amount makes this subtraction impossible, and no amount of presentation afterwards recovers
it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription
from app.models.treasury import BankMovement, CapitalCall, Contribution, Distribution


@dataclass(frozen=True)
class Position:
    """One subscription, seen as its holder sees it."""

    subscription_id: uuid.UUID
    instrument: str
    currency: str
    #: What was promised.
    committed: Decimal
    #: What the fund has asked for so far.
    called: Decimal
    #: What actually arrived and was attributed.
    contributed: Decimal
    #: Their own money given back.
    capital_repaid: Decimal
    #: What they earned: interest, preferred return, gain.
    income_received: Decimal
    #: Tax withheld at source before payment.
    withheld: Decimal

    @property
    def outstanding_commitment(self) -> Decimal:
        """Still to be paid in. What a call can still ask for.

        ⚠️ Never negative on screen even if over-paid: money paid ahead of any call is a
        real thing, and a negative « remaining commitment » reads as an error rather than as
        an advance.
        """
        return max(self.committed - self.contributed, Decimal("0"))

    @property
    def capital_at_work(self) -> Decimal:
        """The figure an investor checks first."""
        return self.contributed - self.capital_repaid

    @property
    def net_received(self) -> Decimal:
        """What actually reached their account, withholding deducted."""
        return self.capital_repaid + self.income_received - self.withheld


async def positions_of(db: AsyncSession, investor_id: uuid.UUID) -> list[Position]:
    """Every holding of one investor, computed from the facts.

    Four aggregate queries rather than one per subscription: an investor with a dozen
    holdings would otherwise issue fifty, and this is the endpoint their portal calls on
    every visit.
    """
    subscriptions = (
        (
            await db.execute(
                select(Subscription)
                .where(Subscription.investor_id == investor_id)
                .order_by(Subscription.signed_on)
            )
        )
        .scalars()
        .all()
    )
    if not subscriptions:
        return []
    ids = [s.id for s in subscriptions]

    called: dict[uuid.UUID, Decimal] = {}
    for sub_id, amount in (
        await db.execute(
            select(CapitalCall.subscription_id, CapitalCall.amount).where(
                CapitalCall.subscription_id.in_(ids)
            )
        )
    ).all():
        called[sub_id] = called.get(sub_id, Decimal("0")) + amount

    contributed: dict[uuid.UUID, Decimal] = {}
    for sub_id, amount in (
        await db.execute(
            select(Contribution.subscription_id, Contribution.amount).where(
                Contribution.subscription_id.in_(ids)
            )
        )
    ).all():
        contributed[sub_id] = contributed.get(sub_id, Decimal("0")) + amount

    repaid: dict[uuid.UUID, Decimal] = {}
    income: dict[uuid.UUID, Decimal] = {}
    withheld: dict[uuid.UUID, Decimal] = {}
    for sub_id, capital, earned, tax, paid_on in (
        await db.execute(
            select(
                Distribution.subscription_id,
                Distribution.capital_amount,
                Distribution.income_amount,
                Distribution.withholding_amount,
                Distribution.paid_on,
            ).where(Distribution.subscription_id.in_(ids))
        )
    ).all():
        # ⚠️ ONLY WHAT WAS PAID COUNTS. A distribution decided and not yet sent is a real
        # state, and counting it would tell an investor they have received money that is
        # still in the fund's account.
        if paid_on is None:
            continue
        repaid[sub_id] = repaid.get(sub_id, Decimal("0")) + (capital or Decimal("0"))
        income[sub_id] = income.get(sub_id, Decimal("0")) + (earned or Decimal("0"))
        withheld[sub_id] = withheld.get(sub_id, Decimal("0")) + (tax or Decimal("0"))

    return [
        Position(
            subscription_id=s.id,
            instrument=s.instrument,
            currency=s.currency,
            committed=s.amount,
            called=called.get(s.id, Decimal("0")),
            contributed=contributed.get(s.id, Decimal("0")),
            capital_repaid=repaid.get(s.id, Decimal("0")),
            income_received=income.get(s.id, Decimal("0")),
            withheld=withheld.get(s.id, Decimal("0")),
        )
        for s in subscriptions
    ]


@dataclass(frozen=True)
class CapitalAccount:
    """One investor's capital account over a period, in one currency.

    🔴 THE OPENING BALANCE IS NOT A STORED FIGURE. It is what the account held on the day
    before the period began, recomputed from the movements — the same rule as everywhere
    else in this module. A carried-forward balance kept in a column is a second ledger, and
    the day it disagrees with the movements nobody can say which one is wrong.

    ⚠️ THE PERIOD IS INCLUSIVE AT BOTH ENDS, and it has to be said: an investor comparing a
    quarterly statement with their bank will otherwise find one transfer on neither side, or
    on both.
    """

    currency: str
    since: date
    until: date
    #: Capital at work the day before `since`.
    opening_balance: Decimal
    #: Money paid in during the period.
    contributions: Decimal
    #: Their own capital given back during the period.
    capital_returned: Decimal
    #: What they earned during the period, before withholding.
    income: Decimal
    #: Tax withheld at source during the period.
    withheld: Decimal
    #: Still callable at the end of the period.
    outstanding_commitment: Decimal

    @property
    def closing_balance(self) -> Decimal:
        """Capital at work at the end of the period.

        ⚠️ INCOME DOES NOT ENTER IT. A distribution of profit does not reduce the capital
        the investor has at work; only their own money coming back does. Folding the two
        would shrink the base every future return is computed on, and understate it forever.
        """
        return self.opening_balance + self.contributions - self.capital_returned

    @property
    def net_paid(self) -> Decimal:
        """What actually reached their account during the period."""
        return self.capital_returned + self.income - self.withheld


async def capital_account(
    db: AsyncSession, investor_id: uuid.UUID, *, since: date, until: date
) -> list[CapitalAccount]:
    """The capital account of one investor, one line per currency.

    This is the statement an institutional holder asks for every quarter, and the one the
    positions endpoint cannot give: positions answer « where do I stand today », a capital
    account answers « what moved between these two dates, and what did I hold on either
    side ». The second cannot be derived from the first.
    """
    if until < since:
        raise ValueError(
            "La période se termine avant de commencer : aucun relevé ne peut être établi."
        )

    subscriptions = (
        (
            await db.execute(
                select(Subscription).where(Subscription.investor_id == investor_id)
            )
        )
        .scalars()
        .all()
    )
    if not subscriptions:
        return []
    currency_of = {s.id: s.currency for s in subscriptions}
    ids = list(currency_of)

    blank = {
        "opening": Decimal("0"),
        "contributions": Decimal("0"),
        "capital_returned": Decimal("0"),
        "income": Decimal("0"),
        "withheld": Decimal("0"),
    }
    ledger: dict[str, dict[str, Decimal]] = {
        currency: dict(blank) for currency in set(currency_of.values())
    }

    for sub_id, amount, value_date in (
        await db.execute(
            select(
                Contribution.subscription_id,
                Contribution.amount,
                BankMovement.value_date,
            )
            .join(BankMovement, BankMovement.id == Contribution.bank_movement_id)
            .where(Contribution.subscription_id.in_(ids))
        )
    ).all():
        block = ledger[currency_of[sub_id]]
        if value_date < since:
            block["opening"] += amount
        elif value_date <= until:
            block["contributions"] += amount

    for sub_id, capital, earned, tax, paid_on in (
        await db.execute(
            select(
                Distribution.subscription_id,
                Distribution.capital_amount,
                Distribution.income_amount,
                Distribution.withholding_amount,
                Distribution.paid_on,
            ).where(Distribution.subscription_id.in_(ids))
        )
    ).all():
        if paid_on is None:
            continue  # decided, not paid: not a movement on anybody's account
        block = ledger[currency_of[sub_id]]
        if paid_on < since:
            block["opening"] -= capital or Decimal("0")
        elif paid_on <= until:
            block["capital_returned"] += capital or Decimal("0")
            block["income"] += earned or Decimal("0")
            block["withheld"] += tax or Decimal("0")

    committed: dict[str, Decimal] = {}
    contributed_total: dict[str, Decimal] = {}
    for s in subscriptions:
        committed[s.currency] = committed.get(s.currency, Decimal("0")) + s.amount
    for currency, block in ledger.items():
        contributed_total[currency] = block["opening"] + block["contributions"]

    return [
        CapitalAccount(
            currency=currency,
            since=since,
            until=until,
            opening_balance=block["opening"],
            contributions=block["contributions"],
            capital_returned=block["capital_returned"],
            income=block["income"],
            withheld=block["withheld"],
            # ⚠️ Measured on what was CONTRIBUTED, not on what is still at work: capital
            # already returned does not become callable again.
            outstanding_commitment=max(
                committed.get(currency, Decimal("0"))
                - (block["opening"] + block["contributions"]),
                Decimal("0"),
            ),
        )
        for currency, block in sorted(ledger.items())
    ]


def summarise(positions: list[Position]) -> dict[str, dict[str, Decimal]]:
    """Totals PER CURRENCY. Never one figure.

    An investor holding euros and CFA francs has two portfolios, and adding them would give
    a number that is a holding nowhere. The screen shows one block per currency, which is
    also how their bank shows it.
    """
    out: dict[str, dict[str, Decimal]] = {}
    for position in positions:
        block = out.setdefault(
            position.currency,
            {
                "committed": Decimal("0"),
                "contributed": Decimal("0"),
                "capital_at_work": Decimal("0"),
                "income_received": Decimal("0"),
                "outstanding_commitment": Decimal("0"),
            },
        )
        block["committed"] += position.committed
        block["contributed"] += position.contributed
        block["capital_at_work"] += position.capital_at_work
        block["income_received"] += position.income_received
        block["outstanding_commitment"] += position.outstanding_commitment
    return out
