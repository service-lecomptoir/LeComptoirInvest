"""Sessions closed on the server: what « Déconnexion » does besides clearing the browser.

The token is a stateless JWT that lives its whole lifetime once issued. Before this, a
sign-out forgot it in the browser only: a copy (a shared computer, a stolen browser
profile) kept opening the account until the token expired. Signing out now writes the
token's session id into `revoked_sessions`, and `api/deps.current_user` refuses it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import RevokedSession


async def is_closed(db: AsyncSession, claims: dict) -> bool:
    """Was the session of these claims closed by « Déconnexion »? A token issued before
    session ids existed carries none and lives out its own expiry."""
    sid = claims.get("sid")
    return bool(sid) and await db.get(RevokedSession, sid) is not None


async def close(db: AsyncSession, claims: dict | None) -> bool:
    """Closes the session of these claims, and purges the closed sessions whose token has
    expired. An unreadable or expired token (no claims) closes nothing."""
    sid = claims.get("sid") if claims else None
    if not sid or not claims.get("exp"):
        return False
    await db.execute(
        delete(RevokedSession).where(RevokedSession.expires_at < datetime.now(UTC))
    )
    if await db.get(RevokedSession, sid) is None:
        db.add(
            RevokedSession(
                sid=sid, expires_at=datetime.fromtimestamp(claims["exp"], UTC)
            )
        )
    return True
