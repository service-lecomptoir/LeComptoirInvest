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
from typing import Any
from uuid import UUID

import httpx

from app.config import get_settings
from app.core.i18n import pick

logger = logging.getLogger(__name__)

#: Read calls are short: the screen waits on them. Payment calls get longer, because a
#: Stripe session is created upstream and a timeout there loses a real intent.
_READ_TIMEOUT = 5.0
_ACTION_TIMEOUT = 15.0


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
        async with httpx.AsyncClient(timeout=timeout) as client:
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


async def get_license(user_id: UUID) -> dict | None:
    """The manager's licence: plan, price, blocking, included features."""
    return await _call("GET", f"/api/v1/internal/license/{user_id}")


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
        async with httpx.AsyncClient(timeout=_ACTION_TIMEOUT) as client:
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
