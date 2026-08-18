"""Engagements: what an investor asked for, what the fund agreed, and what converted."""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_manager, current_user, investor_scope
from app.core import eligibility, instruments, kyc
from app.database import get_db
from app.models.investor import Investor
from app.models.subscription import (
    REQUEST_ACCEPTED,
    REQUEST_PENDING,
    REQUEST_REFUSED,
    REQUEST_WITHDRAWN,
    Subscription,
    SubscriptionConversion,
    SubscriptionRequest,
)
from app.models.user import User
from app.services import portfolio_service

router = APIRouter(tags=["subscriptions"])


class RequestIn(BaseModel):
    instrument: str
    amount: Decimal
    currency: str
    information_document_version: str | None = None


class RequestOut(BaseModel):
    id: uuid.UUID
    instrument: str
    amount: Decimal
    currency: str
    requested_on: date
    status: str
    decision_reason: str | None = None
    #: ⚠️ THE COMMITMENT BORN OF THIS REQUEST, and it was missing. A request and a
    #: subscription are two distinct objects on purpose; but without this link, a screen
    #: acting on the commitment only has the request's id to hand, and sends that — to get
    #: back a 404 whose cause is anything but obvious. NULL while it is pending, and NULL
    #: for good if it is refused: which is exactly what makes the two rows useful
    #: separately.
    subscription_id: uuid.UUID | None = None
    #: The last day this investor may still step back. NULL when none protects them.
    reflection_ends_on: date | None = None
    #: When they acknowledged the risk warning, for a commitment above their threshold.
    risk_acknowledged_on: date | None = None


@router.post(
    "/subscription-requests",
    response_model=RequestOut,
    status_code=status.HTTP_201_CREATED,
)
async def request_subscription(
    data: RequestIn,
    user: User = Depends(current_user),
    scope: uuid.UUID | None = Depends(investor_scope),
    db: AsyncSession = Depends(get_db),
):
    """An investor expresses an intent from the portal. It binds nobody.

    🔴 THIS WRITES A REQUEST, NEVER A SUBSCRIPTION. If the portal form created an
    engagement, anybody holding a login would create a binding commitment of the fund — and
    an investor nobody has vetted could do it before anyone looked at who they are.

    ⚠️ AN UNVETTED INVESTOR MAY STILL ASK. Refusing here would be refusing them the one act
    that gets a file started, and the verdict already stops the thing that matters: money.
    The fund sees the request beside the file and decides both together.
    """
    if scope is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Ce compte gère le fonds : il ne souscrit pas."
        )
    if data.instrument not in instruments.INSTRUMENTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Instrument inconnu : {data.instrument!r}.",
        )
    if data.amount <= 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Le montant doit être positif."
        )

    investor = await db.get(Investor, scope)
    requested_on = date.today()
    request = SubscriptionRequest(
        investor_id=scope,
        instrument=data.instrument,
        amount=data.amount,
        currency=data.currency.upper(),
        requested_on=requested_on,
        # 🔴 STORED, NOT RECOMPUTED LATER. The delay belongs to the investor and to the
        # rule in force the day they asked; a request read next year must keep the period
        # it was made under, not the one the regulation moved to since.
        reflection_ends_on=eligibility.reflection_period_ends(
            requested_on=requested_on,
            category=investor.category if investor else None,
        ),
        information_document_version=data.information_document_version,
    )
    db.add(request)
    await db.flush()
    return RequestOut(**{k: getattr(request, k) for k in RequestOut.model_fields})


@router.post(
    "/subscription-requests/{request_id}/acknowledge-risk", response_model=RequestOut
)
async def acknowledge_risk(
    request_id: uuid.UUID,
    scope: uuid.UUID | None = Depends(investor_scope),
    db: AsyncSession = Depends(get_db),
):
    """The investor states they have read the risk warning for a commitment above their cap.

    🔴 ONLY THE INVESTOR MAY DO THIS, AND THAT IS THE WHOLE PROTECTION. A manager who could
    tick it on their behalf would turn the safeguard into a formality: the acknowledgement
    exists precisely to record that the person bearing the loss saw the warning. A fund
    holding both ends of that is a fund with no warning at all.

    ⚠️ IT IS NOT UNDONE BY REPEATING IT. The date recorded is the FIRST one: an
    acknowledgement re-clicked after a dispute must not quietly move to a later day.
    """
    if scope is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Seul l'investisseur peut reconnaître l'avertissement qui le concerne.",
        )
    request = await db.get(SubscriptionRequest, request_id)
    if request is None or request.investor_id != scope:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demande introuvable.")
    if request.status != REQUEST_PENDING:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Cette demande est déjà « {request.status} »."
        )
    if request.risk_acknowledged_on is None:
        request.risk_acknowledged_on = date.today()
        await db.flush()
    return RequestOut(**{k: getattr(request, k) for k in RequestOut.model_fields})


