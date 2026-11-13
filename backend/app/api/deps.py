"""Who is asking, and what they are allowed to see.

🔴 SCOPING IS A RULE OF THE API, NEVER A HABIT OF THE SCREENS. An investor portal that
fetches the fund's data and filters it in the browser has already sent it. `investor_scope`
is what every read passes through, and it answers with an investor id or with « the whole
fund » — there is no third answer, and no endpoint decides for itself.
"""

import uuid

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.firm_scope import firm_of, set_current_firm
from app.core.security import opens_a_session, read_access_token
from app.database import SESSION
from app.models.investor import Investor
from app.models.user import User
from app.services import licence_state, session_service
from app.core.i18n import pick


async def current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = SESSION,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            pick("Authentification requise.", "Sign in required."),
        )
    claims = read_access_token(authorization.split(" ", 1)[1])
    # 🔴 A SESSION TOKEN, AND NO OTHER (3 Nov 2026). The password link and the second step
    # of the sign-in are signed with the same key and name the same account: without
    # `opens_a_session` the intermediate token of the second factor, given for the
    # password alone, would open every door, and a password link presented as a bearer
    # did until then (measured: `/auth/me` answered 200 to one).
    if not claims or not claims.get("sub") or not opens_a_session(claims):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            pick("Session expirée ou invalide.", "Session expired or invalid."),
        )
    if await session_service.is_closed(db, claims):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            pick("Session expirée ou invalide.", "Session expired or invalid."),
        )
    user = await db.get(User, uuid.UUID(claims["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            pick("Compte inactif.", "This account is inactive."),
        )

    # 🔴 THE FIRM'S LICENCE, ON EVERY REQUEST (the owner, 8 Nov 2026). A colleague of a
    # suspended or ended firm is refused here, mid-session as at the sign-in; its subscriber
    # keeps « Mon abonnement » and nothing else, suspended or ended alike (9 Nov 2026); the
    # investors are not concerned. Once it ended, its subscriber still READS for thirty days,
    # to export (terms of sale, 7.4).
    user.licence_held = await licence_state.gate(
        user, reading=request.method in ("GET", "HEAD")
    )
    if user.licence_held and not licence_state.held_subscriber_may_reach(
        request.url.path
    ):
        raise licence_state.held_subscriber_refusal(user.licence_held)

    # 🔴 THE MANAGEMENT COMPANY IS ESTABLISHED HERE, AND NOWHERE ELSE.
    #
    # From this line on, EVERY query touching a fund, a project, an investor or a bank
    # movement is filtered by `core.firm_scope`, whether the place that writes it thinks
    # about it or not. That is what makes a leak structurally impossible rather than
    # dependent on sixty-eight correct `where` clauses.
    #
    # ⚠️ A ContextVar SET INSIDE THE REQUEST'S TASK DOES NOT LEAK into the others: each
    # FastAPI request runs in its own task with its own copy of the context. In TESTS there
    # is no task per request, and an autouse fixture puts the value back -- this product has
    # already paid for a leaked ContextVar once, on the reader's language.
    set_current_firm(firm_of(user))
    # The journal's actor gets its name HERE, where the account is loaded: the token only
    # carries an id, and a journal of ids is one nobody can read.
    audit.identify(user_id=user.id, user_email=user.email)
    return user


async def current_manager(user: User = Depends(current_user)) -> User:
    if not user.sees_whole_fund:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            pick(
                "Réservé à la gestion du fonds.", "Restricted to the fund's management."
            ),
        )
    return user


async def investor_scope(
    user: User = Depends(current_user), db: AsyncSession = SESSION
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
            pick(
                "Ce compte n'est rattaché à aucun investisseur : rien à afficher.",
                "This account is attached to no investor: there is nothing to show.",
            ),
        )
    return found
