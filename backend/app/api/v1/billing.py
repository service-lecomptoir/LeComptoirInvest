"""The fund manager's own subscription: what they pay for this product, and how they pay it.

🔴 THIS FILE IS NOT CALLED `subscription.py`, AND THAT IS DELIBERATE. In this product a
« subscription » is an investor's commitment to a fund: it is the domain's word, it is
taken, and `api/v1/subscriptions.py` already carries it. Naming the software subscription
« subscription » would have put two unrelated notions under one word, in a domain where the
confusion is read in euros. Here, paying for the product is called « billing ».

🔴 NO AMOUNT IS DECIDED HERE. The plan, the price, the blocking and the invoices belong to
the console (Alice): this module is a relay that adds the caller's identity and nothing
else. Writing a price here would make it a second truth, which is exactly the class of
defect this repository pays for elsewhere.

⚠️ READING DEGRADES, PAYING DOES NOT. If the console is unreachable the screen shows
« unknown » and the fund keeps running. But a payment action that fails silently leaves a
manager convinced they have paid: those raise an error.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.api.deps import current_manager
from app.models.user import User
from app.services import alice_client
from app.services.alice_client import AliceUnavailable

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["billing"])


class SubscriptionInfo(BaseModel):
    """What the subscription screen shows at the top.

    ⚠️ `plan_name is None` DOES NOT MEAN « FREE ». It means « we do not know »: either no
    console drives this instance, or it did not answer. A screen that turned absence into
    « free plan » would announce an entitlement nobody granted.
    """

    #: False when no console drives this instance: the screen says so, rather than showing
    #: an empty subscription that reads like a breakdown.
    managed: bool
    plan_name: str | None = None
    monthly_price: float | None = None
    is_blocked: bool = False
    features: list[str] | None = None
    access_until: str | None = None
    #: How many funds the plan includes, when it sets a limit at all.
    fund_limit: int | None = None


def _as_info(license_: dict | None) -> SubscriptionInfo:
    if not license_:
        return SubscriptionInfo(managed=False)
    return SubscriptionInfo(
        managed=True,
        plan_name=license_.get("plan_name"),
        monthly_price=license_.get("monthly_price"),
        is_blocked=bool(license_.get("is_blocked")),
        features=license_.get("features"),
        access_until=license_.get("access_until"),
        # Alice names this limit `property_limit` for every product: it is the
        # cross-product contract, read as it stands and renamed for OUR screens only.
        # Renaming it at the source would break the three sister products.
        fund_limit=license_.get("property_limit"),
    )


@router.get("", response_model=SubscriptionInfo, summary="Mon abonnement")
async def my_subscription(user: User = Depends(current_manager)) -> SubscriptionInfo:
    return _as_info(await alice_client.get_license(user.id))


@router.get("/payment-methods", summary="Moyens de paiement proposés")
async def payment_methods(_: User = Depends(current_manager)) -> dict:
    """What this product can actually collect: card/SEPA through Stripe, and/or transfer.

    ⚠️ BOTH CAN BE CLOSED AT ONCE, and the screen must then say so instead of showing two
    buttons that lead nowhere.
    """
    cfg = await alice_client.payment_config()
    return {
        "card_enabled": bool(cfg.get("stripe_enabled")),
        "transfer_enabled": bool(cfg.get("rib_enabled")),
        "currency": cfg.get("stripe_currency") or "eur",
        "transfer": {
            "holder": cfg.get("rib_holder"),
            "iban": cfg.get("rib_iban"),
            "bic": cfg.get("rib_bic"),
            "bank": cfg.get("rib_bank"),
            "instructions": cfg.get("rib_instructions"),
        }
        if cfg.get("rib_enabled")
        else None,
    }


@router.get("/status", summary="État de l'abonnement payant")
async def billing_status(user: User = Depends(current_manager)) -> dict:
    """The Stripe subscription in force, if there is one. Degrades softly."""
    data = await alice_client.billing("GET", "status", user.id, strict=False)
    return data or {"stripe_enabled": False, "has_subscription": False}


@router.get("/plans", summary="Offres auxquelles souscrire")
async def available_plans(user: User = Depends(current_manager)) -> list:
    """The sellable « fund » plans, and only those.

    ⚠️ The console does the per-product filtering: asking for the list without saying who
    we are would surface the sister products' offers on this screen.
    """
    data = await alice_client.billing("GET", "available-plans", user.id, strict=False)
    return data if isinstance(data, list) else []


class _PlanIn(BaseModel):
    plan_id: str | None = None


def _unavailable(exc: AliceUnavailable) -> HTTPException:
    # 503 rather than 500: the request was valid, it is the downstream that is missing.
    # The message is the one the user will read, never a bare « Erreur ».
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


@router.post("/checkout", summary="Payer par carte ou prélèvement SEPA")
async def checkout(
    body: _PlanIn | None = None, user: User = Depends(current_manager)
) -> dict:
    """Opens a payment session and returns the address where the manager completes it."""
    payload: dict = {"currency": "eur"}
    if body and body.plan_id:
        payload["plan_id"] = body.plan_id
    try:
        return (
            await alice_client.billing("POST", "checkout", user.id, json=payload) or {}
        )
    except AliceUnavailable as exc:
        raise _unavailable(exc)


@router.post("/portal", summary="Gérer son moyen de paiement")
async def portal(user: User = Depends(current_manager)) -> dict:
    """The portal where a card is changed, receipts read, and the subscription stopped."""
    try:
        return await alice_client.billing("POST", "portal", user.id) or {}
    except AliceUnavailable as exc:
        raise _unavailable(exc)


@router.post("/declare-transfer", summary="Déclarer un paiement par virement")
async def declare_transfer(user: User = Depends(current_manager)) -> dict:
    """The manager reports having sent the transfer: the console waits and reconciles.

    ⚠️ THIS DECLARATION IS NOT A PAYMENT and unblocks nothing on its own. It is an
    announcement, matched afterwards by the console against the actual bank movement.
    """
    try:
        return await alice_client.billing("POST", "declare-transfer", user.id) or {}
    except AliceUnavailable as exc:
        raise _unavailable(exc)


@router.post("/cancel-transfer", summary="Annuler sa déclaration de virement")
async def cancel_transfer(user: User = Depends(current_manager)) -> dict:
    try:
        return await alice_client.billing("POST", "cancel-transfer", user.id) or {}
    except AliceUnavailable as exc:
        raise _unavailable(exc)


@router.post("/change-plan", summary="Changer d'offre")
async def change_plan(body: _PlanIn, user: User = Depends(current_manager)) -> dict:
    if not body.plan_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Préciser l'offre choisie.")
    try:
        return (
            await alice_client.billing(
                "POST",
                "change-plan",
                user.id,
                json={"plan_id": body.plan_id, "currency": "eur"},
            )
            or {}
        )
    except AliceUnavailable as exc:
        raise _unavailable(exc)


@router.post("/change-plan-preview", summary="Estimer le coût d'un changement d'offre")
async def change_plan_preview(
    body: _PlanIn, user: User = Depends(current_manager)
) -> dict:
    """The prorated amount, before committing. Degrades softly: a missing estimate beats a
    plan-change screen nobody can open."""
    if not body.plan_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Préciser l'offre choisie.")
    data = await alice_client.billing(
        "POST",
        "change-plan-preview",
        user.id,
        json={"plan_id": body.plan_id, "currency": "eur"},
        strict=False,
    )
    return data or {}


@router.get("/invoices", summary="Mes factures d'abonnement")
async def invoices(user: User = Depends(current_manager)) -> list:
    return await alice_client.invoices(user.id)


@router.get("/invoices/{invoice_id}/pdf", summary="Le PDF d'une facture")
async def invoice_pdf(
    invoice_id: str, user: User = Depends(current_manager)
) -> Response:
    """⚠️ THE MANAGER'S ID IS THE SESSION'S, never a parameter. The console files invoices
    by manager: accepting an id from the request would let another fund's invoice be read
    by changing one digit in the address."""
    found = await alice_client.invoice_pdf(user.id, invoice_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Facture introuvable.")
    content, disposition = found
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )


@router.get("/payments", summary="Historique des paiements")
async def payments(user: User = Depends(current_manager)) -> list:
    data = await alice_client.billing("GET", "payments", user.id, strict=False)
    return data if isinstance(data, list) else []
