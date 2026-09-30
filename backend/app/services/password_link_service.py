"""A password is CHOSEN through a link, never received in an e-mail.

🔴 WHY THIS EXISTS (customer recipe, 30 Sept 2026). This product had no « mot de passe
oublié » at all: a manager or an investor who forgot theirs had no way back in but to write
to support. And an account opened by the console arrived with a temporary password written
in clear in an e-mail. The house rule (Immo, 8 Sept 2026, then PDF, Compta, RH): no password
travels by e-mail. The letter carries a link to the page where the person types the one
they want, for a first sign-in as for a forgotten one, and the page opens the session.

The link is a SIGNED TOKEN, not a row: it names the account, the purpose and the expiry,
and it is bound to a FINGERPRINT of the password hash in force when it was issued. Setting
the password changes the hash, hence the fingerprint, hence every link issued before dies
at once: single use without a table to keep, and an old e-mail found later cannot reopen
the door. Two purposes, two lifetimes: a welcome link waits a week for somebody who never
signed in; a reset link lasts two hours.

⚠️ THE LETTER SPEAKS THE HOLDER'S LANGUAGE (`User.locale`, through `use_lang`): there is no
request behind a welcome link the console asks for. It wears the look the management
company chose (the product's default otherwise), and the link is a button.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.concurrency import run_in_threadpool

from app.config import get_settings
from app.core import email_envelope
from app.core.i18n import pick, use_lang
from app.core.security import hash_password
from app.models.user import User
from app.services import email_themes, mailer

logger = logging.getLogger(__name__)

Purpose = Literal["welcome", "reset"]
LIFETIMES: dict[str, timedelta] = {
    "welcome": timedelta(days=7),
    "reset": timedelta(hours=2),
}
TOKEN_TYPE = "password_link"
_ALGORITHM = "HS256"
#: The front end's route that consumes the token. One constant, read by the tests too.
LINK_PATH = "/set-password/"


class PasswordLinkError(Exception):
    """Why a link cannot be honoured: `invalid`, `expired` or `used`."""

    def __init__(self, reason: Literal["invalid", "expired", "used"]):
        super().__init__(reason)
        self.reason = reason


def unusable_password() -> str:
    """The hash of an account nobody has chosen a password for yet: a random secret nobody
    ever saw, so no sign-in can match it until the holder follows their link."""
    return hash_password(secrets.token_urlsafe(32))


def fingerprint(user: User) -> str:
    """What the link is bound to: a short digest of the CURRENT password hash."""
    return hashlib.sha256((user.hashed_password or "").encode("utf-8")).hexdigest()[:16]


def issue(user: User, purpose: Purpose) -> str:
    """A signed token for `user`, good for one setting of the password."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "type": TOKEN_TYPE,
        "purpose": purpose,
        "fp": fingerprint(user),
        "iat": now,
        "exp": now + LIFETIMES[purpose],
    }
    return jwt.encode(payload, get_settings().SECRET_KEY, algorithm=_ALGORITHM)


def link_for(token: str) -> str:
    return get_settings().PUBLIC_APP_URL.rstrip("/") + LINK_PATH + token


def purpose_for(user: User) -> Purpose:
    """Somebody who never signed in gets a week; somebody who did gets two hours."""
    return "welcome" if user.last_login_at is None else "reset"


