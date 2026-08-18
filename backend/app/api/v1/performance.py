"""Performance: DPI, TVPI, RVPI and the rate of return, per currency.

⚠️ THE SAME SCOPING RULE AS EVERY OTHER READ. An investor sees their own performance and
nothing else; the query parameter is IGNORED for them rather than refused, because a scope
a parameter can widen is not a scope. A manager may ask for any investor, or for the fund.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, investor_scope
from app.database import get_db
from app.models.user import User
from app.services import performance_service, portfolio_service

router = APIRouter(tags=["performance"])


class PerformanceOut(BaseModel):
    currency: str
    as_of: date
    paid_in: Decimal
    distributed: Decimal
    residual_value: Decimal | None = None
    dpi: Decimal | None = None
    rvpi: Decimal | None = None
    tvpi: Decimal | None = None
    irr: Decimal | None = None
    #: 🔴 CARRIED TO THE SCREEN, NEVER DROPPED. True means the rate covers only what has
    #: already come back: it under-states an open fund, and a reader who does not know that
    #: will compare it with a full IRR and conclude the fund is doing badly.
    irr_is_realised_only: bool = True
    unavailable_reason: str | None = None


@router.get("/performance", response_model=list[PerformanceOut])
async def performance(
    as_of: date | None = None,
    investor_id: uuid.UUID | None = None,
    scope: uuid.UUID | None = Depends(investor_scope),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """One block per currency. An investor's own, or the fund's when a manager asks.

    ⚠️ `as_of` DEFAULTS TO NOTHING, and the caller must say which day it means. A server
    that filled in its own today would date an investor's report by the timezone of a
    machine, and two readers in different places would get different figures for what they
    both call « today ».
    """
    if as_of is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Préciser la date à laquelle la performance est arrêtée.",
        )
    if scope is not None:
        target = scope
    elif investor_id is not None:
        target = investor_id
    else:
        # A manager asking for nobody in particular is asking about the fund itself.
        target = None
        if (
            not user.sees_whole_fund
        ):  # pragma: no cover - investor_scope already refused
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Réservé à la gestion du fonds."
            )

    measured = await performance_service.performance(
        db, as_of=as_of, investor_id=target
    )
    return [PerformanceOut(**vars(m)) for m in measured]


class CapitalAccountOut(BaseModel):
    currency: str
    since: date
    until: date
    opening_balance: Decimal
    contributions: Decimal
    capital_returned: Decimal
    income: Decimal
    withheld: Decimal
    outstanding_commitment: Decimal
    closing_balance: Decimal
    net_paid: Decimal


@router.get("/capital-account", response_model=list[CapitalAccountOut])
async def capital_account(
    since: date,
    until: date,
    investor_id: uuid.UUID | None = None,
    scope: uuid.UUID | None = Depends(investor_scope),
    db: AsyncSession = Depends(get_db),
):
    """The capital account of one investor over a period, one line per currency.

    ⚠️ BOTH DATES ARE REQUIRED AND NEITHER IS GUESSED. « This quarter » is a different
    period depending on who asks and where they are; a statement that dated itself would
    reconcile against the investor's bank on some days and not others.
    """
    target = scope if scope is not None else investor_id
    if target is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Préciser l'investisseur dont on veut le relevé de compte.",
        )
    try:
        lines = await portfolio_service.capital_account(
            db, target, since=since, until=until
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return [
        CapitalAccountOut(
            **vars(line),
            closing_balance=line.closing_balance,
            net_paid=line.net_paid,
        )
        for line in lines
    ]
