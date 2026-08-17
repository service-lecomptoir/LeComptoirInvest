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
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription
from app.models.treasury import CapitalCall, Contribution, Distribution


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
