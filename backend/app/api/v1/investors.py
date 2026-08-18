"""The register: investors, their file, and the verdict on doing business with them."""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_manager, current_user, investor_scope
from app.core import eligibility, kyc, landlord_kind_values
from app.database import get_db
from app.models.investor import Investor
from app.models.user import User

router = APIRouter(prefix="/investors", tags=["investors"])


class InvestorIn(BaseModel):
    kind: str
    first_name: str | None = None
    last_name: str | None = None
    company_name: str | None = None
    national_id: str | None = None
    born_on: date | None = None
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None
    zip_code: str | None = None
    city: str | None = None
    country_code: str | None = None
    iban: str | None = None
    bic: str | None = None
    payout_currency: str | None = None
    is_pep: bool = False
    source_of_funds: str | None = None


class InvestorOut(BaseModel):
    id: uuid.UUID
    kind: str
    display_name: str
    email: str | None = None
    country_code: str | None = None
    payout_currency: str | None = None
    kyc_status: str
    kyc_risk_level: str
    kyc_review_due_on: date | None = None
    #: ⚠️ THE IBAN IS NOT IN THIS SCHEMA, and that is not an oversight. A register listing is
    #: read constantly, and shipping every investor's account details on every page view is
    #: how a leak becomes exhaustive. It is served by its own endpoint, one investor at a
    #: time, to a manager.
    has_bank_details: bool = False
    #: 🔴 THE TRUTH THE GATES ACTUALLY APPLY, staleness included. It used to read the status
    #: alone: an acceptance long past its review date answered « true » here while every
    #: endpoint that moves money refused it. A register that disagrees with the gate teaches
    #: its reader to trust neither.
    accepts_money: bool = False
    #: Why money is refused, when it is. Carried to the screen so « refused » is actionable:
    #: « never accepted » means open a file, « out of date » means review one that exists.
    refusal_reason: str | None = None

    #: Which protections apply to this investor. NULL means nobody has assessed them, and
    #: `eligibility.is_protected` reads that as PROTECTED.
    category: str | None = None
    loss_bearing_capacity: Decimal | None = None
    #: The amount above which a warning must be acknowledged, or None when it cannot be
    #: established. ⚠️ None is never « no limit ».
    warning_threshold: Decimal | None = None
    threshold_reason: str | None = None

    model_config = {"from_attributes": True}


def _out(investor: Investor, *, today: date | None = None) -> InvestorOut:
    """⚠️ `today` IS AN ARGUMENT because whether an acceptance has aged out depends on a
    date. A serialiser reading the machine's clock would answer differently for two readers
    in different timezones, on the same file, on the day it expires."""
    on = today or date.today()
    refusal = kyc.refusal_reason(
        status=investor.kyc_status,
        accepted_on=investor.kyc_decided_on,
        risk_level=investor.kyc_risk_level,
        today=on,
    )
    threshold = eligibility.warning_threshold(
        category=investor.category,
        loss_bearing_capacity=investor.loss_bearing_capacity,
    )
    return InvestorOut(
        id=investor.id,
        kind=investor.kind,
        display_name=investor.display_name,
        email=investor.email,
        country_code=investor.country_code,
        payout_currency=investor.payout_currency,
        kyc_status=investor.kyc_status,
        kyc_risk_level=investor.kyc_risk_level,
        kyc_review_due_on=investor.kyc_review_due_on,
        has_bank_details=bool(investor.iban_encrypted),
        accepts_money=refusal is None,
        refusal_reason=refusal,
        category=investor.category,
        loss_bearing_capacity=investor.loss_bearing_capacity,
        warning_threshold=threshold.amount,
        threshold_reason=threshold.unavailable_reason,
    )


@router.get("", response_model=list[InvestorOut])
async def list_investors(
    scope: uuid.UUID | None = Depends(investor_scope),
    db: AsyncSession = Depends(get_db),
):
    """Every investor for the fund; only themselves for an investor.

    The scope is applied in the QUERY, not after it: filtering a full result set in the
    caller has already read the register into memory, and one forgotten `if` sends it on.
    """
    query = select(Investor).order_by(Investor.last_name, Investor.company_name)
    if scope is not None:
        query = query.where(Investor.id == scope)
    rows = (await db.execute(query)).scalars().all()
    return [_out(i) for i in rows]


