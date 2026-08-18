"""The dated cash flows a performance figure is computed from, read from what happened.

🔴 THE DATE IS THE POINT, and it is the reason this could not be done from
`portfolio_service`. That module answers « how much », and sums are enough for it. A rate of
return needs to know WHEN each euro moved: a hundred thousand paid back after one year and
the same amount after five are the same total and a completely different performance.

⚠️ EACH SIDE TAKES ITS DATE FROM THE BANK, NOT FROM THE DECISION. A contribution is dated by
the movement that carried it, a distribution by the day it was actually paid. Using the
decision date would credit the investor with money on a day it was still in the fund's
account, and shorten every holding period by the settlement delay.

⚠️ AND A DECIDED-BUT-UNPAID DISTRIBUTION IS NOT A FLOW. It is a promise; counting it would
raise the return on the strength of a transfer that may still be rejected. Same rule as the
investor's statement, and deliberately NOT the rule the waterfall uses when it proposes —
those two answer different questions, and the difference is written down in both places.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.performance import Flow, Performance, measure
from app.models.subscription import Subscription
from app.models.treasury import BankMovement, Contribution, Distribution


async def flows_by_currency(
    db: AsyncSession, *, investor_id: uuid.UUID | None = None
) -> dict[str, list[Flow]]:
    """Every dated movement, grouped by currency.

    ⚠️ NEVER ONE LIST. Mixing currencies would produce a rate on a sum that is a holding
    nowhere — the same rule `portfolio_service.summarise` applies to totals, and it matters
    more here: a mixed IRR is not merely unreadable, it is arithmetically meaningless.

    `investor_id` limits it to one holder; without it the answer is the fund's own.
    """
    subscriptions_query = select(Subscription.id, Subscription.currency)
    if investor_id is not None:
        subscriptions_query = subscriptions_query.where(
            Subscription.investor_id == investor_id
        )
    currency_of = {
        sub_id: currency
        for sub_id, currency in (await db.execute(subscriptions_query)).all()
    }
    if not currency_of:
        return {}
    ids = list(currency_of)

    out: dict[str, list[Flow]] = {
        currency: [] for currency in set(currency_of.values())
    }

    # Money in: negative, because it left the investor.
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
        out[currency_of[sub_id]].append(Flow(on=value_date, amount=-amount))

    # Money back: positive, and GROSS of withholding. The tax was withheld from them, so it
    # is money they earned; netting it here would blame the fund's performance for a levy.
    for sub_id, capital, income, paid_on in (
        await db.execute(
            select(
                Distribution.subscription_id,
                Distribution.capital_amount,
                Distribution.income_amount,
                Distribution.paid_on,
            ).where(Distribution.subscription_id.in_(ids))
        )
    ).all():
        if paid_on is None:
            continue
        out[currency_of[sub_id]].append(Flow(on=paid_on, amount=capital + income))

    return out


async def performance(
    db: AsyncSession,
    *,
    as_of: date,
    investor_id: uuid.UUID | None = None,
    valuations: dict[str, object] | None = None,
) -> list[Performance]:
    """One measure per currency, for one investor or for the whole fund.

    `valuations` maps a currency to what is still held, valued on `as_of`. This product
    values nothing on its own: a figure only appears here because somebody recorded it, and
    without it the answer stays limited to what has already come back and says so.
    """
    supplied = valuations or {}
    return [
        measure(
            currency=currency,
            as_of=as_of,
            flows=flows,
            residual_value=supplied.get(currency),  # type: ignore[arg-type]
        )
        for currency, flows in sorted(
            (await flows_by_currency(db, investor_id=investor_id)).items()
        )
    ]


__all__ = ["flows_by_currency", "performance"]
