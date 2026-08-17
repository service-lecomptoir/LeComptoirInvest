"""Passwords and tokens."""

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

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
        {"sub": subject, "role": role, "exp": expire},
        settings.SECRET_KEY,
        algorithm=_ALGORITHM,
    )


def read_access_token(token: str) -> dict | None:
    """Claims, or None. Never raises: an expired token is a 401, not a 500."""
    try:
        return jwt.decode(token, get_settings().SECRET_KEY, algorithms=[_ALGORITHM])
    except JWTError:
        return None
