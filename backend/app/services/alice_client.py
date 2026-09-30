"""What this product asks Alice, and nothing more.

🔴 THE DIRECTION MATTERS. `api/v1/internal_admin.py` is what Alice calls HERE, to create
and manage accounts. This module is the other way round: what the fund manager's own
screen asks Alice about *their* subscription. The two never share a key holder and never
share a route prefix, and confusing them would let a fund manager reach the console's
administration contract.

🔴 EVERY CALL IS FAIL-SOFT BY DESIGN, and that is a product decision, not laziness. Alice
being unreachable must never stop a fund from being run: the subscription screen degrades
to "unknown", it does not take the application down with it. The one exception is a
payment action, where a silent failure would be worse than an error: a manager who thinks
they paid and did not is a support case, an error message is a retry.
"""

from __future__ import annotations

import logging
import ssl
from functools import cache
from typing import Any
from uuid import UUID

import certifi
import httpx

from app.config import get_settings
from app.core.i18n import pick

logger = logging.getLogger(__name__)

#: Read calls are short: the screen waits on them. Payment calls get longer, because a
#: Stripe session is created upstream and a timeout there loses a real intent.
_READ_TIMEOUT = 5.0
_ACTION_TIMEOUT = 15.0
#: A lookup waits on a register the console itself asks (the national company search is
#: the slow one): longer than a read, and still short enough for a form being typed.
_LOOKUP_TIMEOUT = 8.0
#: 🔴 A SIGN-UP WAITS LONGER THAN ANY OTHER CALL, because the console does real work before
#: it answers: it asks THIS product whether the address already has an account
#: (`GET /internal/managers`), files the request and sends the confirmation e-mail. On a
#: loaded host that took more than 15 s in the customer recipe of 30 Sept 2026, and the
#: prospect was told « not recorded » of a request the console went on to answer.
_SIGNUP_TIMEOUT = 30.0


@cache
def _tls() -> ssl.SSLContext:
    """The trust store, read ONCE for the life of the process.

    🔴 `httpx.AsyncClient()` without `verify` builds a new SSL context each time, and that
    reads and parses the whole CA bundle SYNCHRONOUSLY, inside the event loop, even for a
    plain `http://` call. Measured in the customer recipe of 30 Sept 2026: 3.5 s per call to
    the console on a loaded machine (0.1 s for the console itself), during which the worker
    answered nobody. One context serves every client; the bundle does not change while the
    process lives. Guard: `tests_unit/test_the_event_loop_is_never_held.py`.
    """
    return ssl.create_default_context(cafile=certifi.where())


def _target() -> tuple[str, dict[str, str]] | None:
    """The console URL and its key, or None when this instance is not driven by Alice.

    ⚠️ AN UNCONFIGURED INSTANCE IS A LEGITIMATE STATE. A local run, or a fund hosted on
    its own, has no console: the subscription screen must then say "no subscription
    managed here", not show an error that suggests a breakdown.
    """
    cfg = get_settings()
    if not cfg.ALICE_URL or not cfg.ALICE_API_KEY:
        return None
    return cfg.ALICE_URL.rstrip("/"), {"X-Internal-Key": cfg.ALICE_API_KEY}


class AliceUnavailable(RuntimeError):
    """Raised only where silence would be misread as success."""


