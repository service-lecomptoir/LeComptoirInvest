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
from app.services import valuation_service


async def flows_by_currency(
    db: AsyncSession,
    *,
    investor_id: uuid.UUID | None = None,
    fund_id: uuid.UUID | None = None,
) -> dict[str, list[Flow]]:
    """Every dated movement, grouped by currency.

    ⚠️ NEVER ONE LIST. Mixing currencies would produce a rate on a sum that is a holding
    nowhere — the same rule `portfolio_service.summarise` applies to totals, and it matters
    more here: a mixed IRR is not merely unreadable, it is arithmetically meaningless.

    `investor_id` limits it to one holder; without it the answer is the fund's own.

    🔴 AND `fund_id` IS NOT AN OPTIONAL REFINEMENT ONCE A SECOND VEHICLE EXISTS. Without it
    an investor who subscribed to two funds gets ONE rate covering both, which is a return on
    a holding that exists nowhere - and the two funds have different terms, different
    projects and different lives. Left as None it means « every vehicle », which is the right
    answer for a platform with one.
    """
    subscriptions_query = select(Subscription.id, Subscription.currency)
    if investor_id is not None:
        subscriptions_query = subscriptions_query.where(
            Subscription.investor_id == investor_id
        )
    # 🔴 None MEANS « THE UNATTACHED VEHICLE », NOT « ALL OF THEM », and it means that in
    # `distribution_service._holdings` and in `valuation_service.net_asset_value` too. One
    # convention, because the residual value below comes from those: flows covering every
    # fund divided by a residual covering one produces a TVPI of nothing in particular, and
    # it is a plausible figure.
    subscriptions_query = subscriptions_query.where(
        Subscription.fund_id.is_(fund_id)
        if fund_id is None
        else Subscription.fund_id == fund_id
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
    fund_id: uuid.UUID | None = None,
) -> list[Performance]:
    """One measure per currency, for one investor or for the whole fund.

    🔴 THE RESIDUAL VALUE IS FETCHED, NOT PASSED IN, AND THAT IS THE POINT. It used to be an
    argument nobody supplied: `valuation_service` could compute it and this module never
    asked, so TVPI answered « unknown » on a fund whose projects had all been valued. A
    module that CAN answer and is never called is the same object as a rule nobody applies.

    ⚠️ AND IT STAYS None WHEN THE VALUE IS UNKNOWN. An unvalued project makes the whole net
    asset value unknown; the measure then reports what has come back and says why the rest
    is missing, exactly as before. Nothing here invents a figure.
    """
    flows_per_currency = await flows_by_currency(
        db, investor_id=investor_id, fund_id=fund_id
    )
    out: list[Performance] = []
    for currency, flows in sorted(flows_per_currency.items()):
        residual = await valuation_service.residual_value_of(
            db,
            currency=currency,
            as_of=as_of,
            investor_id=investor_id,
            fund_id=fund_id,
        )
        out.append(
            measure(
                currency=currency, as_of=as_of, flows=flows, residual_value=residual
            )
        )
    return out


__all__ = ["flows_by_currency", "performance"]
