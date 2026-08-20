"""The `/internal` contract (Alice → Le Comptoir Invest).

🔴 MOUNTED AT THE ROOT, OUTSIDE `/api`, AND THAT IS THE SECURITY. The edge proxy forwards
only `/api/` and `/health` to this backend; everything else goes to the front end, whose
SPA fallback answers `index.html`. So `https://invest.lecomptoir.services/internal/managers`
reaches a static page and never this router. It is reachable only from the shared Docker
network, which is where Alice lives. Verified on 18 August 2026: the public URL answers
`text/html`, not JSON.

Moving this router under `/api` would publish the fund's account administration on the
internet behind a single shared header. The prefix is not cosmetic.

⚠️ THE SHARED KEY IS COMPARED IN CONSTANT TIME. A `==` on a secret leaks its length and
then its content, one byte at a time, to anybody who can measure a response.
"""

from __future__ import annotations

import hmac
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import create_access_token, hash_password
from app.database import get_db
from app.models.investor import Investor
from app.models.subscription import Subscription
from app.models.user import FUND_WIDE_ROLES, MANAGER, User
from app.core.i18n import pick

router = APIRouter(prefix="/internal", tags=["internal"])

#: Accounts Alice may SEE and ACT ON. The administrator is one of them.
#:
#: 🔴 THE PROTECTION GUARDS THE OUTCOME, NEVER THE ROLE. Excluding the admin from this list
#: would look prudent and be wrong in both directions: it forbids renaming an admin or
#: resetting its password — which lock nobody out — while still allowing the last *manager*
#: to be deleted, which does. `_refuse_if_last_administrator` refuses exactly the operation
#: that would leave the fund with nobody able to run it, and nothing else.
#:
#: Same shape as the sister product's `_MANAGEABLE_ROLES`, and the same lesson.
_MANAGED_ROLES: tuple[str, ...] = FUND_WIDE_ROLES


def require_internal_key(x_internal_key: str | None = Header(default=None)) -> None:
    cfg = get_settings()
    if (
        not x_internal_key
        or not cfg.ALICE_INTERNAL_KEY
        or not hmac.compare_digest(x_internal_key, cfg.ALICE_INTERNAL_KEY)
    ):
        raise HTTPException(
            status_code=401,
            detail=pick("Clé interne invalide.", "Invalid internal key."),
        )


# ── Contract schemas ─────────────────────────────────────────────────────────────
class ManagerOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    #: The contract's JSON name stays `full_name` — Alice and the sister products speak it —
    #: while the column is `account_name`. Renaming the wire format to match a local column
    #: would break every product at once, for a reader's convenience.
    full_name: str | None = Field(default=None, validation_alias="account_name")
    role: str
    is_active: bool
    phone: str | None = None
    address: str | None = None
    zip_code: str | None = None
    city: str | None = None
    country: str | None = None
    created_at: datetime | None = None

    #: 🔴 THE BILLING QUANTITY, UNDER THE NAME THE PLATFORM ALREADY SPEAKS. Alice reads
    #: `managed_count` from every product and multiplies whatever exceeds the plan's
    #: limit by the overage price. The word says « property » because the first product
    #: managed properties; renaming the wire format would break four products at once for
    #: one reader's comfort. What it CARRIES is « the units this subscription is billed on ».
    #:
    #: 🔴 AND FOR A FUND, THOSE UNITS ARE INVESTORS, NOT VEHICLES. Everything this product
    #: does scales with them: a KYC file, a capital call, a notice, a reminder, an annual
    #: statement, a share of every distribution. A club deal of six people on fifty million
    #: is less work than a crowdfunding raise of four hundred on two — and billing by
    #: vehicle would charge the two the same.
    #:
    #: ⚠️ IT IS THE SAME NUMBER ON EVERY MANAGER ACCOUNT of one installation, because this
    #: product has ONE register that every manager sees. Two manager accounts on the same
    #: fund therefore report the same count, and Alice bills a licence per account.
    #: 🔴 THE GENERIC NAME, the one this platform is moving to. It pairs with Alice's
    #: registry, which already carries each product's WORD (`managed_one` /
    #: `managed_many`): this is the count of it.
    managed_count: int = 0

    model_config = {"from_attributes": True, "populate_by_name": True}


