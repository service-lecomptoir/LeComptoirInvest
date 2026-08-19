"""Signing in, and replacing the credential somebody else handed you."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models.user import User
from app.core.i18n import pick

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
async def login(data: LoginIn, db: AsyncSession = Depends(get_db)):
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
    return LoginOut(
        access_token=create_access_token(str(user.id), user.role),
        role=user.role,
        must_change_password=user.must_change_password,
    )


class MeOut(BaseModel):
    """Who is signed in, for a front end that only kept a token across a refresh."""

    id: uuid.UUID
    email: EmailStr
    account_name: str | None = None
    role: str
    sees_whole_fund: bool
    must_change_password: bool


@router.get("/me", response_model=MeOut)
async def me(user: User = Depends(current_user)):
    return MeOut(
        id=user.id,
        email=user.email,
        account_name=user.account_name,
        role=user.role,
        sees_whole_fund=user.sees_whole_fund,
        must_change_password=user.must_change_password,
    )


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    data: ChangePasswordIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
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
