"""Symmetric encryption of what must never be readable in a database dump.

WHAT IS ENCRYPTED HERE: investors' bank details. A fund's investor table is a list of names,
addresses and IBANs — the single most useful file to steal in the whole product — and a
backup, a replica or a mis-scoped dump exposes it entirely if it is stored in clear.

The sister product encrypts its landlords' payment secrets exactly this way; this one has
no reason to be laxer, and the shape is deliberately identical so the two can be reasoned
about together.

⚠️ THE KEY DERIVES FROM `SECRET_KEY`, WHICH HAS NO DEFAULT. A fallback would give every
deployment that forgot to set one the same key, which is the same as no encryption while
looking encrypted. Missing key raises here rather than silently storing clear text.
"""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    secret = (get_settings().SECRET_KEY or "").strip()
    if not secret:
        raise RuntimeError(
            "SECRET_KEY is not set. It derives the key that encrypts investors' bank "
            "details: refusing to run rather than write them in clear."
        )
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt(value: str | None) -> str | None:
    """Encrypt. None or blank gives None — an absent IBAN is absent, not an empty secret."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(token: str | None) -> str | None:
    """Decrypt. An unreadable token gives None and never raises.

    ⚠️ NEVER RAISES, ON PURPOSE. A rotated key or a value written before encryption was
    turned on must not take down the screen that lists investors: the field reads as absent,
    which is visible and fixable, where a 500 on a list page is neither.
    """
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def fingerprint(value: str | None) -> str | None:
    """A stable, non-reversible fingerprint of an IBAN, for MATCHING without decrypting.

    THIS IS WHAT MAKES ENCRYPTION USABLE HERE. Reconciliation needs to ask « does this
    incoming transfer come from an IBAN we know? », and an encrypted column cannot be
    searched: Fernet output differs on every encryption of the same value. The fingerprint
    is deterministic, so it can be indexed and compared, and it reveals nothing on its own.

    Salted with `SECRET_KEY` so the fingerprints of one deployment say nothing about
    another's, and so a stolen table cannot be tested against a list of candidate IBANs
    without the key.
    """
    if not value:
        return None
    normalised = "".join(value.split()).upper()
    if not normalised:
        return None
    secret = (get_settings().SECRET_KEY or "").strip()
    if not secret:
        raise RuntimeError(
            "SECRET_KEY is not set: refusing to compute an unsalted fingerprint."
        )
    return hashlib.sha256(f"{secret}|{normalised}".encode("utf-8")).hexdigest()
