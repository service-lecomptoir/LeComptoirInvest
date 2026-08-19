"""Where this product takes its sending configuration from: Alice first, the environment second.

🔴 THE CONFIGURATION COMES FROM ALICE, THE ENVIRONMENT IS ONLY A FALLBACK. That is the
platform's rule, and the three sibling products already apply it with this same module.
Invest was absent from it because it sent nothing: writing it a `.env.prod` by hand would
have brought back exactly the gesture the shared store and the console removed, which is
editing four files every time anything changes.

Alice's NON-EMPTY values are laid over the environment, never the other way round. With
Alice unreachable, sending carries on with whatever the environment holds: an unavailable
console must not stop a fund writing to its investors.

🔴 AND AN EMPTY VALUE REPLACES NOTHING, which is the finest point of the merge. Alice no
longer returns a shared sending address: a scope that entered none gets « ». If that empty
string overwrote the local value, filling the console in halfway would cut off sending for a
product that worked - an outage caused by configuring. It is ignored, and an absence on BOTH
sides makes the send refuse and say so.

⚠️ THE SENDING IDENTITY BELONGS TO THIS PRODUCT, never inherited. The connection is shared
(one relay, one credential, one rotation); the identity is not. A scope writing from another
product's domain sends a message the recipient is right to treat as a phishing attempt.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

#: This product's code in Alice's registry. Written here and nowhere else.
_APP = "invest"
#: Five minutes. Short enough that a change in the console shows up straight away, long
#: enough that a batch of notices does not make one request per letter.
_TTL_SECONDS = 300.0
_cache: dict = {"data": None, "ts": 0.0}


@dataclass(frozen=True)
class EffectiveComm:
    """What sending actually happens with.

    The field names are `Settings`' own, deliberately: the mailer reads one or the other
    without having to know which.
    """

    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_USER: str
    SMTP_PASSWORD: str
    SMTP_FROM_EMAIL: str
    SMTP_FROM_NAME: str
    SMTP_TLS: bool

    @property
    def can_send(self) -> bool:
        """Both halves are required, and that is a decision.

        A server with no sending address does not know who the message is from; an address
        with no server has nobody to hand it to. Answered as one value so a screen can say
        « sending is not set up » before the click rather than after it.
        """
        return bool(self.SMTP_HOST and self.SMTP_FROM_EMAIL)


def _from_env() -> dict:
    settings = get_settings()
    return {
        "SMTP_HOST": settings.SMTP_HOST or "",
        "SMTP_PORT": int(settings.SMTP_PORT or 587),
        "SMTP_USER": settings.SMTP_USER or "",
        "SMTP_PASSWORD": settings.SMTP_PASSWORD or "",
        "SMTP_FROM_EMAIL": settings.SMTP_FROM_EMAIL or "",
        "SMTP_FROM_NAME": settings.SMTP_FROM_NAME or "",
        "SMTP_TLS": bool(getattr(settings, "SMTP_TLS", True)),
    }


async def _fetch_alice() -> dict | None:
    """What Alice says about THIS product, or None when she does not answer.

    ⚠️ `ALICE_INTERNAL_KEY`, NOT `ALICE_API_KEY`. Both keys exist and they run in opposite
    directions: one is what Alice presents when calling this product, the other what this
    product presents when calling Alice. Swapping them gives a 401 that nothing explains.
    """
    settings = get_settings()
    base = getattr(settings, "ALICE_URL", "") or ""
    key = getattr(settings, "ALICE_INTERNAL_KEY", "") or ""
    if not base or not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{base}/api/v1/internal/comm-config",
                params={"app": _APP},
                headers={"X-Internal-Key": key},
            )
        if response.status_code == 200:
            return response.json()
        logger.warning("Alice comm-config answered %s", response.status_code)
    except Exception as exc:  # noqa: BLE001 - Alice unreachable: keep the environment
        logger.debug("Alice comm-config unavailable: %s", exc)
    return None


_FROM_ALICE = {
    "smtp_host": "SMTP_HOST",
    "smtp_user": "SMTP_USER",
    "smtp_password": "SMTP_PASSWORD",
    "smtp_from_email": "SMTP_FROM_EMAIL",
    "smtp_from_name": "SMTP_FROM_NAME",
}


def _merge(env: dict, alice: dict | None) -> dict:
    merged = dict(env)
    if not alice:
        return merged
    for theirs, ours in _FROM_ALICE.items():
        value = alice.get(theirs)
        if value:  # 🔴 empty overwrites nothing: see the module header
            merged[ours] = value
    if alice.get("smtp_port"):
        merged["SMTP_PORT"] = int(alice["smtp_port"])
    if "smtp_tls" in alice:
        merged["SMTP_TLS"] = bool(alice["smtp_tls"])
    return merged


async def get_effective_comm() -> EffectiveComm:
    now = time.monotonic()
    if _cache["data"] is None or (now - _cache["ts"]) > _TTL_SECONDS:
        _cache["data"] = _merge(_from_env(), await _fetch_alice())
        _cache["ts"] = now
    return EffectiveComm(**_cache["data"])


def forget() -> None:
    """Empty the cache. For the tests, and for the day a screen wants to say « I have just
    changed the configuration, read it again »."""
    _cache["data"] = None
    _cache["ts"] = 0.0


__all__ = ["EffectiveComm", "forget", "get_effective_comm"]
