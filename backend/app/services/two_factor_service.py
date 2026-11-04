"""The second factor of an account: set-up, sign-in, backup codes, removal, reset.

The arithmetic lives in `app.core.two_factor` (the same file in every product of Le
Comptoir, under a fingerprint guard); this module is this product's glue: the secret is
encrypted by `core/crypto` (the data keyring that already encrypts the investors' bank
details), the backup codes are keyed fingerprints, and every event of the factor writes
ONE line of the audit journal, never a code:

- `two_factor.enabled`, `two_factor.disabled`, `two_factor.failed`,
  `two_factor.backup_code_used`, `two_factor.backup_codes_regenerated`, `two_factor.reset`.

The owner, 2 Nov 2026: offered to every account, RECOMMENDED (a discreet banner, never an
obligation) to whoever runs the fund: the manager (`manager`, the subscriber and the
colleagues of its management company) and the platform's administrator (`admin`). An
investor's account may switch it on too; it is not invited.

🔴 NO SCREEN OF THIS PRODUCT ADMINISTERS ANOTHER ACCOUNT: the console (Alice) creates,
blocks and resets them through `/internal`, and no screen of the fund opens, blocks or
resets a colleague's or an investor's login. A lost phone is therefore answered by
`scripts/reset_two_factor.py` on the server, never by a route (a route that removes the
factor would be the one door a stolen password needs).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.config import get_settings
from app.core import audit, crypto, email_envelope, two_factor
from app.core.i18n import pick, use_lang
from app.models.two_factor import UserTwoFactor
from app.models.user import FUND_WIDE_ROLES, User
from app.services import email_themes, mailer

logger = logging.getLogger(__name__)

#: The accounts the banner invites to switch it on: whoever runs the fund.
RECOMMENDED_ROLES = frozenset(FUND_WIDE_ROLES)

ENABLED = "two_factor.enabled"
DISABLED = "two_factor.disabled"
FAILED = "two_factor.failed"
BACKUP_CODE_USED = "two_factor.backup_code_used"
BACKUP_CODES_REGENERATED = "two_factor.backup_codes_regenerated"
RESET = "two_factor.reset"


def issuer() -> str:
    """The name an authenticator app shows above the code: the product's own."""
    return get_settings().APP_NAME


def _pepper() -> str:
    return get_settings().SECRET_KEY


async def row_of(db: AsyncSession, user_id: Any) -> UserTwoFactor | None:
    return await db.scalar(
        select(UserTwoFactor).where(UserTwoFactor.user_id == user_id)
    )


def is_on(row: UserTwoFactor | None) -> bool:
    return row is not None and row.enabled_at is not None


async def is_enabled(db: AsyncSession, user: User) -> bool:
    return is_on(await row_of(db, user.id))


def is_recommended(user: User) -> bool:
    return user.role in RECOMMENDED_ROLES


async def status_of(db: AsyncSession, user: User) -> dict[str, Any]:
    row = await row_of(db, user.id)
    on = row if is_on(row) else None
    return {
        "enabled": on is not None,
        "enabled_at": on.enabled_at if on else None,
        "backup_codes_remaining": len(on.backup_codes_hashed or []) if on else 0,
        "recommended": is_recommended(user),
        # 🔴 NEVER REQUIRED IN THE PRODUCT (the owner, 2 Nov 2026): only the console's is.
        "required": False,
    }


async def _journal(
    db: AsyncSession, action: str, target: User, details: dict | None = None
) -> None:
    """One line of the journal, under the name of whoever acts (the request's actor: the
    person, or the server's command that reset it). Never a code, never the secret."""
    await audit.record(
        db, action, entity_type="users", entity_id=target.id, details=details or {}
    )


async def start_setup(db: AsyncSession, user: User) -> dict[str, str] | None:
    """A fresh secret, stored encrypted, NOT active until a first valid code. None when the
    factor is already on. Called again before the activation, it draws a new QR code."""
    row = await row_of(db, user.id)
    if is_on(row):
        return None
    secret = two_factor.generate_secret()
    sealed = crypto.encrypt(secret) or ""
    if row is None:
        db.add(UserTwoFactor(user_id=user.id, secret_encrypted=sealed))
    else:
        row.secret_encrypted = sealed
        row.last_step = None
        row.backup_codes_hashed = None
    await db.flush()
    uri = two_factor.provisioning_uri(secret, user.email, issuer())
    return {
        "secret": secret,
        "otpauth_uri": uri,
        "qr_code": two_factor.qr_code_svg(uri),
    }


async def _accept_step(db: AsyncSession, row: UserTwoFactor, step: int) -> bool:
    """Writes `step` as the last accepted one, ONLY if it is after the stored one: one
    conditional UPDATE, so two requests carrying the same code cannot both pass."""
    result = await db.execute(
        update(UserTwoFactor)
        .where(
            UserTwoFactor.id == row.id,
            or_(UserTwoFactor.last_step.is_(None), UserTwoFactor.last_step < step),
        )
        .values(last_step=step)
        .execution_options(synchronize_session=False)
    )
    if getattr(result, "rowcount", 0) != 1:
        return False
    set_committed_value(row, "last_step", step)
    return True