async def _call(
    method: str,
    path: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
    timeout: float = _READ_TIMEOUT,
    strict: bool = False,
) -> Any:
    target = _target()
    if target is None:
        if strict:
            raise AliceUnavailable(
                pick(
                    "Aucune console d'abonnement n'est configurée.",
                    "No subscription console is configured.",
                )
            )
        return None
    base, headers = target
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=_tls()) as client:
            resp = await client.request(
                method, f"{base}{path}", headers=headers, json=json, params=params
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Alice %s %s injoignable : %s", method, path, exc)
        if strict:
            raise AliceUnavailable(
                pick(
                    "Le service d'abonnement est momentanément indisponible.",
                    "The subscription service is temporarily unavailable.",
                )
            )
        return None
    if resp.status_code == 404:
        return None
    if resp.status_code >= 400:
        detail = None
        try:
            detail = resp.json().get("detail")
        except Exception:  # noqa: BLE001
            pass
        logger.warning("Alice %s %s -> %s %s", method, path, resp.status_code, detail)
        if strict:
            raise AliceUnavailable(
                detail
                or pick(
                    "Le service d'abonnement a refusé la demande.",
                    "The subscription service refused the request.",
                )
            )
        return None
    if not resp.content:
        return None
    return resp.json()


def console_configured() -> bool:
    """Whether a console drives this installation AT ALL - a question about CONFIGURATION.

    🔴 IT ANSWERS SOMETHING NO FAILED CALL EVER ANSWERS. « Nobody sells this fund a plan »
    and « the console did not reply » look identical to a caller that only sees `None`, and a
    quota that conflated the two would have gone unlimited for the whole of any outage. The
    guard asks this FIRST, and only then places a call it is allowed to fail on.
    """
    return _target() is not None


async def get_license(user_id: UUID, *, strict: bool = False) -> dict | None:
    """The manager's licence: plan, price, blocking, included features, ceiling.

    ⚠️ `strict` IS FOR CALLERS THAT ENFORCE, not for callers that display. The subscription
    screen wants a soft `None` and shows « unknown »; the quota guard wants the failure,
    because the alternative is granting an allowance nobody checked.
    """
    return await _call("GET", f"/api/v1/internal/license/{user_id}", strict=strict)


async def payment_config() -> dict:
    """Payment methods this product may offer: card (Stripe) and/or transfer (bank details).

    ⚠️ THE SCOPE IS `invest`, NOT `immo`. Each product carries its own bank details and its
    own Stripe account in the console; reading a sister product's would print another
    company's IBAN on our screen.
    """
    data = await _call(
        "GET", "/api/v1/internal/payment-config", params={"app": "invest"}
    )
    return data or {"stripe_enabled": False, "rib_enabled": False}


async def comm_config() -> dict | None:
    """The effective e-mail configuration for THIS product, or None when Alice is silent.

    🔴 IT GOES THROUGH `_call`, AND THAT IS THE WHOLE POINT OF PUTTING IT HERE. The first
    version of the caller built its own request and presented `ALICE_INTERNAL_KEY` - the
    INBOUND key, the one Alice shows when calling this product. Alice answered 401, the
    caller fell back on the environment, and a manager who had just filled the console in
    correctly kept reading << sending is not configured >>. Nothing failed loudly.

    One house knows the console's address and which of the two keys opens it.
    """
    return await _call("GET", "/api/v1/internal/comm-config", params={"app": "invest"})


async def billing(
    method: str,
    action: str,
    user_id: UUID,
    *,
    json: dict | None = None,
    strict: bool = True,
) -> Any:
    """One of Alice's `/internal/billing/{action}/{user_id}` operations."""
    return await _call(
        method,
        f"/api/v1/internal/billing/{action}/{user_id}",
        json=json,
        timeout=_ACTION_TIMEOUT,
        strict=strict,
    )


async def lookup(path: str, params: dict[str, str], fallback: Any) -> Any:
    """One of Alice's common lookups (`countries`, `company`, `address`, `town`).

    🔴 THE REGISTERS ARE READ BY THE CONSOLE, NEVER HERE (the manager, 28 Sept 2026:
    everything common lives in Alice, reachable by API). This product only relays, with
    the same outbound key as every other call in this file.

    ⚠️ THE FALLBACK IS RETURNED FOR ANY ANSWER OF THE WRONG SHAPE, not only for silence: a
    list where a dict was expected, or a body that is not JSON, must degrade the form to
    typing by hand, never turn into a 500 on a sign-up screen.
    """
    try:
        data = await _call(
            "GET",
            f"/api/v1/internal/lookups/{path}",
            params=params,
            timeout=_LOOKUP_TIMEOUT,
        )
    except ValueError:
        return fallback
    return data if isinstance(data, type(fallback)) else fallback


#: 🔴 WRITTEN OUT IN FULL, NOT ASSEMBLED. These paths are a contract with ANOTHER
#: repository, the same one every sibling product calls; the product code travels as a
#: parameter the console REQUIRES (it used to default to Immo and published Immo's prices).
_PLANS_PATH = "/api/v1/internal/plans"
_LEADS_PATH = "/api/v1/internal/leads"
PRODUCT = "invest"


class SignupRefused(ValueError):
    """The console refused a sign-up and said why, in one sentence the person can act on."""


class SignupNotAnswered(RuntimeError):
    """The sign-up LEFT, and the console did not answer in time: it may well be filed.

    ⚠️ NOT A REFUSAL AND NOT A LOSS. The console may have filed it and sent the
    confirmation e-mail; « not recorded » would then be a lie, and the prospect who tries
    again is told the account already exists.
    """


async def public_plans() -> list[dict]:
    """The plans the console sells for THIS product, as its catalogue lists them.

    ⚠️ FAIL-SOFT: an empty list when the console is silent, unconfigured or answers
    something that is not a list. The pricing page then says so and still offers the form.
    """
    try:
        data = await _call("GET", _PLANS_PATH, params={"product": PRODUCT})
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def _lead_unavailable() -> str:
    return pick(
        "Nous n'avons pas pu enregistrer votre demande. Réessayez dans un instant, ou "
        "écrivez-nous à contact@lecomptoir.services.",
        "We could not record your request. Try again in a moment, or write to us at "
        "contact@lecomptoir.services.",
    )


async def file_lead(payload: dict) -> dict:
    """Hand a sign-up to the console and return what it answered.

    🔴 NEVER FAIL-SOFT, and that is the one difference with every read above: a request
    swallowed in silence sends the prospect waiting for an answer that will never come.
    Raises `SignupRefused` with the console's sentence on a 422 (« Indiquez votre prénom
    et votre nom. »), `SignupNotAnswered` when the request left but no answer came in
    time, `AliceUnavailable` on any other failure.
    """
    target = _target()
    if target is None:
        raise AliceUnavailable(_lead_unavailable())
    base, headers = target
    try:
        async with httpx.AsyncClient(timeout=_SIGNUP_TIMEOUT, verify=_tls()) as client:
            resp = await client.post(
                f"{base}{_LEADS_PATH}", headers=headers, json=payload
            )
    except (httpx.ReadTimeout, httpx.WriteTimeout):
        # The request reached the console (or was being written to it): only its answer
        # is missing. A connection refused or a connect timeout never left, and stays below.
        logger.warning("Alice POST %s: sent, no answer in time", _LEADS_PATH)
        raise SignupNotAnswered() from None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Alice POST %s injoignable : %s", _LEADS_PATH, exc)
        raise AliceUnavailable(_lead_unavailable()) from None
    if resp.status_code >= 400:
        detail = None
        try:
            detail = resp.json().get("detail")
        except Exception:  # noqa: BLE001
            pass
        if resp.status_code == 422 and isinstance(detail, str) and detail.strip():
            raise SignupRefused(detail.strip())
        logger.warning("Alice POST %s -> %s", _LEADS_PATH, resp.status_code)
        raise AliceUnavailable(_lead_unavailable())
    try:
        said = resp.json() if resp.content else {}
    except ValueError:
        said = {}
    return said if isinstance(said, dict) else {}


_EMAIL_THEMES_PATH = "/api/v1/internal/email-themes"


async def email_themes(etag: str | None) -> tuple[int, Any, str | None] | None:
    """The console's catalogue of e-mail looks: `(status, body, etag)`, or None when silent.

    ⚠️ ITS OWN REQUEST RATHER THAN `_call`, because the answer's HEADERS matter: the console
    tags its catalogue, and a copy revalidated with `If-None-Match` comes back as a bare 304
    while nothing changed. `_call` would read that empty answer as « nothing to say ».

    `(304, None, etag)` means « keep your copy »; `(200, body, etag)` carries a new one; None
    covers an unconfigured console, an unreachable one and any refusal, and the caller keeps
    whatever copy it has. The key is the OUTBOUND one, as for every call in this file.
    """
    target = _target()
    if target is None:
        return None
    base, headers = target
    if etag:
        headers = {**headers, "If-None-Match": etag}
    try:
        async with httpx.AsyncClient(timeout=_READ_TIMEOUT, verify=_tls()) as client:
            resp = await client.get(
                f"{base}{_EMAIL_THEMES_PATH}", headers=headers, params={"app": PRODUCT}
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Alice GET %s unreachable: %s", _EMAIL_THEMES_PATH, exc)
        return None
    if resp.status_code == 304:
        return 304, None, resp.headers.get("etag") or etag
    if resp.status_code != 200:
        logger.warning("Alice GET %s -> %s", _EMAIL_THEMES_PATH, resp.status_code)
        return None
    try:
        body = resp.json()
    except ValueError:
        return None
    return 200, body, resp.headers.get("etag")


async def invoices(user_id: UUID) -> list[dict]:
    data = await _call("GET", f"/api/v1/internal/invoices/{user_id}")
    return data if isinstance(data, list) else []


async def invoice_pdf(user_id: UUID, invoice_id: str) -> tuple[bytes, str] | None:
    """The PDF bytes of one subscription invoice, and the filename Alice named it."""
    target = _target()
    if target is None:
        return None
    base, headers = target
    try:
        async with httpx.AsyncClient(timeout=_ACTION_TIMEOUT, verify=_tls()) as client:
            resp = await client.get(
                f"{base}/api/v1/internal/invoices/{user_id}/{invoice_id}/pdf",
                headers=headers,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Alice invoice pdf injoignable : %s", exc)
        return None
    if resp.status_code != 200:
        return None
    return resp.content, resp.headers.get(
        "content-disposition", 'attachment; filename="FACTURE.pdf"'
    )