class ManagerIn(BaseModel):
    """What Alice sends when it provisions an account.

    🔴 THE FIELDS THIS PRODUCT DOES NOT KEEP ARE NAMED HERE, ON PURPOSE. Pydantic drops an
    unknown key without a word; the sister product shipped a schema that swallowed
    `real_charges` and produced NaN in production. So the landlord identity Alice pushes
    down — `owner_kind`, `owner_account_name`, `owner_company`, `owner_national_id` — is
    declared and explicitly NOT stored: a fund has no landlord, and the decision is
    readable here instead of being a field that quietly vanished.
    """

    email: EmailStr
    full_name: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, min_length=8)
    role: str = MANAGER
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = None
    zip_code: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=80)

    # ⚠️ Reçus et NON conservés : identité de bailleur, sans objet pour un fonds.
    owner_kind: str | None = None
    owner_account_name: str | None = None
    owner_full_name: str | None = None
    owner_company: str | None = None
    owner_national_id: str | None = None


#: The fields Alice sends that this product does NOT keep. Named here so a guard can hold
#: the decision still, and so that adding a column one day is a single line.
IGNORED_BY_DESIGN: tuple[str, ...] = (
    "owner_kind",
    "owner_account_name",
    "owner_full_name",
    "owner_company",
    "owner_national_id",
)

_STORED = ("phone", "address", "zip_code", "city", "country")


class Stats(BaseModel):
    managers: int
    active_managers: int
    users: int
    #: Fund-side figures, so Alice's dashboard shows something true about THIS product
    #: rather than a customer count that says nothing about what it does.
    investors: int
    subscriptions: int


class BlockResult(BaseModel):
    #: What was actually deactivated, so `unblock` restores exactly that and nothing more.
    #: Reactivating « every account of this manager » would revive accounts somebody had
    #: disabled for their own reasons, and nobody would connect the two events.
    user_ids: list[uuid.UUID]


class UnblockIn(BaseModel):
    user_ids: list[uuid.UUID]


class ResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=8)


# ── Helpers ──────────────────────────────────────────────────────────────────────
async def _managed(db: AsyncSession, manager_id: uuid.UUID) -> User:
    user = await db.get(User, manager_id)
    if user is None or user.role not in _MANAGED_ROLES:
        raise HTTPException(
            status_code=404,
            detail=pick(
                "Compte gestionnaire introuvable.", "Manager account not found."
            ),
        )
    return user


async def _refuse_if_last_administrator(db: AsyncSession, target: User) -> None:
    """Refuse the operation that would leave the fund with nobody able to run it.

    🔴 THE OUTCOME, NOT THE ROLE. Whether the account is « the admin » is beside the point:
    what must never happen is a fund whose owner is locked out of it from the outside.
    Renaming an admin, or resetting its password, does not do that and goes through.
    """
    others = await db.scalar(
        select(func.count())
        .select_from(User)
        .where(
            User.role.in_(_MANAGED_ROLES),
            User.is_active.is_(True),
            User.id != target.id,
        )
    )
    if not others:
        raise HTTPException(
            status_code=409,
            detail=(
                pick(
                    "C'est le dernier compte actif capable d'administrer ce fonds : le supprimer ou le bloquer fermerait la porte de l'extérieur, sans recours.",
                    "This is the last active account able to administer this fund: deleting or blocking it would lock the door from the outside, with no way back.",
                )
            ),
        )


# ── Managers ─────────────────────────────────────────────────────────────────────
@router.get("/managers", response_model=list[ManagerOut])
async def list_managers(
    _: None = Depends(require_internal_key), db: AsyncSession = Depends(get_db)
):
    rows = (
        (
            await db.execute(
                select(User)
                .where(User.role.in_(_MANAGED_ROLES))
                .order_by(User.created_at)
            )
        )
        .scalars()
        .all()
    )
    counted = await _investors_under_management(db)
    return [
        ManagerOut.model_validate(r).model_copy(update={"managed_count": counted})
        for r in rows
    ]


async def _investors_under_management(db: AsyncSession) -> int:
    """How many investors this installation actually carries. The billing quantity.

    🔴 A REFUSED FILE IS NOT AN INVESTOR UNDER MANAGEMENT. They were assessed and turned
    away: they hold nothing, they receive nothing, and no capital call will ever go to
    them. Counting them would bill a fund for the people it declined — and the more
    carefully it screens, the more it would pay.

    ⚠️ EVERYTHING ELSE COUNTS, including a file still pending or under review. The work
    is done the moment the file exists, which is exactly what is being billed; waiting
    for an acceptance would make the quantity lag the effort by weeks.
    """
    from sqlalchemy import func

    from app.core import kyc
    from app.models.investor import Investor

    return int(
        (
            await db.execute(
                select(func.count(Investor.id)).where(
                    Investor.kyc_status != kyc.REFUSED
                )
            )
        ).scalar_one()
    )


