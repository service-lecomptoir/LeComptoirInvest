"""Two-factor authentication: TOTP codes (RFC 6238) and single-use backup codes.

🔴 ONE PATTERN, WRITTEN ONCE (the owner, 2 Nov 2026). This file is the same, byte for byte,
in every product of Le Comptoir that has accounts. It holds the arithmetic only: no model, no
route, no setting. Each product writes its own glue around it (where the secret is stored,
which token is issued, which audit row is written), and a test of each product checks the
fingerprint of this file, so that a copy changed in one product fails until all are changed.

What it guarantees:
- a 6-digit code every 30 seconds, HMAC-SHA1, the defaults every authenticator app reads
  (Google Authenticator, Microsoft Authenticator, 1Password, Aegis...);
- a window of one period on each side (a phone clock a few seconds off still works);
- NO REPLAY: a code is accepted only for a time step strictly after the last accepted one,
  which the caller stores and passes back (`last_step`);
- ten backup codes, kept as keyed fingerprints (never in clear), each one usable once.

The secret itself is never stored here: the caller encrypts it with the product's own
mechanism for secrets at rest before writing it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

PERIOD_SECONDS = 30
DIGITS = 6
# One period before and one after the current one are accepted.
WINDOW_STEPS = 1
SECRET_BYTES = 20
BACKUP_CODE_COUNT = 10
BACKUP_CODE_LENGTH = 10
# The intermediate token between the password and the code: short-lived, single purpose.
PENDING_TOKEN_MINUTES = 5
PENDING_TOKEN_TYPE = "two_factor_pending"

# No 0/o, 1/l/i: a code copied from paper must not be ambiguous.
_BACKUP_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


# ── TOTP ─────────────────────────────────────────────────────────────────────


def generate_secret() -> str:
    """A fresh random secret, base32 without padding (what the apps expect)."""
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode("ascii").rstrip("=")


def _secret_bytes(secret: str) -> bytes:
    cleaned = secret.replace(" ", "").upper()
    return base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))


def hotp(key: bytes, counter: int, digits: int = DIGITS) -> str:
    """RFC 4226: the code of one counter value."""
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**digits)).zfill(digits)


def current_step(now: float | None = None) -> int:
    """The RFC 6238 time step of `now` (seconds since the epoch, the current time if None)."""
    return int((time.time() if now is None else now) // PERIOD_SECONDS)


def code_at(secret: str, step: int) -> str:
    """The code an app shows during time step `step`."""
    return hotp(_secret_bytes(secret), step)


def normalize_code(code: str | None) -> str:
    """The digits of a typed code: spaces and dashes are dropped (« 123 456 » is accepted)."""
    return "".join(ch for ch in (code or "") if not ch.isspace() and ch != "-")


def match_step(
    secret: str, code: str | None, last_step: int | None, now: float | None = None
) -> int | None:
    """The time step a typed code belongs to, or None when it is wrong or replayed.

    Accepted: the current step and one on each side, and only a step STRICTLY AFTER
    `last_step` (the last one accepted for this account). The caller stores the returned
    step as the new `last_step`, so the same code, or an older one, never works twice.
    """
    typed = normalize_code(code)
    if len(typed) != DIGITS or not typed.isdigit():
        return None
    step = current_step(now)
    for candidate in range(step - WINDOW_STEPS, step + WINDOW_STEPS + 1):
        if last_step is not None and candidate <= last_step:
            continue
        if hmac.compare_digest(code_at(secret, candidate), typed):
            return candidate
    return None


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    """The `otpauth://` address an app reads from the QR code."""
    label = quote(f"{issuer}:{account}", safe="")
    params = urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": DIGITS,
            "period": PERIOD_SECONDS,
        },
        quote_via=quote,
    )
    return f"otpauth://totp/{label}?{params}"


def qr_code_svg(uri: str) -> str:
    """The QR code of `uri` as an SVG data URI, drawn on the server (no image service)."""
    import segno

    return segno.make(uri, error="m", micro=False).svg_data_uri(scale=5, border=2)


# ── Backup codes ─────────────────────────────────────────────────────────────


def generate_backup_codes(count: int = BACKUP_CODE_COUNT) -> list[str]:
    """`count` fresh codes, shown once, written « abcde-23456 » (about 49 bits each)."""
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(_BACKUP_ALPHABET) for _ in range(BACKUP_CODE_LENGTH))
        half = BACKUP_CODE_LENGTH // 2
        codes.append(f"{raw[:half]}-{raw[half:]}")
    return codes


def normalize_backup_code(code: str | None) -> str:
    """Lowercase, without spaces or dashes: « ABCDE 23456 » is the same code."""
    return "".join(ch for ch in (code or "").lower() if ch.isalnum())


def hash_backup_code(code: str, pepper: str) -> str:
    """The keyed fingerprint stored for one backup code (HMAC-SHA256 with `pepper`)."""
    return hmac.new(
        pepper.encode("utf-8"), normalize_backup_code(code).encode("utf-8"), hashlib.sha256
    ).hexdigest()


def hash_backup_codes(codes: list[str], pepper: str) -> list[str]:
    return [hash_backup_code(code, pepper) for code in codes]


def consume_backup_code(
    stored: list[str] | None, code: str | None, peppers: list[str]
) -> list[str] | None:
    """The fingerprints left once `code` is used, or None when it matches none of them.

    `peppers` lists every key the fingerprints may have been made with (the current one
    first, then the keys kept for a rotation), so a rotation does not void the codes.
    """
    typed = normalize_backup_code(code)
    if len(typed) != BACKUP_CODE_LENGTH or not stored:
        return None
    candidates = {hash_backup_code(typed, pepper) for pepper in peppers if pepper}
    for index, fingerprint in enumerate(stored):
        if any(hmac.compare_digest(fingerprint, candidate) for candidate in candidates):
            return stored[:index] + stored[index + 1 :]
    return None
