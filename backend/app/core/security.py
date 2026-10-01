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
        {"sub": subject, "role": role, "exp": expire, "sid": uuid.uuid4().hex},
        settings.SECRET_KEY,
        algorithm=_ALGORITHM,
    )


def read_access_token(token: str) -> dict | None:
    """Claims, or None. Never raises: an expired token is a 401, not a 500."""
    try:
        return jwt.decode(token, get_settings().SECRET_KEY, algorithms=[_ALGORITHM])
    except JWTError:
        return None