@router.get("/managers/{manager_id}", response_model=ManagerOut)
async def get_manager(
    manager_id: uuid.UUID,
    _: None = Depends(require_internal_key),
    db: AsyncSession = Depends(get_db),
):
    return ManagerOut.model_validate(await _managed(db, manager_id))


@router.get("/billing-identity/{user_id}")
async def billing_identity(
    user_id: uuid.UUID,
    _: None = Depends(require_internal_key),
    db: AsyncSession = Depends(get_db),
):
    """Name and e-mail of an account, WHATEVER its role, for an accounting document.

    ⚠️ NOT `get_manager`. That one answers only for a manager, which is right for current
    billing and wrong for history: an account that stops being a manager stops being
    findable, and its past invoices retroactively lose their recipient.
    """
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=404, detail=pick("Compte introuvable.", "Account not found.")
        )
    return {"id": user.id, "full_name": user.account_name, "email": user.email}


@router.post("/managers", response_model=ManagerOut, status_code=201)
async def create_manager(
    data: ManagerIn,
    _: None = Depends(require_internal_key),
    db: AsyncSession = Depends(get_db),
):
    """Alice provisions the account. This is the ONLY way a manager is born here.

    ⚠️ A password is required. Alice generates a temporary one and mails it; minting an
    account with no credential would leave a role nobody can use and nobody can see is
    unusable.
    """
    if data.role not in _MANAGED_ROLES:
        raise HTTPException(
            status_code=422,
            detail=pick(
                f"Rôle « {data.role} » inconnu de ce produit.",
                f"Role « {data.role} » is unknown to this product.",
            ),
        )
    if not data.password:
        raise HTTPException(
            status_code=422,
            detail=pick("Un mot de passe est requis.", "A password is required."),
        )

    email = data.email.lower().strip()
    already = (
        await db.execute(select(User.id).where(User.email == email))
    ).scalar_one_or_none()
    if already:
        raise HTTPException(
            status_code=409,
            detail=pick(
                "Cette adresse a déjà un compte.",
                "This address already has an account.",
            ),
        )

    user = User(
        email=email,
        hashed_password=hash_password(data.password),
        account_name=(data.full_name or "").strip() or None,
        role=data.role,
        # The credential was handed over by Alice, so it is not the holder's yet.
        must_change_password=True,
        **{f: getattr(data, f) for f in _STORED},
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return ManagerOut.model_validate(user)


@router.patch("/managers/{manager_id}", response_model=ManagerOut)
async def update_manager(
    manager_id: uuid.UUID,
    data: ManagerIn,
    _: None = Depends(require_internal_key),
    db: AsyncSession = Depends(get_db),
):
    """Alice pushes an identity change down.

    ⚠️ Only the fields actually SENT are written. Alice calls this with
    `exclude_unset=True`, so a payload carrying one field must not blank the others —
    which is exactly what reading every attribute of the model would do.
    """
    user = await _managed(db, manager_id)
    sent = data.model_dump(exclude_unset=True)

    if "email" in sent and sent["email"]:
        email = str(sent["email"]).lower().strip()
        clash = (
            await db.execute(
                select(User.id).where(User.email == email, User.id != user.id)
            )
        ).scalar_one_or_none()
        if clash:
            raise HTTPException(
                status_code=409,
                detail=pick(
                    "Cette adresse a déjà un compte.",
                    "This address already has an account.",
                ),
            )
        user.email = email
    if "full_name" in sent:
        user.account_name = (sent["full_name"] or "").strip() or None
    if "role" in sent and sent["role"]:
        if sent["role"] not in _MANAGED_ROLES:
            raise HTTPException(
                status_code=422,
                detail=pick(
                    "Rôle inconnu de ce produit.", "Role unknown to this product."
                ),
            )
        # Demoting the last administrator is the same lock-out as deleting them.
        if user.role in _MANAGED_ROLES and sent["role"] != user.role:
            await _refuse_if_last_administrator(db, user)
        user.role = sent["role"]
    for field in _STORED:
        if field in sent:
            setattr(user, field, sent[field])

    await db.commit()
    await db.refresh(user)
    return ManagerOut.model_validate(user)


@router.delete("/managers/{manager_id}", status_code=204)
async def delete_manager(
    manager_id: uuid.UUID,
    _: None = Depends(require_internal_key),
    db: AsyncSession = Depends(get_db),
):
    """Remove the account. The fund's history does not move.

    ⚠️ `decided_by` and `attributed_by` hold an E-MAIL, not a foreign key, and that is why
    this deletion is safe: who authorised a 500 000 € deployment must remain readable long
    after the person has left. A foreign key would have forced a choice between keeping a
    ghost account and losing the answer.
    """
    user = await _managed(db, manager_id)
    await _refuse_if_last_administrator(db, user)
    await db.delete(user)
    await db.commit()


@router.post("/managers/{manager_id}/block", response_model=BlockResult)
async def block(
    manager_id: uuid.UUID,
    _: None = Depends(require_internal_key),
    db: AsyncSession = Depends(get_db),
):
    """Suspend the account — non-payment, usually.

    ⚠️ BLOCKS THE MANAGER, NEVER THE INVESTORS. An unpaid subscription is a dispute between
    the fund and Alice; the investors are third parties who committed money and are owed
    sight of it. Cutting their access would turn a billing incident into something a
    regulator reads very differently.
    """
    user = await _managed(db, manager_id)
    await _refuse_if_last_administrator(db, user)
    blocked: list[uuid.UUID] = []
    if user.is_active:
        user.is_active = False
        blocked.append(user.id)
        await db.commit()
    return BlockResult(user_ids=blocked)


@router.post("/managers/{manager_id}/unblock", status_code=204)
async def unblock(
    manager_id: uuid.UUID,
    data: UnblockIn,
    _: None = Depends(require_internal_key),
    db: AsyncSession = Depends(get_db),
):
    """Reactivate EXACTLY what the matching block deactivated.

    🔴 THE LIST COMES FROM THE CALLER, and that is the point. Reactivating « every account
    of this manager » would revive accounts somebody had disabled for their own reasons —
    a departure, a suspicion — and nobody would ever connect the two events.
    """
    await _managed(db, manager_id)
    if not data.user_ids:
        return
    rows = (
        (await db.execute(select(User).where(User.id.in_(data.user_ids))))
        .scalars()
        .all()
    )
    for row in rows:
        row.is_active = True
    await db.commit()


@router.post("/managers/{manager_id}/reset-password", status_code=204)
async def reset_password(
    manager_id: uuid.UUID,
    data: ResetPasswordIn,
    _: None = Depends(require_internal_key),
    db: AsyncSession = Depends(get_db),
):
    """Alice hands over a new credential.

    `must_change_password` is set: a password somebody else has seen is not the holder's.
    """
    user = await _managed(db, manager_id)
    user.hashed_password = hash_password(data.new_password)
    user.must_change_password = True
    await db.commit()


@router.post("/managers/{manager_id}/login-link")
async def login_link(
    manager_id: uuid.UUID,
    _: None = Depends(require_internal_key),
    db: AsyncSession = Depends(get_db),
):
    """A one-shot sign-in URL, so support can see what the customer sees.

    ⚠️ A BLOCKED ACCOUNT GETS NO LINK. Otherwise the link becomes the way around the block,
    and the suspension means nothing.
    """
    user = await _managed(db, manager_id)
    if not user.is_active:
        raise HTTPException(
            status_code=409,
            detail=pick(
                "Ce compte est bloqué : un lien de connexion contournerait le blocage.",
                "This account is blocked: a sign-in link would work around the block.",
            ),
        )
    token = create_access_token(str(user.id), user.role)
    return {"token": token, "url": f"/login?token={token}"}


@router.get("/stats", response_model=Stats)
async def stats(
    _: None = Depends(require_internal_key), db: AsyncSession = Depends(get_db)
):
    """What Alice's dashboard shows for this product.

    ⚠️ The customer counts AND the fund-side figures. A console that shows « 1 gestionnaire »
    and nothing else says nothing about whether the product is being used.
    """
    managers = (
        await db.scalar(
            select(func.count()).select_from(User).where(User.role.in_(_MANAGED_ROLES))
        )
        or 0
    )
    active = (
        await db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role.in_(_MANAGED_ROLES), User.is_active.is_(True))
        )
        or 0
    )
    return Stats(
        managers=managers,
        active_managers=active,
        users=await db.scalar(select(func.count()).select_from(User)) or 0,
        investors=await db.scalar(select(func.count()).select_from(Investor)) or 0,
        subscriptions=await db.scalar(select(func.count()).select_from(Subscription))
        or 0,
    )


@router.get("/health")
async def internal_health():
    """Lets Alice tell « the product is up » from « the key is wrong »."""
    return {"status": "ok", "at": datetime.now(UTC).isoformat()}
