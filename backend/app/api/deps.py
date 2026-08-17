"""Who is asking, and what they are allowed to see.

🔴 SCOPING IS A RULE OF THE API, NEVER A HABIT OF THE SCREENS. An investor portal that
fetches the fund's data and filters it in the browser has already sent it. `investor_scope`
is what every read passes through, and it answers with an investor id or with « the whole
fund » — there is no third answer, and no endpoint decides for itself.
"""

import uuid

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import read_access_token
from app.database import get_db
from app.models.investor import Investor
from app.models.user import User


async def current_user(
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise.")
    claims = read_access_token(authorization.split(" ", 1)[1])
    if not claims or not claims.get("sub"):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Session expirée ou invalide."
        )
    user = await db.get(User, uuid.UUID(claims["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte inactif.")
    return user


async def current_manager(user: User = Depends(current_user)) -> User:
    if not user.sees_whole_fund:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé à la gestion du fonds.")
    return user


async def investor_scope(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> uuid.UUID | None:
    """The investor this caller is confined to, or None for « the whole fund ».

    ⚠️ AN INVESTOR ACCOUNT WITH NO INVESTOR RECORD SEES NOTHING, and is refused rather than
    shown everything. The failure mode of a scoping rule must be « too little », never « the
    fund's entire register », and an unlinked account is exactly the state a mistake creates.
    """
    if user.sees_whole_fund:
        return None
    found = (
        await db.execute(
            select(Investor.id).where(Investor.user_id == user.id).limit(1)
        )
    ).scalar_one_or_none()
    if found is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Ce compte n'est rattaché à aucun investisseur : rien à afficher.",
        )
    return found
