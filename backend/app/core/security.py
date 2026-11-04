"""Passwords and tokens."""

import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

#: ⚠️ BCRYPT IS A QUARTER OF A SECOND OF CPU BY DESIGN (a second on the loaded machine of
#: the customer recipe of Le Comptoir BTP, 30 Sept 2026, where the account Alice opened held
#: the worker that long). An `async def` hands `hash_password`, `verify_password` and
#: `password_link_service.unusable_password` to the threadpool (`run_in_threadpool`),
#: never calls them: the library releases the GIL, the loop keeps serving. Guard:
#: `tests_unit/test_the_event_loop_is_never_held.py`.
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_ALGORITHM = "HS256"

#: What a session token opens. 🔴 THE PASSWORD LINK AND THE SECOND STEP OF THE SIGN-IN ARE
#: SIGNED WITH THE SAME KEY AND NAME THE SAME ACCOUNT (`sub`): until 3 Nov 2026 the door
#: read any of them as a session, so a password link presented as a bearer opened the
#: account for its two hours, or its week (measured: `/auth/me` answered 200). A token of
#: another `type` is refused; a token issued before the field existed carries none and
#: lives out its own expiry (twelve hours at most).
ACCESS_TOKEN_TYPE = "access"


def hash_password(raw: str) -> str:
    return _pwd.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return _pwd.verify(raw, hashed)
    except ValueError:
        return False


def create_access_token(subject: str, role: str) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        # `sid`: the session this sign-in opens, what « Déconnexion » closes on the
        # server (`services/session_service.py`). One token, one session: nothing
        # renews it, so each token issued is a sign-in of its own.
        #
        # `type`: what the token opens (`ACCESS_TOKEN_TYPE`, the session). Every other
        # token signed with this key (the password link, the second step of the sign-in)
        # names another, and the door refuses it (`deps.current_user`).
        {
            "sub": subject,
            "role": role,
            "exp": expire,
            "sid": uuid.uuid4().hex,
            "type": ACCESS_TOKEN_TYPE,
        },
        settings.SECRET_KEY,
        algorithm=_ALGORITHM,
    )


def read_access_token(token: str) -> dict | None:
    """Claims, or None. Never raises: an expired token is a 401, not a 500."""
    try:
        return jwt.decode(token, get_settings().SECRET_KEY, algorithms=[_ALGORITHM])
    except JWTError:
        return None


def opens_a_session(claims: dict) -> bool:
    """Is this a session token? A token with no `type` was issued before the field existed
    (a session, at most twelve hours old); any other `type` opens something else."""
    return claims.get("type", ACCESS_TOKEN_TYPE) == ACCESS_TOKEN_TYPE


# ── Second factor: the intermediate token between the password and the code ─────────


def create_two_factor_pending_token(subject: str) -> str:
    """A few minutes, one purpose: it opens nothing but the second step of the sign-in
    (`opens_a_session` refuses it at every other door). No `sid`: it is no session."""
    from app.core.two_factor import PENDING_TOKEN_MINUTES, PENDING_TOKEN_TYPE

    expire = datetime.now(UTC) + timedelta(minutes=PENDING_TOKEN_MINUTES)
    return jwt.encode(
        {"sub": subject, "exp": expire, "type": PENDING_TOKEN_TYPE},
        get_settings().SECRET_KEY,
        algorithm=_ALGORITHM,
    )


def read_two_factor_pending_token(token: str) -> str | None:
    """The account id an intermediate token names, or None (expired, forged, other type)."""
    from app.core.two_factor import PENDING_TOKEN_TYPE

    claims = read_access_token(token)
    if not claims or claims.get("type") != PENDING_TOKEN_TYPE:
        return None
    subject = claims.get("sub")
    return str(subject) if subject else None