async def _check_code(db: AsyncSession, row: UserTwoFactor, code: str | None) -> bool:
    secret = crypto.decrypt(row.secret_encrypted)
    if not secret:
        return False
    step = two_factor.match_step(secret, code, row.last_step)
    if step is None:
        return False
    return await _accept_step(db, row, step)


async def activate(db: AsyncSession, user: User, code: str | None) -> list[str] | None:
    """Switches the factor on after a first valid code: the ten backup codes, shown once.
    None when the code is wrong or no set-up is waiting. The caller commits."""
    row = await row_of(db, user.id)
    if row is None or is_on(row):
        return None
    if not await _check_code(db, row, code):
        return None
    codes = two_factor.generate_backup_codes()
    row.backup_codes_hashed = two_factor.hash_backup_codes(codes, _pepper())
    row.enabled_at = datetime.now(UTC)
    await _journal(db, ENABLED, user)
    return codes


async def verify_second_step(
    db: AsyncSession,
    user: User,
    code: str | None = None,
    backup_code: str | None = None,
) -> bool:
    """A code of the app, or one backup code (used up). Journals the failure or the use of
    a backup code; the caller commits in both cases."""
    row = await row_of(db, user.id)
    if row is None or not is_on(row):
        return False
    if backup_code:
        left = two_factor.consume_backup_code(
            row.backup_codes_hashed, backup_code, [_pepper()]
        )
        if left is None:
            await _journal(db, FAILED, user, {"method": "backup_code"})
            return False
        row.backup_codes_hashed = left
        await _journal(db, BACKUP_CODE_USED, user, {"remaining": len(left)})
        return True
    if await _check_code(db, row, code):
        return True
    await _journal(db, FAILED, user, {"method": "totp"})
    return False


async def regenerate_backup_codes(db: AsyncSession, user: User) -> list[str] | None:
    row = await row_of(db, user.id)
    if row is None or not is_on(row):
        return None
    codes = two_factor.generate_backup_codes()
    row.backup_codes_hashed = two_factor.hash_backup_codes(codes, _pepper())
    await _journal(db, BACKUP_CODES_REGENERATED, user)
    return codes


async def disable(db: AsyncSession, user: User) -> None:
    """Removes the factor (the caller has checked the password AND a code)."""
    row = await row_of(db, user.id)
    if row is not None:
        await db.delete(row)
    await _journal(db, DISABLED, user)


async def reset_by(db: AsyncSession, target: User, by: str) -> bool:
    """The server's command removes the factor of somebody who lost their phone. The
    journal line carries the request's actor and says who in `by`. False when none was on.
    """
    row = await row_of(db, target.id)
    if row is None or not is_on(row):
        return False
    await db.delete(row)
    await _journal(db, RESET, target, {"by": by})
    return True


def letter(target: User) -> email_envelope.Letter:
    """The e-mail that tells the person their second factor was removed, in the holder's
    language (the server's command has no request, hence no reader's language)."""
    product = get_settings().APP_NAME
    with use_lang(target.locale):
        name = (target.account_name or "").strip()
        greeting = (
            pick(f"Bonjour {name},", f"Hello {name},")
            if name
            else pick("Bonjour,", "Hello,")
        )
        lead = pick(
            f"La double authentification de votre compte {product} vient d'être retirée par le support. Vous vous connectez désormais avec votre seul mot de passe. Réactivez-la depuis Mon profil, section Sécurité.",
            f"The two-factor authentication of your {product} account has just been removed by support. You now sign in with your password alone. Turn it on again from My profile, Security section.",
        )
        warning = pick(
            "Si vous n'êtes pas à l'origine de cette demande, changez votre mot de passe et prévenez le support.",
            "If you did not ask for this, change your password and warn support.",
        )
        return email_envelope.Letter(
            title=pick(
                "Double authentification retirée de votre compte",
                "Two-factor authentication removed from your account",
            ),
            brand=product,
            body="\n\n".join([greeting, lead, warning]),
            signature=(pick("Cordialement,", "Kind regards,"), product),
            footer=pick(
                f"{product} · Ce message est automatique, merci de ne pas y répondre.",
                f"{product} · This message is automatic, please do not reply to it.",
            ),
            lang=target.locale or "fr",
        )


async def notify_reset(db: AsyncSession, target: User) -> bool:
    """Tells the person, in the look their management company chose (fail-soft: the reset
    stands when the letter does not leave). Straight to the mailer, like the password
    link: a security letter is not a notice one may switch off."""
    if not (target.email or "").strip():
        return False
    written = letter(target)
    try:
        look = await email_themes.look_for_firm(db, target.firm_id or target.id)
        await mailer.send(
            to=target.email,
            subject=written.title + " · " + written.brand,
            body=written.text(),
            html=email_envelope.render(look, written),
        )
    except Exception as exc:  # noqa: BLE001 - a letter never undoes the reset
        logger.warning("Second factor reset letter not sent (%s): %s", target.id, exc)
        return False
    return True


__all__ = [
    "BACKUP_CODES_REGENERATED",
    "BACKUP_CODE_USED",
    "DISABLED",
    "ENABLED",
    "FAILED",
    "RECOMMENDED_ROLES",
    "RESET",
    "activate",
    "disable",
    "is_enabled",
    "is_on",
    "is_recommended",
    "letter",
    "notify_reset",
    "regenerate_backup_codes",
    "reset_by",
    "row_of",
    "start_setup",
    "status_of",
    "verify_second_step",
]