@router.post("", response_model=InvestorOut, status_code=status.HTTP_201_CREATED)
async def create_investor(
    data: InvestorIn,
    _: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    if data.kind not in landlord_kind_values.KINDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Forme juridique inconnue : {data.kind!r}. Attendu « personne » ou « societe ».",
        )
    payload = data.model_dump(exclude={"iban"})
    investor = Investor(**payload)
    # Through the property, so the fingerprint is written in the same breath as the cipher.
    investor.iban = data.iban
    db.add(investor)
    await db.flush()
    return _out(investor)


class VerdictIn(BaseModel):
    status: str
    risk_level: str = kyc.RISK_STANDARD
    reason: str | None = None


@router.post("/{investor_id}/kyc", response_model=InvestorOut)
async def record_verdict(
    investor_id: uuid.UUID,
    data: VerdictIn,
    user: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Decide whether the fund may do business with this investor.

    The decision is validated by `kyc.Verdict` BEFORE anything is written: a refusal with no
    reason is refused there, because it could neither be reconsidered nor explained to the
    investor.
    """
    investor = await db.get(Investor, investor_id)
    if investor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investisseur introuvable.")
    if data.risk_level not in kyc.RISK_LEVELS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Niveau de risque inconnu."
        )
    try:
        verdict = kyc.Verdict(
            status=data.status,
            decided_by=user.email,
            decided_on=date.today(),
            reason=data.reason,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    investor.kyc_status = verdict.status
    investor.kyc_risk_level = data.risk_level
    investor.kyc_decided_by = verdict.decided_by
    investor.kyc_decided_on = verdict.decided_on
    investor.kyc_reason = verdict.reason
    await db.flush()
    return _out(investor)


class BankDetailsOut(BaseModel):
    iban: str | None
    bic: str | None
    virtual_iban: str | None


class EligibilityIn(BaseModel):
    #: One of `eligibility.CATEGORIES`. Required: this endpoint exists to answer the
    #: question, and accepting an empty value would record an assessment nobody made.
    category: str
    #: What they declared they could afford to lose. NULL leaves the threshold unknown, and
    #: an unknown threshold refuses every commitment rather than allowing any.
    loss_bearing_capacity: Decimal | None = None


@router.post("/{investor_id}/eligibility", response_model=InvestorOut)
async def set_eligibility(
    investor_id: uuid.UUID,
    data: EligibilityIn,
    _: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Record which protections apply to this investor, and on what basis.

    🔴 THIS IS NOT A KYC DECISION, and it deliberately lives on its own endpoint. KYC says
    whether the fund may deal with them at all; this says how much they may commit before a
    warning is owed. Folding the two into one screen would let an « accepted » click quietly
    lift a cap, which is precisely the confusion the separate module exists to prevent.

    ⚠️ A CAPACITY SET BACK TO NULL RESTORES THE REFUSAL, and that is correct: forgetting what
    somebody declared must return the fund to « we do not know », never to « no limit ».
    """
    investor = await db.get(Investor, investor_id)
    if investor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investisseur introuvable.")
    if data.category not in eligibility.CATEGORIES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Catégorie inconnue : {data.category!r}. Attendu : "
            f"{', '.join(eligibility.CATEGORIES)}.",
        )
    if data.loss_bearing_capacity is not None and data.loss_bearing_capacity < 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Une capacité de perte négative n'a pas de sens.",
        )
    investor.category = data.category
    investor.loss_bearing_capacity = data.loss_bearing_capacity
    await db.flush()
    return _out(investor)


@router.get("/{investor_id}/bank-details", response_model=BankDetailsOut)
async def bank_details(
    investor_id: uuid.UUID,
    _: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """The account details, decrypted, one investor at a time and for a manager only.

    Its own endpoint precisely so that reading the register does not read everybody's bank
    account: a listing is fetched on every page, and a leak of it should not be a leak of
    the payment file.
    """
    investor = await db.get(Investor, investor_id)
    if investor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investisseur introuvable.")
    return BankDetailsOut(
        iban=investor.iban, bic=investor.bic, virtual_iban=investor.virtual_iban
    )


@router.get("/me", response_model=InvestorOut)
async def me(
    user: User = Depends(current_user),
    scope: uuid.UUID | None = Depends(investor_scope),
    db: AsyncSession = Depends(get_db),
):
    """The investor behind the signed-in account."""
    if scope is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Ce compte gère le fonds : il n'est rattaché à aucun investisseur.",
        )
    investor = await db.get(Investor, scope)
    return _out(investor)
