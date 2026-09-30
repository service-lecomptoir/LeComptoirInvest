"""The settings of the account that sends the letters: today, the look of its e-mails.

🔴 THE CHOICE IS THE MANAGEMENT COMPANY'S, stored on the row `firm_of(user)` points at. A
letter to an investor goes out on the company's behalf, whoever clicked, so two managers of
one company cannot dress its letters two ways. An investor's login has no such setting: it
sends nothing.

🔴 THE LIST IS ALICE'S (`services.email_themes`), and so is the check. A key the console
does not list is refused with a sentence, never stored: a choice nobody can render would
turn every letter into the default without anybody having chosen it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_manager
from app.core.firm_scope import firm_of
from app.core.i18n import pick
from app.database import SESSION
from app.models.user import User
from app.services import email_themes

router = APIRouter(prefix="/account", tags=["account"])


class EmailFamilyOut(BaseModel):
    key: str
    name: str
    hint: str


class EmailThemeOut(BaseModel):
    key: str
    name: str
    description: str
    family: str
    layout: str
    ink: str
    accent: str
    soft: str


class EmailLookOut(BaseModel):
    """The company's choice, and what it may choose from."""

    #: The chosen key, or None for the product's own look.
    email_theme: str | None
    #: The product's own look, as the console set it. None when the console is out of
    #: reach with no copy kept, or names a look it does not list.
    default: str | None
    families: list[EmailFamilyOut]
    themes: list[EmailThemeOut]
    #: False when the console never answered: the screen then says so, rather than
    #: showing an empty list that reads as « there is nothing to choose ».
    catalogue_available: bool


class EmailLookIn(BaseModel):
    #: A key of the console's catalogue, or None to go back to the product's own look.
    email_theme: str | None = Field(default=None, max_length=40)


async def _firm_account(db: AsyncSession, user: User) -> User:
    firm = await db.get(User, firm_of(user))
    if firm is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            pick(
                "Le compte de votre société de gestion est introuvable : l'apparence "
                "de ses e-mails ne peut pas être enregistrée.",
                "Your management company's account cannot be found: the look of its "
                "e-mails cannot be saved.",
            ),
        )
    return firm


async def _out(firm: User) -> EmailLookOut:
    kept = await email_themes.catalogue()
    return EmailLookOut(
        email_theme=firm.email_theme,
        default=kept.default if kept else None,
        families=[EmailFamilyOut(**f) for f in kept.families] if kept else [],
        themes=[EmailThemeOut(**t) for t in kept.themes] if kept else [],
        catalogue_available=kept is not None,
    )


@router.get("/email-theme", response_model=EmailLookOut)
async def read_email_look(
    user: User = Depends(current_manager), db: AsyncSession = SESSION
):
    return await _out(await _firm_account(db, user))


@router.put("/email-theme", response_model=EmailLookOut)
async def choose_email_look(
    data: EmailLookIn,
    user: User = Depends(current_manager),
    db: AsyncSession = SESSION,
):
    """Store the company's look, once the console's catalogue lists it.

    ⚠️ 422 FOR A KEY THE CATALOGUE DOES NOT LIST, 503 WHEN NOTHING CAN CHECK IT: the first
    is the request's fault, the second the console's, and the manager does something
    different about each. Going back to the product's own look (None) needs no check.
    """
    firm = await _firm_account(db, user)
    key = (data.email_theme or "").strip() or None
    if key is not None:
        try:
            await email_themes.check_choice(key)
        except email_themes.UnknownLook as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        except email_themes.CatalogueOutOfReach as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    firm.email_theme = key
    await db.commit()
    return await _out(firm)
