"""Signing in."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, verify_password
from app.database import get_db
from app.models.user import User

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
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants incorrects.")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ce compte est désactivé.")
    return LoginOut(
        access_token=create_access_token(str(user.id), user.role),
        role=user.role,
        must_change_password=user.must_change_password,
    )
