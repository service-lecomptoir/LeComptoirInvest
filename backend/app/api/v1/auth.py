"""Signing in, choosing a password through a link, and replacing the credential somebody
else handed you."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.core import account_kind
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.database import SESSION
from app.models.user import User
from app.core.i18n import pick
from app.core.visitor_window import VisitorWindow
from app.services import password_link_service

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    must_change_password: bool


@router.post("/login", response_model=LoginOut)
async def login(data: LoginIn, db: AsyncSession = SESSION):
    user = (
        await db.execute(select(User).where(User.email == data.email.lower()))
    ).scalar_one_or_none()
    # ⚠️ ONE MESSAGE FOR BOTH FAILURES. Saying « unknown e-mail » tells whoever is asking
    # which addresses hold accounts, and on a fund that list is worth something on its own.
    if user is None or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            pick("Identifiants incorrects.", "Wrong credentials."),
        )
    if not user.is_active:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            pick("Ce compte est désactivé.", "This account is disabled."),
        )
    # Kept so a password link knows whether it welcomes somebody (a week) or serves a
    # forgotten password (two hours).
    user.last_login_at = datetime.now(UTC)
    return LoginOut(
        access_token=create_access_token(str(user.id), user.role),
        role=user.role,
        must_change_password=user.must_change_password,
    )


class ForgotIn(BaseModel):
    email: EmailStr


class ForgotOut(BaseModel):
    message: str


#: At most this many requests a minute from one visitor: each one may send an e-mail.
FORGOT_PER_MINUTE = 5
_forgot_window = VisitorWindow(FORGOT_PER_MINUTE)


@router.post("/forgot-password", response_model=ForgotOut)
async def forgot_password(data: ForgotIn, request: Request, db: AsyncSession = SESSION):
    """E-mail a LINK to the page where a new password is chosen.

    ⚠️ THE SAME ANSWER WHETHER THE ADDRESS HOLDS AN ACCOUNT OR NOT, as the sign-in's single
    refusal: saying « unknown address » would tell whoever asks which addresses hold
    accounts on a fund. A blocked account gets no link either: it would open a door the
    block closed.
    """
    if not _forgot_window.admit(request):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            pick(
                "Trop de demandes d'un coup : réessayez dans une minute.",
                "Too many requests at once: try again in a minute.",
            ),
        )
    user = (
        await db.execute(select(User).where(User.email == str(data.email).lower()))
    ).scalar_one_or_none()
    if user is not None and user.is_active:
        await password_link_service.send_link(db, user, "reset")
    return ForgotOut(
        message=pick(
            "Si un compte existe pour cette adresse, un e-mail vient de lui être envoyé "
            "avec un lien pour choisir un nouveau mot de passe. Il est valable deux heures.",
            "If an account exists for this address, an e-mail has just been sent to it "
            "with a link to choose a new password. It is valid for two hours.",
        )
    )


def _link_refusal(reason: str) -> HTTPException:
    """What the page says of a link it cannot honour, and what to do instead."""
    if reason == "expired":
        return HTTPException(
            status.HTTP_410_GONE,
            pick(
                "Ce lien a expiré. Demandez-en un nouveau depuis la page de connexion, "
                "avec « Mot de passe oublié ».",
                "This link has expired. Ask for a new one from the sign-in page, with "
                "« Forgot password ».",
            ),
        )
    if reason == "used":
        return HTTPException(
            status.HTTP_410_GONE,
            pick(
                "Ce lien a déjà servi : le mot de passe est choisi. Connectez-vous, ou "
                "demandez un nouveau lien si vous l'avez oublié.",
                "This link has already been used: the password is set. Sign in, or ask for "
                "a new link if you forgot it.",
            ),
        )
    return HTTPException(
        status.HTTP_404_NOT_FOUND,
        pick(
            "Ce lien n'est pas valide. Vérifiez qu'il a été copié en entier, ou demandez-en "
            "un nouveau depuis la page de connexion.",
            "This link is not valid. Check that it was copied whole, or ask for a new one "
            "from the sign-in page.",
        ),
    )


class PasswordLinkInfo(BaseModel):
    email: EmailStr
    #: `welcome` (a first password) or `reset` (a forgotten one): the page words itself.
    purpose: str


@router.get("/password-link/{token}", response_model=PasswordLinkInfo)
async def password_link_info(token: str, db: AsyncSession = SESSION):
    """Whose link this is, before the page asks for a password: a dead link says so at
    once, rather than after the person has typed twice."""
    try:
        user, purpose = await password_link_service.resolve(db, token)
    except password_link_service.PasswordLinkError as exc:
        raise _link_refusal(exc.reason) from None
    return PasswordLinkInfo(email=user.email, purpose=purpose)


class PasswordLinkIn(BaseModel):
    new_password: str = Field(min_length=10)


@router.post("/password-link/{token}", response_model=LoginOut)
async def password_link_consume(
    token: str, data: PasswordLinkIn, db: AsyncSession = SESSION
):
    """Set the password the person chose and open their session at once: the link proved
    they hold the mailbox, and asking them to type it again right away proves nothing."""
    try:
        user = await password_link_service.consume(db, token, data.new_password)
    except password_link_service.PasswordLinkError as exc:
        raise _link_refusal(exc.reason) from None
    return LoginOut(
        access_token=create_access_token(str(user.id), user.role),
        role=user.role,
        must_change_password=False,
    )


class MeOut(BaseModel):
    """Who is signed in, for a front end that only kept a token across a refresh."""

    id: uuid.UUID
    email: EmailStr
    account_name: str | None = None
    role: str
    sees_whole_fund: bool
    must_change_password: bool
    #: Who the account works for, as the console qualified it (`core.account_kind`). The
    #: label comes translated from here, like every label the server owns; both are NULL
    #: for an account nobody qualified, and the screen says so rather than guessing.
    account_kind: str | None = None
    account_kind_label: str | None = None


@router.get("/me", response_model=MeOut)
async def me(user: User = Depends(current_user)):
    return MeOut(
        id=user.id,
        email=user.email,
        account_name=user.account_name,
        role=user.role,
        sees_whole_fund=user.sees_whole_fund,
        must_change_password=user.must_change_password,
        account_kind=user.account_kind,
        account_kind_label=account_kind.label_of(user.account_kind),
    )


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    data: ChangePasswordIn,
    user: User = Depends(current_user),
    db: AsyncSession = SESSION,
):
    """The holder replaces the credential somebody else handed them.

    🔴 THIS ROUTE WAS MISSING, AND IT WAS THE PRODUCT'S WORST HOLE. `must_change_password`
    is set by the bootstrap, by Alice when an account is created, and on every reset; the
    login faithfully reports it. But nothing let anybody act on it: a user was required to
    replace a password somebody else had seen, and given no way to do so. A control that
    cannot be satisfied is not a control, it is a sign.

    ⚠️ THE CURRENT PASSWORD IS REQUIRED, even when `must_change_password` is true. A stolen
    token would otherwise be enough to take the account for good: the victim loses access
    and the attacker keeps it. A token proves somebody got in, never that they are the
    holder.
    """
    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            pick(
                "Le mot de passe actuel est incorrect.",
                "The current password is wrong.",
            ),
        )
    if verify_password(data.new_password, user.hashed_password):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            pick(
                "Le nouveau mot de passe est identique à l'ancien : il n'a pas cessé d'être connu de qui vous l'a transmis.",
                "The new password is the same as the old one: whoever handed it to you still knows it.",
            ),
        )
    user.hashed_password = hash_password(data.new_password)
    user.must_change_password = False
    await db.commit()