@router.post("/subscription-requests/{request_id}/withdraw", response_model=RequestOut)
async def withdraw(
    request_id: uuid.UUID,
    scope: uuid.UUID | None = Depends(investor_scope),
    db: AsyncSession = Depends(get_db),
):
    """The investor steps back, which is what the reflection period is FOR.

    ⚠️ A PERIOD NOBODY CAN ACT ON IS A DELAY, NOT A RIGHT. Enforcing the wait without
    offering the way out would leave an investor who changed their mind waiting four days to
    be bound by something they no longer want.
    """
    if scope is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Seul l'investisseur peut retirer sa demande."
        )
    request = await db.get(SubscriptionRequest, request_id)
    if request is None or request.investor_id != scope:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demande introuvable.")
    if request.status != REQUEST_PENDING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cette demande est « {request.status} » : elle ne peut plus être retirée.",
        )
    request.status = REQUEST_WITHDRAWN
    await db.flush()
    return RequestOut(**{k: getattr(request, k) for k in RequestOut.model_fields})


@router.get("/subscription-requests", response_model=list[RequestOut])
async def list_requests(
    scope: uuid.UUID | None = Depends(investor_scope),
    db: AsyncSession = Depends(get_db),
):
    query = select(SubscriptionRequest).order_by(
        SubscriptionRequest.requested_on.desc()
    )
    if scope is not None:
        query = query.where(SubscriptionRequest.investor_id == scope)
    rows = (await db.execute(query)).scalars().all()
    return [
        RequestOut(**{k: getattr(r, k) for k in RequestOut.model_fields}) for r in rows
    ]


class DecisionIn(BaseModel):
    accept: bool
    reason: str | None = None
    signed_on: date | None = None
    ends_on: date | None = None
    terms: dict | None = None


@router.post("/subscription-requests/{request_id}/decide", response_model=RequestOut)
async def decide(
    request_id: uuid.UUID,
    data: DecisionIn,
    user: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """The fund accepts or refuses. Acceptance, and only acceptance, creates the engagement.

    🔴 THE VERDICT IS CHECKED BEFORE AN ENGAGEMENT IS CREATED, not only before money moves.
    Signing a commitment with somebody the fund has not vetted is the act identification
    rules exist to prevent; discovering it at the first transfer is a month too late.
    """
    request = await db.get(SubscriptionRequest, request_id)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demande introuvable.")
    if request.status != REQUEST_PENDING:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Cette demande est déjà « {request.status} »."
        )

    if not data.accept:
        if not (data.reason or "").strip():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Un refus sans motif ne peut être ni reconsidéré ni expliqué à l'investisseur.",
            )
        request.status = REQUEST_REFUSED
        request.decision_reason = data.reason
        request.decided_by = user.email
        request.decided_on = date.today()
        await db.flush()
        return RequestOut(**{k: getattr(request, k) for k in RequestOut.model_fields})

    investor = await db.get(Investor, request.investor_id)
    signed_on = data.signed_on or date.today()

    refusal = kyc.refusal_reason(
        status=investor.kyc_status,
        accepted_on=investor.kyc_decided_on,
        risk_level=investor.kyc_risk_level,
        today=signed_on,
    )
    if refusal:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{investor.display_name} : {refusal}"
        )

    # 🔴 THE REFLECTION PERIOD IS ENFORCED, NOT DISPLAYED. A screen that showed the date and
    # signed anyway would record a binding engagement the investor may still revoke — and
    # the fund would have called capital on it.
    allowed, why = eligibility.may_bind(
        requested_on=request.requested_on,
        category=investor.category,
        on=signed_on,
    )
    if not allowed:
        raise HTTPException(status.HTTP_409_CONFLICT, why)

    # ⚠️ ABOVE THEIR THRESHOLD, THE WARNING MUST HAVE BEEN ACKNOWLEDGED — and an
    # unmeasurable threshold is refused rather than waved through. An investor whose
    # loss-bearing capacity was never declared is precisely the one nobody assessed.
    needs_consent, unmeasurable = eligibility.needs_explicit_consent(
        category=investor.category,
        amount=request.amount,
        loss_bearing_capacity=investor.loss_bearing_capacity,
    )
    if unmeasurable:
        raise HTTPException(status.HTTP_409_CONFLICT, unmeasurable)
    if needs_consent and request.risk_acknowledged_on is None:
        threshold = eligibility.warning_threshold(
            category=investor.category,
            loss_bearing_capacity=investor.loss_bearing_capacity,
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Ce montant dépasse le seuil de {threshold.amount} {request.currency} "
            f"applicable à cet investisseur : l'avertissement sur les risques doit avoir "
            f"été reconnu avant tout engagement.",
        )

    subscription = Subscription(
        investor_id=request.investor_id,
        instrument=request.instrument,
        amount=request.amount,
        currency=request.currency,
        signed_on=signed_on,
        ends_on=data.ends_on,
        terms=data.terms,
    )
    db.add(subscription)
    await db.flush()

    request.status = REQUEST_ACCEPTED
    request.subscription_id = subscription.id
    request.decided_by = user.email
    request.decided_on = date.today()
    await db.flush()
    return RequestOut(**{k: getattr(request, k) for k in RequestOut.model_fields})


