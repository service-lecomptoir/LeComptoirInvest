"""The vehicles: what groups projects and subscribers, and whose economics they share."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_manager, current_user
from app.core.instruments import EquityTerms
from app.database import get_db
from app.models.fund import FUND_STATUSES, RAISING, Fund
from app.models.user import User
from app.services import valuation_service
from app.core.i18n import pick

router = APIRouter(prefix="/funds", tags=["funds"])


class FundTermsIn(BaseModel):
    """The vehicle's economics, held once for everybody it serves."""

    preferred_return: float = Field(0.0, ge=0)
    carried_interest: float = Field(0.0, ge=0, le=1)
    management_fee: float = Field(0.0, ge=0, le=1)


class FundIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    currency: str = Field(..., min_length=3, max_length=3)
    #: The vehicle's own bank account. ⚠️ Without it, and with another fund in existence, the
    #: net asset value refuses to total: a statement line says nothing about which fund the
    #: euro was for, and splitting shared cash would be an invention that reconciles.
    iban: str | None = Field(None, max_length=34)
    terms: FundTermsIn | None = None
    opened_on: date | None = None
    mandate: str | None = None


class FundOut(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    currency: str
    iban: str | None = None
    terms: dict | None = None
    opened_on: date | None = None
    closed_on: date | None = None
    mandate: str | None = None
    #: 🔴 CARRIED TO THE SCREEN. A fund with no account of its own, while another exists,
    #: cannot have its net asset value computed — and the reader has to know that before
    #: they go looking for a figure that will not come.
    cash_is_separable: bool = True


def _out(fund: Fund, *, cash_is_separable: bool = True) -> FundOut:
    return FundOut(
        id=fund.id,
        name=fund.name,
        status=fund.status,
        currency=fund.currency,
        iban=fund.iban,
        terms=fund.terms,
        opened_on=fund.opened_on,
        closed_on=fund.closed_on,
        mandate=fund.mandate,
        cash_is_separable=cash_is_separable,
    )


@router.get("", response_model=list[FundOut])
async def list_funds(
    _: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    """Every vehicle, and whether each one's cash can be told apart from the others'."""
    funds = (await db.execute(select(Fund).order_by(Fund.name))).scalars().all()
    several = len(funds) > 1
    return [
        _out(fund, cash_is_separable=bool(fund.iban) or not several) for fund in funds
    ]


@router.post("", response_model=FundOut, status_code=status.HTTP_201_CREATED)
async def create_fund(
    data: FundIn, _: User = Depends(current_manager), db: AsyncSession = Depends(get_db)
):
    """Open a vehicle.

    ⚠️ THE TERMS ARE VALIDATED AGAINST `EquityTerms` RATHER THAN STORED AS FREE JSON. A
    hurdle of « 8 » instead of « 0.08 » is a hundred-fold error that reads as a plausible
    number, and it would only surface as a carry of nothing on the first distribution.
    """
    if data.terms is not None:
        # Round-tripping through the dataclass is what proves the shape: an unknown key or a
        # missing one fails here, not on the day money is being split.
        EquityTerms(**data.terms.model_dump())

    fund = Fund(
        name=data.name.strip(),
        status=RAISING,
        currency=data.currency.upper(),
        iban=(data.iban or "").replace(" ", "").upper() or None,
        terms=data.terms.model_dump() if data.terms else None,
        opened_on=data.opened_on,
        mandate=data.mandate,
    )
    db.add(fund)
    await db.flush()
    return _out(fund)


class FundStatusIn(BaseModel):
    status: str
    closed_on: date | None = None


@router.post("/{fund_id}/status", response_model=FundOut)
async def set_status(
    fund_id: uuid.UUID,
    data: FundStatusIn,
    _: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Move the vehicle through its life: raising, investing, harvesting, closed.

    ⚠️ CLOSING IS NOT UNDOING. A closed fund holds nothing left to value and nothing left to
    call; the status is what tells the net asset value to stop asking for a valuation of its
    projects. It is recorded with a date because « since when » is the first question asked
    of a wind-down.
    """
    fund = await db.get(Fund, fund_id)
    if fund is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, pick("Fonds introuvable.", "Fund not found.")
        )
    if data.status not in FUND_STATUSES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            pick(
                f"Statut inconnu : {data.status!r}. Attendu : "
                f"{', '.join(FUND_STATUSES)}.",
                f"Unknown status: {data.status!r}. Expected: "
                f"{', '.join(FUND_STATUSES)}.",
            ),
        )
    fund.status = data.status
    fund.closed_on = data.closed_on
    await db.flush()
    return _out(fund)


class NetAssetValueOut(BaseModel):
    """What the vehicle is worth on a given day, or the reason it cannot be said."""

    currency: str
    as_of: date
    projects: Decimal
    cash: Decimal
    debt_to_lenders: Decimal
    #: Projects with no valuation on or before `as_of`. Named, not counted: « 2 projets non
    #: valorises » sends the reader hunting; their names send them to the two records.
    unvalued: list[str] = []
    total: Decimal | None = None
    #: 🔴 REACHES THE SCREEN. A project nobody valued does not make the fund worth less;
    #: it makes the total unknown, and a zero in its place would understate every figure
    #: derived from it - which is the error nobody disputes.
    unavailable_reason: str | None = None


@router.get("/net-asset-value", response_model=list[NetAssetValueOut])
async def fund_net_asset_value(
    as_of: date,
    currency: str,
    fund_id: uuid.UUID | None = None,
    _: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """The headline figure a fund is judged on, which had no route at all until now.

    🔴 IT WAS COMPUTED AND UNREACHABLE. `valuation_service.net_asset_value` totals the
    projects, adds the cash and deducts what the lenders are owed; the only way to see any
    of it was sideways, through the residual value buried inside a performance. A function
    that answers a question nobody can ask is the same object as a rule nobody applies.

    ⚠️ `fund_id` OMITTED MEANS « the vehicle no fund row was created for », the same reading
    the waterfall and the performance use. It is not « every fund added together »: cash
    cannot be split between vehicles that share an account, which is exactly what
    `cash_is_separable` warns about on the list above.
    """
    value = await valuation_service.net_asset_value(
        db, currency=currency.upper(), as_of=as_of, fund_id=fund_id
    )
    return [
        NetAssetValueOut(
            currency=value.currency,
            as_of=value.as_of,
            projects=value.projects,
            cash=value.cash,
            debt_to_lenders=value.debt,
            unvalued=value.unvalued,
            total=value.total,
            unavailable_reason=value.unavailable_reason,
        )
    ]
