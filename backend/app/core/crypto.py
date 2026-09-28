"""Symmetric encryption of what must never be readable in a database dump.

WHAT IS ENCRYPTED HERE: investors' bank details. A fund's investor table is a list of names,
addresses and IBANs — the single most useful file to steal in the whole product — and a
backup, a replica or a mis-scoped dump exposes it entirely if it is stored in clear.

The sister product (Le Comptoir RH) encrypts its staff numbers exactly this way; the
keyring below is written identically in both, so the two can be reasoned about together
and a fix travels instead of being re-invented.

🔴 A KEYRING, NOT A KEY, AND IT IS NOT `SECRET_KEY`. Until 28 Sept 2026 the one key was
DERIVED from `SECRET_KEY`: rotating the secret that signs sessions made every IBAN
unreadable, and nothing could re-encrypt them. `DATA_ENCRYPTION_KEYS` now holds an ordered
list of Fernet keys: the FIRST encrypts, EVERY one is tried to decrypt (`MultiFernet`).
Rotating means putting a new key first, running `python -m app.services.reencrypt`, then
dropping the old one — the procedure is in the README and `docs/rotation_cle_donnees.ps1`.

⚠️ UNSET, THE KEYRING IS EXACTLY TODAY'S KEY, derived from `SECRET_KEY` byte for byte, so a
deployment that has not made its key explicit keeps reading its data with no change. It is
the only case where `SECRET_KEY` still matters to the data, and the reason the first step of
the procedure writes that derived key down as the explicit one.

⚠️ `SECRET_KEY` STILL HAS NO DEFAULT. A fallback would give every deployment that forgot to
set one the same key, which is the same as no encryption while looking encrypted. Missing
key raises here rather than silently storing clear text.
"""

import base64
import hashlib
import hmac
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import get_settings


def _legacy_secret() -> str:
    """The secret the key was derived from before the keyring, read EXACTLY as then."""
    secret = (get_settings().SECRET_KEY or "").strip()
    if not secret:
        raise RuntimeError(
            "SECRET_KEY is not set. It derives the key that encrypts investors' bank "
            "details: refusing to run rather than write them in clear."
        )
    return secret


