"""The platform's contact address, read in Alice (Communication screen, tab Alice).

🔴 IT WAS WRITTEN HERE, IN FIVE SENTENCES AND ON THE PUBLIC PAGES. The manager asked, on
3 Oct 2026, for one place to change it, with a view of it: moving to lecomptoir-services.com
meant a deployment of every product for a mailbox. Alice serves it
on the door this product already calls for its e-mail settings (`/internal/comm-config`).

⚠️ THE LAST ADDRESS KNOWN IS KEPT. The sentences that name it are the ones said when
something failed, Alice included: an address learnt five minutes earlier is still the right
one. Nothing learnt yet (a fresh start with Alice down), or nothing entered in the console:
the sentence says no address rather than an invented one.

⚠️ IN THE READER'S LANGUAGE: a sentence is written with `pick`, its ending too.
"""

from __future__ import annotations

import logging
import time

from app.core.i18n import pick

logger = logging.getLogger(__name__)

_PATH = "/api/v1/internal/comm-config"
#: How long an answer is reused; a failed call is retried sooner.
_TTL_SECONDS = 300.0
_RETRY_SECONDS = 30.0

#: Where a sentence names the address: « …, ou écrivez-nous à X. » and « Écrivez-nous à X. »
OR_WRITE = "{or_write}"
WRITE = "{write}"

_known: dict = {"value": "", "next": 0.0}


async def _fetch() -> str | None:
    # Imported here: `alice_client` writes its sentences with the markers above.
    from app.services import alice_client

    try:
        data = await alice_client._call(
            "GET", _PATH, params={"app": alice_client.PRODUCT}
        )
    except Exception as exc:  # noqa: BLE001 : Alice unavailable, the last address known stays
        logger.debug("Contact address (Alice) unavailable: %s", exc)
        return None
    if isinstance(data, dict):
        return str(data.get("contact_email") or "").strip()
    return None


async def contact_email() -> str:
    """The contact address the console holds, or "" when none is known."""
    now = time.monotonic()
    if now >= _known["next"]:
        fetched = await _fetch()
        if fetched is not None:
            _known["value"] = fetched
        _known["next"] = now + (_TTL_SECONDS if fetched is not None else _RETRY_SECONDS)
    return _known["value"]


async def said(sentence: str) -> str:
    """The sentence with the address where it names it, or without it when none is known."""
    c = await contact_email()
    or_write = (
        pick(f", ou écrivez-nous à {c}.", f", or write to us at {c}.") if c else "."
    )
    write = pick(f"Écrivez-nous à {c}.", f"Write to us at {c}.") if c else ""
    return sentence.replace(OR_WRITE, or_write).replace(WRITE, write).strip()
