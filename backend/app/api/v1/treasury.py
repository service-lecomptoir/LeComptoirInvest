"""The money: statement lines, what they probably are, and what a human says they are."""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_manager
from app.database import get_db
from app.models.subscription import Subscription
from app.models.treasury import IN, BankMovement, CapitalCall
from app.models.user import User
from app.services import treasury_service

router = APIRouter(prefix="/treasury", tags=["treasury"])


class MovementIn(BaseModel):
    account_iban: str
    external_id: str | None = None
    direction: str = IN
    amount: Decimal
    currency: str
    value_date: date
    label: str | None = None
    counterparty_name: str | None = None
    counterparty_iban: str | None = None


class ProposalOut(BaseModel):
    investor_id: str | None
    capital_call_id: str | None
    basis: str
    third_party_payer: bool
    explanation: str


class MovementOut(BaseModel):
    id: uuid.UUID
    amount: Decimal
    currency: str
    value_date: date
    label: str | None
    counterparty_name: str | None
    proposal: ProposalOut | None = None


@router.post(
    "/movements", response_model=list[MovementOut], status_code=status.HTTP_201_CREATED
)
async def import_movements(
    lines: list[MovementIn],
    _: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Record statement lines, and say what each one probably is.

    ⚠️ RE-IMPORTING A STATEMENT IS NORMAL — an operator reruns yesterday's file — so a line
    already known by (account, external id) is SKIPPED rather than duplicated. Duplicating a
    200 000 € transfer would make the treasury fail in the direction that looks like good
    news, and it would look reconciled on this side.
    """
    created: list[BankMovement] = []
    for line in lines:
        if line.external_id:
            already = (
                await db.execute(
                    select(BankMovement.id).where(
                        BankMovement.account_iban == line.account_iban,
                        BankMovement.external_id == line.external_id,
                    )
                )
            ).first()
            if already:
                continue
        movement = BankMovement(**line.model_dump())
        db.add(movement)
        created.append(movement)
    await db.flush()

    out = []
    for movement in created:
        proposal = await treasury_service.propose_for(db, movement)
        out.append(
            MovementOut(
                id=movement.id,
                amount=movement.amount,
                currency=movement.currency,
                value_date=movement.value_date,
                label=movement.label,
                counterparty_name=movement.counterparty_name,
                proposal=ProposalOut(**proposal.__dict__),
            )
        )
    return out


@router.get("/unattributed", response_model=list[MovementOut])
async def list_unattributed(
    _: User = Depends(current_manager), db: AsyncSession = Depends(get_db)
):
    """Money the fund holds and cannot name. The pile that must stay short."""
    out = []
    for movement in await treasury_service.unattributed(db):
        proposal = await treasury_service.propose_for(db, movement)
        out.append(
            MovementOut(
                id=movement.id,
                amount=movement.amount,
                currency=movement.currency,
                value_date=movement.value_date,
                label=movement.label,
                counterparty_name=movement.counterparty_name,
                proposal=ProposalOut(**proposal.__dict__),
            )
        )
    return out


class AttributionIn(BaseModel):
    subscription_id: uuid.UUID
    amount: Decimal
    capital_call_id: uuid.UUID | None = None
    third_party_reason: str | None = None


@router.post("/movements/{movement_id}/attribute", status_code=status.HTTP_201_CREATED)
async def attribute(
    movement_id: uuid.UUID,
    data: AttributionIn,
    user: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """A human says whose money this is. The proposal never does it on its own."""
    movement = await db.get(BankMovement, movement_id)
    if movement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mouvement introuvable.")
    subscription = await db.get(Subscription, data.subscription_id)
    if subscription is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Souscription introuvable.")
    call = (
        await db.get(CapitalCall, data.capital_call_id)
        if data.capital_call_id
        else None
    )
    try:
        contribution = await treasury_service.attribute(
            db,
            movement=movement,
            subscription=subscription,
            amount=data.amount,
            capital_call=call,
            attributed_by=user.email,
            third_party_reason=data.third_party_reason,
        )
    except ValueError as exc:
        # 409 rather than 422: nothing about the request is malformed — the fund's state
        # refuses it, and the operator needs to read why.
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"id": str(contribution.id), "amount": str(contribution.amount)}


@router.get("/balance")
async def balance(
    _: User = Depends(current_manager), db: AsyncSession = Depends(get_db)
):
    """One balance per currency. Never a single total: a figure mixing euros and CFA francs
    is a balance nowhere, and it looks plausible because it sums real amounts."""
    return {
        c: str(a) for c, a in (await treasury_service.treasury_by_currency(db)).items()
    }
