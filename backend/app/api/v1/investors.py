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
from app.core import fund_time
from app.database import get_db
from app.models.investor import Investor
from app.models.user import User
from app.services import license_service
from app.core.i18n import pick

router = APIRouter(prefix="/investors", tags=["investors"])


class InvestorIn(BaseModel):
    kind: str
    first_name: str | None = None
    last_name: str | None = None
    company_name: str | None = None
    #: Legal person: their company number. Natural person: their identity document and
    #: the type of that document. See the model: one column for two notions made it
    #: impossible to check either, because nobody knew which one they were reading.
    company_number: str | None = None
    identity_document_number: str | None = None
    identity_document_type: str | None = None
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
    # ⚠️ THE FUND'S DAY, not the container's. Whether an acceptance has expired is judged
    # on the day the fund is having, and a serialiser reading UTC would flip a file to
    # « out of date » a few hours early for anybody the fund's own zone is ahead of.
    on = today or fund_time.platform_today()
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


@router.get("/quota")
async def quota(
    user: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Where the register stands against the plan, deciding nothing.

    🔴 IT IS THE GUARD'S OWN ARITHMETIC, not a second copy of it. The screen showing
    « 48 / 50 » and the endpoint refusing the 51st read `license_service.outlook`, so a
    panel can never promise room the guard will deny, nor a price the invoice will not
    charge.

    ⚠️ `verdict == "unknown"` IS NOT AN ERROR AND NOT « fine ». It means the console did
    not answer: the screen says the allowance cannot be read, and registration will refuse
    until it can. Rendering it as unlimited is the failure mode this whole module exists
    to prevent.
    """
    return await license_service.quota_outlook(db, user, adding=1)


@router.post("", response_model=InvestorOut, status_code=status.HTTP_201_CREATED)
async def create_investor(
    data: InvestorIn,
    accept_overage: bool = False,
    user: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Register an investor. THE FIRST OF THE TWO DOORS THE ALLOWANCE IS COUNTED THROUGH.

    ⚠️ THE SHAPE IS CHECKED FIRST, THE ALLOWANCE SECOND. A malformed payload is not an
    attempt to exceed anything, and answering « this will cost you more » to a request that
    was never going to be written would announce a charge for something nobody asked for.
    """
    if data.kind not in landlord_kind_values.KINDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            pick(
                f"Forme juridique inconnue : {data.kind!r}. Attendu « personne » ou "
                f"« societe ».",
                f"Unknown legal form: {data.kind!r}. Expected « personne » or « societe ».",
            ),
        )
    # 🔴 CHECKED BEFORE THE ROW EXISTS, never after. A guard placed after the flush
    # would refuse an investor already written, and the refusal message would be a lie: the
    # register would carry them and the next call would count them.
    await license_service.check_investor_quota(
        db, user, adding=1, accept_overage=accept_overage
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
    accept_overage: bool = False,
    user: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Decide whether the fund may do business with this investor.

    The decision is validated by `kyc.Verdict` BEFORE anything is written: a refusal with no
    reason is refused there, because it could neither be reconsidered nor explained to the
    investor.

    🔴 THE SECOND DOOR THE ALLOWANCE IS COUNTED THROUGH, and the one that does not look
    like one. A refused file is not billed; reversing that refusal makes it billable again,
    so a fund at its ceiling could refuse a hundred people and un-refuse them one by one,
    for free, without a single call to `POST /investors`. Guarding registration alone is
    this repository's oldest defect written once more: a fix placed at one site out of N.

    ⚠️ AND ONLY THAT DIRECTION. Refusing somebody, or re-deciding a file that already
    counted, adds nothing to the quantity and reaches no console — a compliance decision
    must not fail because a subscription service is down.
    """
    investor = await db.get(Investor, investor_id)
    if investor is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            pick("Investisseur introuvable.", "Investor not found."),
        )
    if data.risk_level not in kyc.RISK_LEVELS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            pick("Niveau de risque inconnu.", "Unknown risk level."),
        )
    try:
        verdict = kyc.Verdict(
            status=data.status,
            decided_by=user.email,
            # The FUND took this verdict: its own day, not the container's.
            decided_on=fund_time.platform_today(),
            reason=data.reason,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    # `adding` is 0 for every verdict but one, and 0 short-circuits without a network call.
    became_countable = (
        investor.kyc_status == kyc.REFUSED and verdict.status != kyc.REFUSED
    )
    await license_service.check_investor_quota(
        db, user, adding=1 if became_countable else 0, accept_overage=accept_overage
    )

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
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            pick("Investisseur introuvable.", "Investor not found."),
        )
    if data.category not in eligibility.CATEGORIES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            pick(
                f"Catégorie inconnue : {data.category!r}. Attendu : "
                f"{', '.join(eligibility.CATEGORIES)}.",
                f"Unknown category: {data.category!r}. Expected: "
                f"{', '.join(eligibility.CATEGORIES)}.",
            ),
        )
    if data.loss_bearing_capacity is not None and data.loss_bearing_capacity < 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            pick(
                "Une capacité de perte négative n'a pas de sens.",
                "A negative loss-bearing capacity makes no sense.",
            ),
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
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            pick("Investisseur introuvable.", "Investor not found."),
        )
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
            pick(
                "Ce compte gère le fonds : il n'est rattaché à aucun investisseur.",
                "This account manages the fund: it is attached to no investor.",
            ),
        )
    investor = await db.get(Investor, scope)
    return _out(investor)
