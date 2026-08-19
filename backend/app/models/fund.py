"""The vehicle: what groups projects and subscribers, and whose economics they share.

🔴 UNTIL THIS EXISTED, « THE FUND » WAS THE DATABASE. Every sweep scoped its work by CURRENCY
alone — the waterfall, the net asset value, the performance — which is exactly right while
there is one vehicle and silently catastrophic the day there are two: fund A's cash would be
distributed to fund B's subscribers, and every figure would reconcile.

⚠️ A FUND IS OPTIONAL, AND THAT IS THE PRODUCT DECISION. This tool serves two models: a
crowdfunding vehicle where each project stands alone, and a structured fund grouping several.
Making the fund mandatory would force the first to invent one; making it absent would leave
the second unable to keep two vehicles apart. `fund_id` is therefore nullable everywhere, and
NULL means « the unattached pool » — a real scope, not a missing value.

🔴 THE ECONOMICS BELONG HERE, NOT ON EACH SUBSCRIPTION. A hurdle, a carry and a management fee
describe the VEHICLE: the carry is computed on everybody's surplus at once. They lived on
`Subscription.terms` because that is where a terms column existed, and the waterfall had to
refuse whenever two subscribers disagreed — a refusal that was correct and that nobody could
resolve, because there was no object to hold the answer. There is now.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk

#: Taking commitments, not yet deployed.
RAISING = "raising"
#: Money at work in projects.
INVESTING = "investing"
#: Returning capital and gains to subscribers.
HARVESTING = "harvesting"
#: Wound down. Nothing left to value, nothing left to call.
CLOSED = "closed"

FUND_STATUSES: tuple[str, ...] = (RAISING, INVESTING, HARVESTING, CLOSED)

#: Statuses in which the vehicle still holds something worth valuing. Enumerated rather than
#: written as « not closed »: a status added later must be placed here on purpose, and a test
#: by exclusion answers wrongly for every value invented after it.
OPEN_STATUSES: frozenset[str] = frozenset({RAISING, INVESTING, HARVESTING})


class Fund(Base, TimestampMixin):
    """One vehicle: its own subscribers, its own projects, its own bank account."""

    __tablename__ = "funds"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RAISING, server_default=RAISING, index=True
    )
    #: 🔴 ONE CURRENCY PER VEHICLE, and it is not a simplification. A fund holding euros and
    #: CFA francs has two treasuries, two net asset values and two waterfalls; giving it one
    #: currency column forces that reality to be modelled as two funds, which is what it is.
    currency: Mapped[str] = mapped_column(String(3), nullable=False, index=True)

    #: 🔴 THE VEHICLE'S OWN ACCOUNT, and the only honest way to split cash between funds.
    #: `treasury_by_currency` sums every movement in a currency; with two funds on one
    #: account, no rule can say whose euro is whose. When a fund declares its IBAN its cash
    #: is filtered by it; when it does not, and another fund exists, the net asset value is
    #: REFUSED rather than computed on somebody else's money.
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True, index=True)

    #: `EquityTerms` as JSON: the hurdle, the carry and the management fee, held once for the
    #: whole vehicle. NULL means the fund never agreed any, which is the crowdfunding case and
    #: leaves the waterfall exactly as it was.
    terms: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    opened_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    mandate: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    def __repr__(self) -> str:
        return f"<Fund {self.name} [{self.status}] {self.currency}>"