def legacy_key() -> str:
    """The key every value was encrypted with before `DATA_ENCRYPTION_KEYS` existed.

    Used by the keyring when the setting is empty, and by the procedure that writes it down
    as the explicit key. ⚠️ Never log it: it IS the key.
    """
    digest = hashlib.sha256(_legacy_secret().encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")


def key_id(key: str) -> str:
    """A short, non-reversible name for a key, so a key can be SPOKEN about in a log or a
    script output without being shown. Eight hex characters of its SHA-256."""
    return hashlib.sha256(key.encode("ascii")).hexdigest()[:8]


@lru_cache
def keyring() -> tuple[str, ...]:
    """The keys in force, the encrypting one first. Raises on a malformed setting.

    🔴 A MALFORMED KEY RAISES `RuntimeError`, NEVER `ValueError`: `decrypt` swallows
    `ValueError` on purpose, and a typo in the setting would then read as « every IBAN is
    absent » instead of stopping the application. The message names the POSITION of the
    bad key, never the key.
    """
    raw = (get_settings().DATA_ENCRYPTION_KEYS or "").strip()
    if not raw:
        return (legacy_key(),)
    keys = tuple(part.strip() for part in raw.split(",") if part.strip())
    for position, key in enumerate(keys, start=1):
        try:
            Fernet(key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise RuntimeError(
                f"DATA_ENCRYPTION_KEYS: key #{position} is not a Fernet key (32 bytes, "
                "url-safe base64). Refusing to start rather than read every value as absent."
            ) from exc
    if len(set(keys)) != len(keys):
        raise RuntimeError("DATA_ENCRYPTION_KEYS: the same key is listed twice.")
    return keys


def is_explicit() -> bool:
    """True once the keyring is written in `DATA_ENCRYPTION_KEYS` rather than derived."""
    return bool((get_settings().DATA_ENCRYPTION_KEYS or "").strip())


@lru_cache
def _multi() -> MultiFernet:
    return MultiFernet([Fernet(key.encode("ascii")) for key in keyring()])


@lru_cache
def _current() -> Fernet:
    return Fernet(keyring()[0].encode("ascii"))


def reset() -> None:
    """Forget the cached keyring. For tests and for a process that re-reads its settings."""
    for cached in (keyring, _multi, _current):
        cached.cache_clear()


def encrypt(value: str | None) -> str | None:
    """Encrypt. None or blank gives None — an absent IBAN is absent, not an empty secret."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return _multi().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(token: str | None) -> str | None:
    """Decrypt. An unreadable token gives None and never raises.

    ⚠️ NEVER RAISES, ON PURPOSE. A rotated key or a value written before encryption was
    turned on must not take down the screen that lists investors: the field reads as absent,
    which is visible and fixable, where a 500 on a list page is neither. The keyring is
    built OUTSIDE the `try`, so a malformed setting still raises.
    """
    if not token:
        return None
    multi = _multi()
    try:
        return multi.decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None


def is_current(token: str) -> bool:
    """Does this token open with the encrypting key ALONE? Fernet carries no key id, so
    this is asked by trying; it is what makes a re-encryption pass idempotent."""
    current = _current()
    try:
        current.decrypt(token.encode("ascii"))
    except (InvalidToken, ValueError, TypeError):
        return False
    return True


def rotate(token: str) -> str:
    """The same value, re-encrypted with the encrypting key. RAISES `InvalidToken` when no
    key of the ring opens it: the re-encryption pass must stop, not write a None."""
    return _multi().rotate(token.encode("ascii")).decode("ascii")


def _normalised(value: str | None) -> str | None:
    if not value:
        return None
    return "".join(value.split()).upper() or None


def _fingerprint_with(key: str, normalised: str) -> str:
    """HMAC-SHA256 of the IBAN under a sub-key of one data key."""
    subkey = hashlib.sha256(b"iban-fingerprint|" + key.encode("ascii")).digest()
    return hmac.new(subkey, normalised.encode("utf-8"), hashlib.sha256).hexdigest()


def _legacy_fingerprint(normalised: str) -> str:
    return hashlib.sha256(f"{_legacy_secret()}|{normalised}".encode()).hexdigest()


def fingerprint(value: str | None) -> str | None:
    """A stable, non-reversible fingerprint of an IBAN, for MATCHING without decrypting.

    THIS IS WHAT MAKES ENCRYPTION USABLE HERE. Reconciliation needs to ask « does this
    incoming transfer come from an IBAN we know? », and an encrypted column cannot be
    searched: Fernet output differs on every encryption of the same value. The fingerprint
    is deterministic, so it can be indexed and compared, and it reveals nothing on its own.

    🔴 KEYED WITH THE ENCRYPTING DATA KEY once the keyring is explicit, salted with
    `SECRET_KEY` (exactly as before) while it is not. It must follow the data key: a
    fingerprint salted with a retired secret lets whoever holds that secret test a stolen
    table against a list of candidate IBANs. The re-encryption pass recomputes every stored
    fingerprint along with the ciphertext.
    """
    normalised = _normalised(value)
    if normalised is None:
        return None
    if not is_explicit():
        return _legacy_fingerprint(normalised)
    return _fingerprint_with(keyring()[0], normalised)


def fingerprints(value: str | None) -> list[str]:
    """Every fingerprint this IBAN may be stored under right now, the current one first.

    ⚠️ ONLY FOR MATCHING, during the minutes between a new key being put first and the
    re-encryption pass rewriting the stored fingerprints: a transfer imported then must
    still be recognised. The legacy form is included for the same window when the key is
    first made explicit. Never used to WRITE a fingerprint.
    """
    normalised = _normalised(value)
    if normalised is None:
        return []
    if not is_explicit():
        return [_legacy_fingerprint(normalised)]
    out = [_fingerprint_with(key, normalised) for key in keyring()]
    if (get_settings().SECRET_KEY or "").strip():
        out.append(_legacy_fingerprint(normalised))
    return out
