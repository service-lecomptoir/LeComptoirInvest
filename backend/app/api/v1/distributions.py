"""Paying the investors: propose, decide, pay. Three steps, and never one.

🔴 THE THREE ARE SEPARATE ENDPOINTS BECAUSE THEY ARE SEPARATE FACTS. A single « distribuer »
button would collapse a proposal, a decision and a transfer into one row, and the fund would
be unable to answer the only three questions that get asked afterwards: what did the rule
say, what did we decide, and when did the money actually leave.
"""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_manager, investor_scope
from app.database import get_db
from app.models.subscription import Subscription
from app.models.treasury import BankMovement, Distribution
from app.models.user import User
from app.services import distribution_service
from app.core.i18n import pick

router = APIRouter(tags=["distributions"])


class ShareOut(BaseModel):
    subscription_id: uuid.UUID
    investor_id: uuid.UUID
    investor_name: str
    instrument: str
    capital_amount: Decimal
    income_amount: Decimal


class WaterfallOut(BaseModel):
    currency: str
    available: Decimal
    as_of: date
    shares: list[ShareOut]
    distributed: Decimal
    undistributed: Decimal
    debt_remaining: Decimal
    #: ⚠️ SHOWN, NEVER FOLDED INTO `distributed` ALONE. The manager's carry leaves the
    #: subscribers' pocket: a screen that only displayed the total would let it pass as
    #: part of what the investors received.
    carried_interest: Decimal = Decimal("0")
    #: ⚠️ SHOWN BESIDE THE CARRY, NEVER ADDED TO IT. A fee is owed whether the fund performs
    #: or not; one combined figure would hide a flat year in which the manager was still paid.
    management_fee: Decimal = Decimal("0")
    #: What is still missing before the hurdle is met. Zero means the carry has begun.
    preferred_remaining: Decimal = Decimal("0")
    blocked_reason: str | None = None
    unknown: list[str] = []


def _to_out(waterfall) -> WaterfallOut:
    return WaterfallOut(
        currency=waterfall.currency,
        available=waterfall.available,
        as_of=waterfall.as_of,
        shares=[
            ShareOut(
                subscription_id=s.subscription_id,
                investor_id=s.investor_id,
                investor_name=s.investor_name,
                instrument=s.instrument,
                capital_amount=s.capital_amount,
                income_amount=s.income_amount,
            )
            for s in waterfall.shares
        ],
        distributed=waterfall.distributed,
        undistributed=waterfall.undistributed,
        debt_remaining=waterfall.debt_remaining,
        carried_interest=waterfall.carried_interest,
        management_fee=waterfall.management_fee,
        preferred_remaining=waterfall.preferred_remaining,
        blocked_reason=waterfall.blocked_reason,
        unknown=[reason for _, reason in waterfall.unknown],
    )


class ProposeIn(BaseModel):
    currency: str
    #: Which vehicle is distributing. ⚠️ OMITTED MEANS « the one no fund row was created
    #: for », not « all of them »: `distribution_service` reads it that way, and so do the
    #: net asset value and the performance. One convention, or two funds share a waterfall.
    fund_id: uuid.UUID | None = None
    amount: Decimal
    as_of: date
    repay_capital: bool = False


@router.post("/distributions/propose", response_model=WaterfallOut)
async def propose(
    data: ProposeIn,
    _: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """What the rule says, shown before anything is written.

    ⚠️ A PROPOSAL WRITES NOTHING, including when it is blocked. The fund looks at it, and
    a blocked proposal is the most useful answer this endpoint gives: it names the debt that
    has to be served first, and the amount.
    """
    if data.amount <= 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            pick("Le montant doit être positif.", "The amount has to be positive."),
        )
    waterfall = await distribution_service.propose(
        db,
        currency=data.currency.upper(),
        amount=data.amount,
        as_of=data.as_of,
        fund_id=data.fund_id,
        repay_capital=data.repay_capital,
    )
    return _to_out(waterfall)


class DecideIn(ProposeIn):
    decided_on: date
    #: Tax withheld at source, per subscription. Supplied by the fund, never inferred: it
    #: depends on the investor's country and on treaties, and a wrong default is a real
    #: amount taken from somebody.
    withholding: dict[uuid.UUID, Decimal] = {}


@router.post("/distributions", status_code=status.HTTP_201_CREATED)
async def decide(
    data: DecideIn,
    _: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Record the distribution the fund decided. Recomputed here, never trusted from the UI.

    🔴 THE WATERFALL IS RUN AGAIN SERVER-SIDE. Accepting the shares the browser posted would
    let the ordering be edited in a developer console — and the one rule this product exists
    to enforce is exactly the one that would be bypassed. The screen shows a proposal; the
    server decides what is written.
    """
    waterfall = await distribution_service.propose(
        db,
        currency=data.currency.upper(),
        amount=data.amount,
        as_of=data.as_of,
        fund_id=data.fund_id,
        repay_capital=data.repay_capital,
    )
    if waterfall.unknown or not waterfall.shares:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            waterfall.blocked_reason
            or pick(
                "Cette répartition ne distribue rien.",
                "This split distributes nothing.",
            ),
        )
    created = await distribution_service.record(
        db, waterfall, decided_on=data.decided_on, withholding=data.withholding
    )
    return {
        "decided": len(created),
        "ids": [str(d.id) for d in created],
        "blocked_reason": waterfall.blocked_reason,
    }


class DistributionOut(BaseModel):
    id: uuid.UUID
    subscription_id: uuid.UUID
    capital_amount: Decimal
    income_amount: Decimal
    withholding_amount: Decimal
    currency: str
    decided_on: date
    paid_on: date | None


@router.get("/distributions", response_model=list[DistributionOut])
async def list_distributions(
    scope: uuid.UUID | None = Depends(investor_scope),
    db: AsyncSession = Depends(get_db),
):
    """Every distribution, or only this investor's. The scope decides, not a parameter."""
    query = select(Distribution).order_by(Distribution.decided_on.desc())
    if scope is not None:
        query = query.join(
            Subscription, Subscription.id == Distribution.subscription_id
        ).where(Subscription.investor_id == scope)
    rows = (await db.execute(query)).scalars().all()
    return [
        DistributionOut(**{k: getattr(r, k) for k in DistributionOut.model_fields})
        for r in rows
    ]


class PayIn(BaseModel):
    bank_movement_id: uuid.UUID
    paid_on: date | None = None


@router.post("/distributions/{distribution_id}/pay")
async def pay(
    distribution_id: uuid.UUID,
    data: PayIn,
    _: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """The transfer left. Attach it, and only then is the investor paid."""
    distribution = await db.get(Distribution, distribution_id)
    if distribution is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            pick("Distribution introuvable.", "Distribution not found."),
        )
    movement = await db.get(BankMovement, data.bank_movement_id)
    if movement is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            pick("Mouvement introuvable.", "Movement not found."),
        )
    try:
        await distribution_service.pay(
            db, distribution=distribution, movement=movement, paid_on=data.paid_on
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"id": str(distribution.id), "paid_on": str(distribution.paid_on)}


@router.get("/distributions/debt")
async def debt(
    currency: str,
    as_of: date,
    _: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """What the fund owes its lenders today, beside the cash it holds.

    A balance shown without the debt already carried is the figure that gets distributed.
    """
    total, unknown = await distribution_service.owed_to_lenders(
        db, currency=currency.upper(), as_of=as_of
    )
    return {
        "currency": currency.upper(),
        "as_of": str(as_of),
        "owed_to_lenders": str(total),
        "unmeasurable": [reason for _, reason in unknown],
    }
