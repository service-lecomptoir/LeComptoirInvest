"""The money: statement lines, what they probably are, and what a human says they are."""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_manager, investor_scope
from app.core import camt
from app.core import fund_time
from app.database import get_db
from app.models.subscription import Subscription
from app.models.treasury import IN, BankMovement, CapitalCall
from app.models.user import User
from app.services import call_chasing_service, treasury_service

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


class CamtImportOut(BaseModel):
    #: Movements actually created. Fewer than the file holds when some were already known.
    imported: list[MovementOut]
    #: Lines the file held and this import did not create, with the reason, one per line.
    #: 🔴 NEVER SUMMARISED INTO A COUNT. « 3 lignes ignorées » is unactionable; a statement
    #: quietly short of one entry reconciles to a figure that is wrong and looks right.
    refused: list[str] = []
    #: Already known by (account, external id), so skipped rather than duplicated.
    already_known: int = 0


@router.post(
    "/movements/camt", response_model=CamtImportOut, status_code=status.HTTP_201_CREATED
)
async def import_camt(
    file: UploadFile = File(...),
    _: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Import a CAMT.053 statement from the bank, and say what each line probably is.

    🔴 THE MATCHING ENGINE EXISTED AND HAD NOTHING TO EAT. `matching.propose` ties a transfer
    to a subscription by its reference, its virtual IBAN and its payer name; the only way to
    feed it was somebody retyping a statement. Retyped money carries a typo, and the typo
    lands on the reference — the single field the whole matching rests on.

    ⚠️ RE-IMPORTING THE SAME FILE IS NORMAL and must change nothing: a line already known by
    (account, external id) is skipped, exactly as in the manual import. Duplicating a
    200 000 € transfer would make the treasury wrong in the direction that looks like good
    news.
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Fichier vide.")
    parsed = camt.parse(raw)
    if not parsed.lines and parsed.refused:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Aucun mouvement n'a pu être lu : " + " | ".join(parsed.refused[:5]),
        )

    created: list[BankMovement] = []
    already = 0
    for line in parsed.lines:
        if line.external_id:
            known = (
                await db.execute(
                    select(BankMovement.id).where(
                        BankMovement.account_iban == line.account_iban,
                        BankMovement.external_id == line.external_id,
                    )
                )
            ).first()
            if known:
                already += 1
                continue
        movement = BankMovement(
            account_iban=line.account_iban,
            external_id=line.external_id,
            direction=line.direction,
            amount=line.amount,
            currency=line.currency,
            value_date=line.value_date,
            label=line.label,
            counterparty_name=line.counterparty_name,
            counterparty_iban=line.counterparty_iban,
        )
        db.add(movement)
        created.append(movement)
    await db.flush()

    imported = []
    for movement in created:
        proposal = await treasury_service.propose_for(db, movement)
        imported.append(
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
    return CamtImportOut(
        imported=imported, refused=parsed.refused, already_known=already
    )


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
            today=fund_time.platform_today(),
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


class CallIn(BaseModel):
    subscription_id: uuid.UUID
    amount: Decimal
    called_on: date
    due_on: date


class CallOut(BaseModel):
    id: uuid.UUID
    subscription_id: uuid.UUID
    reference: str
    amount: Decimal
    currency: str
    called_on: date
    due_on: date
    notified_on: date | None = None
    #: What the investor scans to pay. Euro only, and absent rather than wrong otherwise.
    epc_qr: str | None = None


@router.post("/calls", response_model=CallOut, status_code=status.HTTP_201_CREATED)
async def open_call(
    data: CallIn,
    _: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Ask an investor for part of what they committed.

    ⚠️ A CALL IS NOT MONEY. It creates a demand carrying a reference; the transfer arrives
    later, on a statement, and is attributed then. Counting calls as cash is the second of
    the four confusions, and the one that has funds spending money nobody has sent.

    🔴 NEVER CALLS MORE THAN WHAT REMAINS COMMITTED. A call beyond the engagement is not a
    call, it is an invoice the investor never agreed to — and it would show up on their
    portal as something they owe.
    """
    subscription = await db.get(Subscription, data.subscription_id)
    if subscription is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Souscription introuvable.")
    if data.amount <= 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Le montant doit être positif."
        )
    if data.due_on < data.called_on:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "L'échéance d'un appel ne peut pas précéder sa date d'émission.",
        )

    already = sum(
        (
            row
            for row in (
                await db.execute(
                    select(CapitalCall.amount).where(
                        CapitalCall.subscription_id == subscription.id
                    )
                )
            )
            .scalars()
            .all()
        ),
        Decimal("0"),
    )
    if already + data.amount > subscription.amount:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"L'engagement est de {subscription.amount} {subscription.currency} et "
            f"{already} ont déjà été appelés : il ne reste que "
            f"{subscription.amount - already} à appeler.",
        )

    call = await treasury_service.open_call(
        db,
        subscription=subscription,
        amount=data.amount,
        due_on=data.due_on,
        called_on=data.called_on,
    )
    return _call_out(call)


def _call_out(call: CapitalCall) -> CallOut:
    """One shape for a call, so the portal and the fund never see two different ones."""
    from app.config import get_settings
    from app.core import money, references

    settings = get_settings()
    ibans = settings.fund_ibans
    qr = None
    if call.currency == "EUR" and ibans:
        # ⚠️ EURO ONLY. The EPC standard is euro-denominated; producing one for an XOF call
        # would encode an amount the investor's bank will read as euros.
        qr = references.epc_qr_payload(
            beneficiary=settings.APP_NAME,
            iban=ibans[0],
            amount=str(money.quantize(call.amount, call.currency)),
            currency=call.currency,
            reference=call.reference,
        )
    return CallOut(
        id=call.id,
        subscription_id=call.subscription_id,
        reference=call.reference,
        amount=call.amount,
        currency=call.currency,
        called_on=call.called_on,
        due_on=call.due_on,
        notified_on=call.notified_on,
        epc_qr=qr,
    )


class LateCallOut(BaseModel):
    call_id: uuid.UUID
    reference: str
    investor_id: uuid.UUID
    investor_name: str
    currency: str
    called: Decimal
    received: Decimal
    outstanding: Decimal
    due_on: date
    days_late: int
    late_interest: Decimal
    #: 🔴 CARRIED TO THE SCREEN. True means the notice was never sent: the fund is late,
    #: not the investor, and a reminder would blame them for the fund's own omission.
    never_notified: bool
    last_reminded_on: date | None = None
    #: Whether a reminder is due today, and the reason when it is not.
    reminder_due: bool = False
    reminder_blocked_reason: str | None = None


@router.get("/late-calls", response_model=list[LateCallOut])
async def late_calls(
    as_of: date | None = None,
    _: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Calls past their due date and still short, oldest first.

    ⚠️ `as_of` IS REQUIRED. Whether a call is late depends on a date, and a server reading
    its own clock would answer differently for two readers in different timezones, on the
    same call, on the day it falls due.
    """
    if as_of is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Préciser la date à laquelle les retards sont constatés.",
        )
    out = []
    for late in await call_chasing_service.late_calls(db, as_of=as_of):
        due, why = call_chasing_service.due_for_reminder(late, as_of=as_of)
        out.append(
            LateCallOut(
                call_id=late.call_id,
                reference=late.reference,
                investor_id=late.investor_id,
                investor_name=late.investor_name,
                currency=late.currency,
                called=late.called,
                received=late.received,
                outstanding=late.outstanding,
                due_on=late.due_on,
                days_late=late.days_late,
                late_interest=late.late_interest,
                never_notified=late.never_notified,
                last_reminded_on=late.last_reminded_on,
                reminder_due=due,
                reminder_blocked_reason=why,
            )
        )
    return out


@router.get("/calls", response_model=list[CallOut])
async def list_calls(
    scope: uuid.UUID | None = Depends(investor_scope),
    db: AsyncSession = Depends(get_db),
):
    """The calls an investor has to pay, or all of them for the fund.

    The scope decides. An investor sees their own with the reference to quote, which is the
    single thing that lets the fund attribute their transfer without guessing.
    """
    query = select(CapitalCall).order_by(CapitalCall.due_on)
    if scope is not None:
        query = query.join(
            Subscription, Subscription.id == CapitalCall.subscription_id
        ).where(Subscription.investor_id == scope)
    return [_call_out(c) for c in (await db.execute(query)).scalars().all()]
