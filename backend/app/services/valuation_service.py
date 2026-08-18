"""The fund's net asset value, and what an investor's share of it is worth.

🔴 THIS IS WHAT THE PERFORMANCE MODULE WAS WAITING FOR. TVPI, RVPI and a full rate of return
all need the value of what is still held; without it they answered « unknown », which was
honest and incomplete. This module supplies the missing half — and only when somebody has
actually judged the value. It computes no opinion of its own.

NET ASSET VALUE, IN THE ORDER THE MONEY WOULD ACTUALLY COME BACK:

    NAV = value of the open projects + cash at the bank − what the lenders are owed

⚠️ THE DEBT IS SUBTRACTED, AND IT IS NOT A DETAIL. A lender is a creditor: their capital and
their accrued interest leave before any subscriber sees a euro. A « net asset value » that
ignored the debt would tell an equity holder they own a share of money that is spoken for,
and the error grows with exactly the leverage that made it worth reporting.

🔴 AN UNVALUED PROJECT IS NOT WORTH ZERO, AND THE TOTAL IS THEN REFUSED. This is the same
discipline as `accrual.amount_due` and `performance.measure`: a fund holding four projects
of which one was never valued has an UNKNOWN net asset value, not one short by a quarter.
Filling the gap with a nil would under-state the fund — and an under-stated value is the
error nobody disputes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import instruments
from app.models.project import ACTIVE, STUDY, Project, ProjectValuation
from app.models.subscription import Subscription
from app.models.treasury import IN, BankMovement, Contribution, Distribution
from app.services import distribution_service

#: Projects still holding money. A closed or written-off project has nothing left to value:
#: what came back is already in the treasury, and what was lost is already a loss.
OPEN_STATUSES: tuple[str, ...] = (STUDY, ACTIVE)


@dataclass(frozen=True)
class NetAssetValue:
    """What the fund is worth on a date, in one currency, or why that cannot be said."""

    currency: str
    as_of: date
    projects: Decimal = Decimal("0")
    cash: Decimal = Decimal("0")
    #: What lenders are owed, subtracted from the total. Positive here, deducted below.
    debt: Decimal = Decimal("0")
    #: Projects with no valuation on or before `as_of`, by name. Non-empty means `total`
    #: is None and the answer is « unknown ».
    unvalued: list[str] = field(default_factory=list)
    unavailable_reason: str | None = None

    @property
    def total(self) -> Decimal | None:
        if self.unavailable_reason is not None:
            return None
        return self.projects + self.cash - self.debt

    @property
    def is_known(self) -> bool:
        return self.unavailable_reason is None


async def _latest_valuations(
    db: AsyncSession, *, currency: str, as_of: date
) -> dict[uuid.UUID, Decimal]:
    """The most recent valuation of each project ON OR BEFORE `as_of`.

    ⚠️ NEVER A LATER ONE. A June valuation must not appear in a March report: an as-of date
    that reached forward would let a fund publish a quarter using knowledge it did not have,
    which is the one thing a dated report exists to prevent.
    """
    rows = (
        await db.execute(
            select(
                ProjectValuation.project_id,
                ProjectValuation.valued_on,
                ProjectValuation.amount,
            )
            .where(
                ProjectValuation.currency == currency,
                ProjectValuation.valued_on <= as_of,
            )
            .order_by(ProjectValuation.project_id, ProjectValuation.valued_on)
        )
    ).all()
    latest: dict[uuid.UUID, tuple[date, Decimal]] = {}
    for project_id, valued_on, amount in rows:
        known = latest.get(project_id)
        if known is None or valued_on >= known[0]:
            latest[project_id] = (valued_on, amount)
    return {project_id: amount for project_id, (_, amount) in latest.items()}


async def net_asset_value(
    db: AsyncSession, *, currency: str, as_of: date
) -> NetAssetValue:
    """What the fund is worth on `as_of`, or the reason it cannot be totalled."""
    open_projects = (
        (
            await db.execute(
                select(Project).where(
                    Project.currency == currency, Project.status.in_(OPEN_STATUSES)
                )
            )
        )
        .scalars()
        .all()
    )
    valuations = await _latest_valuations(db, currency=currency, as_of=as_of)

    unvalued = [p.name for p in open_projects if p.id not in valuations]
    projects_worth = sum(
        (valuations[p.id] for p in open_projects if p.id in valuations), Decimal("0")
    )

    cash = Decimal("0")
    for direction, amount, value_date in (
        await db.execute(
            select(
                BankMovement.direction, BankMovement.amount, BankMovement.value_date
            ).where(BankMovement.currency == currency, BankMovement.value_date <= as_of)
        )
    ).all():
        cash += amount if direction == IN else -amount

    debt, unmeasurable = await distribution_service.owed_to_lenders(
        db, currency=currency, as_of=as_of
    )

    reason = None
    if unvalued:
        reason = (
            f"{len(unvalued)} projet(s) ouvert(s) sans valorisation à cette date "
            f"({', '.join(unvalued)}) : l'actif net ne peut pas être totalisé, et un projet "
            f"non valorisé ne vaut pas zéro."
        )
    elif unmeasurable:
        reason = (
            f"{len(unmeasurable)} prêt(s) dont le montant dû n'est pas calculable : la dette "
            f"à déduire de l'actif net n'a pas de valeur connue."
        )

    return NetAssetValue(
        currency=currency,
        as_of=as_of,
        projects=projects_worth,
        cash=cash,
        debt=debt,
        unvalued=unvalued,
        unavailable_reason=reason,
    )


async def residual_value_of(
    db: AsyncSession,
    *,
    currency: str,
    as_of: date,
    investor_id: uuid.UUID | None = None,
) -> Decimal | None:
    """The share of the net asset value attributable to one investor, or to every subscriber.

    🔴 PRO RATA TO CAPITAL AT WORK, the same basis the waterfall distributes on. Any other
    key — capital committed, capital contributed, number of subscriptions — would make an
    investor's reported share disagree with what they would actually be paid, and the two
    figures sit on the same screen.

    ⚠️ THE LENDERS' SHARE IS NOT IN HERE. `net_asset_value` has already deducted the debt, so
    what remains belongs to the subscribers. Splitting the gross among everybody would credit
    a lender with an upside their contract caps them out of, and dilute the subscribers who
    carry the risk.

    Returns None when the value is unknown, which the caller must carry as « unknown » and
    never as zero.
    """
    nav = await net_asset_value(db, currency=currency, as_of=as_of)
    if not nav.is_known:
        return None
    attributable = nav.total
    if attributable is None or attributable <= 0:
        # A fund worth nothing (or less) leaves its subscribers nothing: that is a real
        # answer and not a missing one, so it is a figure rather than a None.
        return Decimal("0")

    subscriptions = (
        (
            await db.execute(
                select(Subscription).where(
                    Subscription.currency == currency,
                    Subscription.instrument == instruments.EQUITY,
                    Subscription.converted_on.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not subscriptions:
        return Decimal("0")
    ids = [s.id for s in subscriptions]

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
    for sub_id, capital, paid_on in (
        await db.execute(
            select(
                Distribution.subscription_id,
                Distribution.capital_amount,
                Distribution.paid_on,
            ).where(Distribution.subscription_id.in_(ids))
        )
    ).all():
        if paid_on is None or paid_on > as_of:
            continue
        repaid[sub_id] = repaid.get(sub_id, Decimal("0")) + (capital or Decimal("0"))

    at_work = {
        s.id: contributed.get(s.id, Decimal("0")) - repaid.get(s.id, Decimal("0"))
        for s in subscriptions
    }
    total_at_work = sum((v for v in at_work.values() if v > 0), Decimal("0"))
    if total_at_work <= 0:
        return Decimal("0")

    if investor_id is None:
        return attributable

    mine = sum(
        (
            at_work[s.id]
            for s in subscriptions
            if s.investor_id == investor_id and at_work[s.id] > 0
        ),
        Decimal("0"),
    )
    return attributable * mine / total_at_work


__all__ = ["NetAssetValue", "OPEN_STATUSES", "net_asset_value", "residual_value_of"]