class ConversionIn(BaseModel):
    converted_on: date
    principal_converted: Decimal
    interest_converted: Decimal = Decimal("0")
    interest_paid_in_cash: Decimal = Decimal("0")
    conversion_terms: dict | None = None


@router.post(
    "/subscriptions/{subscription_id}/convert", status_code=status.HTTP_201_CREATED
)
async def convert(
    subscription_id: uuid.UUID,
    data: ConversionIn,
    user: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """A loan becomes a subscription. An EVENT: one holding closes, another opens.

    🔴 THE EXISTING ROW IS NOT MUTATED. Changing its instrument would rewrite history —
    every statement sent said the investor held a loan, every past distribution ranked it as
    debt — and the row would claim it had always been equity.
    """
    loan = await db.get(Subscription, subscription_id)
    if loan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Souscription introuvable.")
    if not loan.is_open:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette ligne est déjà convertie.")
    if not instruments.may_convert(
        loan.instrument, None if loan.terms is None else _Terms(loan.terms)
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Seul un prêt convertible devient une souscription, et jamais l'inverse : "
            "transformer du capital en dette placerait cet investisseur devant les autres "
            "en liquidation, après coup.",
        )

    total = data.principal_converted + data.interest_converted
    equity = Subscription(
        investor_id=loan.investor_id,
        instrument=instruments.EQUITY,
        amount=total,
        currency=loan.currency,
        signed_on=data.converted_on,
        terms=None,
    )
    db.add(equity)
    await db.flush()

    conversion = SubscriptionConversion(
        from_subscription_id=loan.id,
        to_subscription_id=equity.id,
        converted_on=data.converted_on,
        principal_converted=data.principal_converted,
        interest_converted=data.interest_converted,
        interest_paid_in_cash=data.interest_paid_in_cash,
        currency=loan.currency,
        conversion_terms=data.conversion_terms,
        decided_by=user.email,
    )
    db.add(conversion)
    # The loan CLOSES. Its contributions stay attached to it, because that is where the
    # money was paid: what converts is the instrument governing the future.
    loan.converted_on = data.converted_on
    await db.flush()
    return {"conversion_id": str(conversion.id), "new_subscription_id": str(equity.id)}


class _Terms:
    """Read `convertible` out of the stored JSON without pretending to be the dataclass."""

    def __init__(self, raw: dict) -> None:
        self.convertible = bool(raw.get("convertible", True))


@router.get("/portfolio")
async def portfolio(
    scope: uuid.UUID | None = Depends(investor_scope),
    investor_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    """An investor's position, computed from what happened. Nothing is stored.

    A manager may ask for any investor; an investor may only ever be themselves, and the
    parameter is ignored for them rather than honoured — a scope that a query parameter can
    widen is not a scope.
    """
    target = scope if scope is not None else investor_id
    if target is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Préciser l'investisseur dont on veut la position.",
        )
    positions = await portfolio_service.positions_of(db, target)
    return {
        "positions": [
            {
                "subscription_id": str(p.subscription_id),
                "instrument": p.instrument,
                "currency": p.currency,
                "committed": str(p.committed),
                "called": str(p.called),
                "contributed": str(p.contributed),
                "outstanding_commitment": str(p.outstanding_commitment),
                "capital_at_work": str(p.capital_at_work),
                "income_received": str(p.income_received),
                "net_received": str(p.net_received),
            }
            for p in positions
        ],
        "totals_by_currency": {
            currency: {k: str(v) for k, v in block.items()}
            for currency, block in portfolio_service.summarise(positions).items()
        },
    }
