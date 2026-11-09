"""The second factor (TOTP): the second step of the sign-in, and « Sécurité » in « Mon
profil ».

The owner, 2 Nov 2026: offered to every account, recommended to whoever runs the fund (a
discreet banner), never an obligation in the product. The arithmetic is `core/two_factor`
(the same file in every product), the glue `services/two_factor_service`. No screen of
this product administers another account (the console holds them all): a lost phone goes
through a command on the server (`scripts/reset_two_factor.py`), never a route.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.core import audit
from app.core.i18n import pick
from app.core.security import read_two_factor_pending_token, verify_password
from app.core.visitor_window import VisitorWindow
from app.database import SESSION
from app.models.user import User
from app.services import licence_state, two_factor_service

router = APIRouter(prefix="/auth", tags=["auth"])

#: The second step of the sign-in (the code): a code is six digits, and this is what keeps
#: them from being tried by the million. Ten a minute per visitor, as the sibling products
#: allow the password.
SECOND_STEP_PER_MINUTE = 10
_second_step_window = VisitorWindow(SECOND_STEP_PER_MINUTE)
#: The gestures of « Sécurité » that draw a secret or check a password and a code (set-up,
#: activation, new backup codes, removal).
SETTINGS_PER_MINUTE = 5
_settings_window = VisitorWindow(SETTINGS_PER_MINUTE)


def _too_many() -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        pick(
            "Trop de tentatives d'un coup : réessayez dans une minute.",
            "Too many attempts at once: try again in a minute.",
        ),
    )


def _admit(window: VisitorWindow, request: Request) -> None:
    if not window.admit(request):
        raise _too_many()


def _wrong_code() -> str:
    return pick("Code incorrect ou déjà utilisé.", "Wrong code, or already used.")


def _expired() -> str:
    return pick(
        "Étape expirée : reconnectez-vous avec votre mot de passe.",
        "This step has expired: sign in with your password again.",
    )


def _not_on() -> str:
    return pick(
        "La double authentification n'est pas active sur ce compte.",
        "Two-factor authentication is not on for this account.",
    )


class SecondStep(BaseModel):
    """The second step of the sign-in: a code of the app OR one backup code."""

    two_factor_token: str = Field(max_length=2000)
    code: str | None = Field(None, max_length=12)
    backup_code: str | None = Field(None, max_length=20)


class FirstCode(BaseModel):
    code: str = Field(..., max_length=12)


class Confirmation(BaseModel):
    """Removing the factor, or drawing new backup codes: the password AND a code."""

    password: str
    code: str | None = Field(None, max_length=12)
    backup_code: str | None = Field(None, max_length=20)


class Status(BaseModel):
    enabled: bool
    enabled_at: datetime | None = None
    backup_codes_remaining: int = 0
    #: The banner invites this account to switch it on (whoever runs the fund).
    recommended: bool = False
    required: bool = False


class SetUp(BaseModel):
    """Shown ONCE: the secret and its QR code (an SVG data URI drawn by the server)."""

    secret: str
    otpauth_uri: str
    qr_code: str


class BackupCodes(BaseModel):
    """Shown ONCE: only their fingerprints are kept."""

    backup_codes: list[str]


@router.post("/login/two-factor", summary="Sign-in, step 2: the code")
async def login_two_factor(
    data: SecondStep, request: Request, db: AsyncSession = SESSION
):
    """The intermediate token AND a code of the app (or one backup code): the session, as
    `/auth/login` gives it without a second factor.

    A ceiling per visitor. A wrong code is journaled (`two_factor.failed`); a code already
    accepted once, even within its thirty seconds, is refused."""
    from app.api.v1.auth import signed_in

    _admit(_second_step_window, request)
    user_id = read_two_factor_pending_token(data.two_factor_token)
    try:
        key = uuid.UUID(user_id) if user_id else None
    except ValueError:
        key = None
    user = await db.get(User, key) if key else None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _expired())
    # The journal names the account trying (nobody is signed in yet).
    audit.identify(user_id=user.id, user_email=user.email)
    ok = await two_factor_service.verify_second_step(
        db, user, code=data.code, backup_code=data.backup_code
    )
    if not ok:
        # ⚠️ COMMITTED BEFORE THE REFUSAL: the request's session rolls back on an
        # exception, and the line « two_factor.failed » would leave with it.
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _wrong_code())
    # The firm's licence, as at the password step (`licence_state.gate`).
    await licence_state.gate(user)
    return signed_in(user)


async def _confirm(db: AsyncSession, user: User, data: Confirmation) -> None:
    """Removing the factor or drawing new codes asks the password AND a code."""
    if not await run_in_threadpool(
        verify_password, data.password, user.hashed_password
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            pick("Mot de passe incorrect.", "Wrong password."),
        )
    if not await two_factor_service.verify_second_step(
        db, user, code=data.code, backup_code=data.backup_code
    ):
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _wrong_code())


@router.get("/two-factor", response_model=Status, summary="Second factor: status")
async def two_factor_status(
    user: User = Depends(current_user), db: AsyncSession = SESSION
):
    return await two_factor_service.status_of(db, user)


@router.post(
    "/two-factor/setup", response_model=SetUp, summary="Second factor: QR code"
)
async def two_factor_setup(
    request: Request, user: User = Depends(current_user), db: AsyncSession = SESSION
):
    """A fresh secret and its QR code, shown ONCE. Inactive until `/two-factor/activate`."""
    _admit(_settings_window, request)
    shown = await two_factor_service.start_setup(db, user)
    if shown is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            pick(
                "La double authentification est déjà active sur ce compte.",
                "Two-factor authentication is already on for this account.",
            ),
        )
    return shown


@router.post(
    "/two-factor/activate",
    response_model=BackupCodes,
    summary="Second factor: switch on",
)
async def two_factor_activate(
    data: FirstCode,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = SESSION,
):
    """The first valid code switches the factor on: the ten backup codes, shown once."""
    _admit(_settings_window, request)
    codes = await two_factor_service.activate(db, user, data.code)
    if codes is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _wrong_code())
    return BackupCodes(backup_codes=codes)


@router.post(
    "/two-factor/backup-codes",
    response_model=BackupCodes,
    summary="Second factor: new backup codes",
)
async def two_factor_backup_codes(
    data: Confirmation,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = SESSION,
):
    """Ten new backup codes (the old ones stop working), shown once."""
    _admit(_settings_window, request)
    if not await two_factor_service.is_enabled(db, user):
        raise HTTPException(status.HTTP_409_CONFLICT, _not_on())
    await _confirm(db, user, data)
    codes = await two_factor_service.regenerate_backup_codes(db, user)
    return BackupCodes(backup_codes=codes or [])


@router.post(
    "/two-factor/disable", status_code=204, summary="Second factor: switch off"
)
async def two_factor_disable(
    data: Confirmation,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = SESSION,
):
    """Removes the factor: the password AND a code (of the app, or a backup code)."""
    _admit(_settings_window, request)
    if not await two_factor_service.is_enabled(db, user):
        raise HTTPException(status.HTTP_409_CONFLICT, _not_on())
    await _confirm(db, user, data)
    await two_factor_service.disable(db, user)


__all__ = ["router"]