def letter(user: User, purpose: Purpose, url: str) -> email_envelope.Letter:
    """The whole letter, in the holder's language."""
    product = get_settings().APP_NAME
    with use_lang(user.locale):
        name = (user.account_name or "").strip()
        greeting = (
            pick(f"Bonjour {name},", f"Hello {name},")
            if name
            else pick("Bonjour,", "Hello,")
        )
        # ⚠️ THE LINK COMES AFTER THESE WORDS (a button, then its address): they say
        # « ci-dessous », never « ce lien : » followed by another sentence.
        if purpose == "welcome":
            title = pick("Choisissez votre mot de passe", "Choose your password")
            paragraphs = [
                pick(
                    f"Votre espace {product} est ouvert. Choisissez votre mot de passe avec "
                    "le lien ci-dessous : vous serez connecté aussitôt.",
                    f"Your {product} space is open. Choose your password with the link "
                    "below: you will be signed in at once.",
                ),
                pick(
                    "Ce lien est valable une semaine et ne sert qu'une fois.",
                    "This link is valid for one week and works once.",
                ),
            ]
            label = pick("Choisir mon mot de passe", "Choose my password")
        else:
            title = pick("Un nouveau mot de passe", "A new password")
            paragraphs = [
                pick(
                    "Vous avez demandé à choisir un nouveau mot de passe. Le lien ci-dessous "
                    "est valable deux heures et ne sert qu'une fois.",
                    "You asked to choose a new password. The link below is valid for two "
                    "hours and works once.",
                ),
                pick(
                    "Si vous n'avez rien demandé, ignorez ce message : votre mot de "
                    "passe reste inchangé.",
                    "If you asked for nothing, ignore this message: your password is "
                    "unchanged.",
                ),
            ]
            label = pick("Choisir un nouveau mot de passe", "Choose a new password")
        return email_envelope.Letter(
            title=title,
            brand=product,
            body="\n\n".join([greeting, *paragraphs]),
            signature=(pick("Cordialement,", "Kind regards,"), product),
            footer=pick(
                f"{product} · Ce message est automatique, merci de ne pas y répondre.",
                f"{product} · This message is automatic, please do not reply to it.",
            ),
            lang=user.locale or "fr",
            action=(label, url),
        )


async def send_link(db: AsyncSession, user: User, purpose: Purpose) -> bool:
    """Issue a link for `user` and e-mail it. Never raises: a delivery failure is the
    caller's to report (« link not sent »), not to crash on."""
    written = letter(user, purpose, link_for(issue(user, purpose)))
    try:
        # The look of the management company the account belongs to: its own for a
        # manager, the one that runs the fund for an investor.
        look = await email_themes.look_for_firm(db, user.firm_id or user.id)
        await mailer.send(
            to=user.email,
            subject=written.title + " · " + written.brand,
            body=written.text(),
            html=email_envelope.render(look, written),
        )
    except Exception as exc:  # noqa: BLE001 - reported to the caller as « not sent »
        logger.warning("Password link not sent (%s): %s", user.id, exc)
        return False
    return True


def _payload(token: str) -> dict:
    try:
        payload = jwt.decode(token, get_settings().SECRET_KEY, algorithms=[_ALGORITHM])
    except ExpiredSignatureError as exc:
        raise PasswordLinkError("expired") from exc
    except JWTError as exc:
        raise PasswordLinkError("invalid") from exc
    if payload.get("type") != TOKEN_TYPE or payload.get("purpose") not in LIFETIMES:
        raise PasswordLinkError("invalid")
    return payload


async def resolve(db: AsyncSession, token: str) -> tuple[User, Purpose]:
    """The account and purpose behind a link that is still good, or a PasswordLinkError."""
    payload = _payload(token)
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except ValueError as exc:
        raise PasswordLinkError("invalid") from exc
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise PasswordLinkError("invalid")
    if payload.get("fp") != fingerprint(user):
        # The password changed since the link was issued: through this link or another,
        # the door it opened is closed.
        raise PasswordLinkError("used")
    return user, payload["purpose"]


async def consume(db: AsyncSession, token: str, new_password: str) -> User:
    """Set the password the person chose, through a link that is still good.

    The account leaves the « handed-over password » state as well: the password is now the
    person's own, whatever door the account came through.
    """
    user, _purpose = await resolve(db, token)
    user.hashed_password = await run_in_threadpool(hash_password, new_password)
    user.must_change_password = False
    user.last_login_at = datetime.now(UTC)
    await db.flush()
    return user


__all__ = [
    "LIFETIMES",
    "LINK_PATH",
    "PasswordLinkError",
    "Purpose",
    "consume",
    "fingerprint",
    "issue",
    "letter",
    "link_for",
    "purpose_for",
    "resolve",
    "send_link",
    "unusable_password",
]
