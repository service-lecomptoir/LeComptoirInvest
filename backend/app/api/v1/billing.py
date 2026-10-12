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
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import current_manager
from app.api.v1 import terms as terms_api
from app.core import audit
from app.database import AsyncSessionLocal
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services import alice_client
from app.services.alice_client import AliceUnavailable
from app.core.i18n import pick

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
    #: How many INVESTORS the plan includes, when it sets a limit at all: the billed unit
    #: of this product (Alice's registry), never a number of funds or vehicles.
    investor_limit: int | None = None


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
        # 🔴 THE CEILING, UNDER THE PLATFORM'S GENERIC NAME. It counts properties at
        # Immo, homes at Sejour, investors here — and `managed_limit` is what all five
        # repositories now speak. The old `property_limit` was dropped once every reader
        # had been deployed on the new one; keeping a fallback nobody exercises is dead
        # code that reads like a safety net.
        #
        # ⚠️ None IS A VALUE, NOT AN ABSENCE: « unlimited » is null on the wire.
        investor_limit=license_.get("managed_limit"),
    )


@router.get(
    "", response_model=SubscriptionInfo, summary="The manager's own subscription"
)
async def my_subscription(user: User = Depends(current_manager)) -> SubscriptionInfo:
    return _as_info(await alice_client.get_license(user.id))


@router.get("/payment-methods", summary="Payment methods on offer")
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


@router.get("/status", summary="State of the paid subscription")
async def billing_status(user: User = Depends(current_manager)) -> dict:
    """The Stripe subscription in force, if there is one. Degrades softly."""
    data = await alice_client.billing("GET", "status", user.id, strict=False)
    return data or {"stripe_enabled": False, "has_subscription": False}


@router.get("/plans", summary="Plans available to subscribe to")
async def available_plans(user: User = Depends(current_manager)) -> list:
    """The sellable « fund » plans, and only those.

    ⚠️ The console does the per-product filtering: asking for the list without saying who
    we are would surface the sister products' offers on this screen.
    """
    data = await alice_client.billing("GET", "available-plans", user.id, strict=False)
    return data if isinstance(data, list) else []


class _PlanIn(BaseModel):
    plan_id: str | None = None
    #: The version of the terms of sale the screen showed and the subscriber ticked, when
    #: Alice publishes any. See `_sale_accepted`.
    cgv: str | None = None
    language: str = "fr"


async def _sale_accepted(user: User, request: Request, body: _PlanIn) -> None:
    """Choosing a plan is subscribing: the terms of sale are accepted there and then.

    🔴 THE MANAGER, 2 OCT 2026: the subscriber accepts the terms of sale at subscription,
    a plan change included. Alice's plan change carries no terms, so the acceptance is
    recorded first (`method="plan"`), and a refusal (409, a version that changed while the
    page was open) stops the change before it reaches the payment.

    ⚠️ THE SERVER CHECKS, NOT ONLY THE BOX: a change sent without the tick while Alice
    publishes terms of sale is refused. Only the subscriber is asked; another account is
    not the one Alice bills, and her own refusal answers it.
    """
    if not user.holds_the_licence:
        return
    if body.cgv:
        await terms_api.record_acceptance(
            user,
            request,
            kind=terms_api.SALE,
            version=body.cgv,
            language=body.language,
            method="plan",
        )
        return
    owed = await alice_client.terms_status(
        user.id, audience=terms_api.AUDIENCES[user.role], subscriber=True
    )
    if owed is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            pick(
                "Les conditions générales de vente ne peuvent pas être chargées pour le "
                "moment : réessayez dans quelques minutes.",
                "The terms of sale cannot be loaded at the moment: try again in a few "
                "minutes.",
            ),
        )
    sale = owed.get("cgv")
    if isinstance(sale, dict) and sale.get("anything_to_accept"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            pick(
                "Acceptez les conditions générales de vente pour changer de formule.",
                "Accept the terms of sale to change plan.",
            ),
        )


def _unavailable(exc: AliceUnavailable) -> HTTPException:
    # 503 rather than 500: the request was valid, it is the downstream that is missing.
    # The message is the one the user will read, never a bare « Erreur ».
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


@router.post("/checkout", summary="Pay by card or SEPA direct debit")
async def checkout(
    request: Request,
    body: _PlanIn | None = None,
    user: User = Depends(current_manager),
) -> dict:
    """Opens a payment session and returns the address where the manager completes it.

    A plan named here is a subscription to it: its terms of sale are accepted first.
    """
    payload: dict = {"currency": "eur"}
    if body and body.plan_id:
        _subscriber_only(user)
        await _sale_accepted(user, request, body)
        await _journal(user, "subscription.checkout_started", {"plan_id": body.plan_id})
        payload["plan_id"] = body.plan_id
    try:
        return (
            await alice_client.billing("POST", "checkout", user.id, json=payload) or {}
        )
    except AliceUnavailable as exc:
        raise _unavailable(exc)


@router.post("/portal", summary="Manage the payment method")
async def portal(user: User = Depends(current_manager)) -> dict:
    """The portal where a card is changed, receipts read, and the subscription stopped."""
    try:
        return await alice_client.billing("POST", "portal", user.id) or {}
    except AliceUnavailable as exc:
        raise _unavailable(exc)


@router.post("/declare-transfer", summary="Declare a payment made by transfer")
async def declare_transfer(user: User = Depends(current_manager)) -> dict:
    """The manager reports having sent the transfer: the console waits and reconciles.

    ⚠️ THIS DECLARATION IS NOT A PAYMENT and unblocks nothing on its own. It is an
    announcement, matched afterwards by the console against the actual bank movement.
    """
    try:
        return await alice_client.billing("POST", "declare-transfer", user.id) or {}
    except AliceUnavailable as exc:
        raise _unavailable(exc)


@router.post("/cancel-transfer", summary="Cancel a declared transfer")
async def cancel_transfer(user: User = Depends(current_manager)) -> dict:
    try:
        return await alice_client.billing("POST", "cancel-transfer", user.id) or {}
    except AliceUnavailable as exc:
        raise _unavailable(exc)


@router.post("/change-plan", summary="Change plan")
async def change_plan(
    body: _PlanIn, request: Request, user: User = Depends(current_manager)
) -> dict:
    """Move the subscription to another plan, through Alice (proration by Stripe).

    🔴 THE SUBSCRIBER ALONE (the owner, 11 Oct 2026), the terms of sale first (a plan is a
    sale), and Alice's refusals relayed with her sentence: a plan whose cap is under what
    the account holds, a bespoke or beta plan left by a click. Journaled once done."""
    _subscriber_only(user)
    if not body.plan_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            pick("Préciser l'offre choisie.", "Say which plan was chosen."),
        )
    await _sale_accepted(user, request, body)
    try:
        answer = (
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
    await _journal(
        user,
        "subscription.plan_changed",
        {
            "plan_id": body.plan_id,
            "from": answer.get("previous_plan_name"),
            "to": answer.get("plan_name"),
        },
    )
    return answer


@router.post("/change-plan-preview", summary="Estimate the cost of changing plan")
async def change_plan_preview(
    body: _PlanIn, user: User = Depends(current_manager)
) -> dict:
    """Alice's preview of a change, before the subscriber confirms: the card (price before
    tax, VAT, total), the prorated amount (`proration_amount`), how and from when it
    applies, and a refusal when there is one. Degrades softly: a missing estimate beats a
    plan-change screen nobody can open."""
    _subscriber_only(user)
    if not body.plan_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            pick("Préciser l'offre choisie.", "Say which plan was chosen."),
        )
    data = await alice_client.billing(
        "POST",
        "change-plan-preview",
        user.id,
        json={"plan_id": body.plan_id, "currency": "eur"},
        strict=False,
    )
    return data or {}


@router.get("/invoices", summary="The manager's own invoices")
async def invoices(user: User = Depends(current_manager)) -> list:
    return await alice_client.invoices(user.id)


@router.get("/invoices/{invoice_id}/pdf", summary="An invoice as a PDF")
async def invoice_pdf(
    invoice_id: str, user: User = Depends(current_manager)
) -> Response:
    """⚠️ THE MANAGER'S ID IS THE SESSION'S, never a parameter. The console files invoices
    by manager: accepting an id from the request would let another fund's invoice be read
    by changing one digit in the address."""
    found = await alice_client.invoice_pdf(user.id, invoice_id)
    if found is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            pick("Facture introuvable.", "Invoice not found."),
        )
    content, disposition = found
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )


@router.get("/payments", summary="Payment history")
async def payments(user: User = Depends(current_manager)) -> list:
    data = await alice_client.billing("GET", "payments", user.id, strict=False)
    return data if isinstance(data, list) else []


# ── Changing plan, from Alice's offer (the owner, 11 Oct 2026) ────────────────────────────
# The owner asked for a plan change as on Le Comptoir Immo, in every product.
# Every product draws the same page from ONE answer of Alice
# (`/internal/billing/plan-offer`, her `services/plan_change.py`): the plans, their price
# with the VAT of the subscriber's territory, a cap under the current use refused, a
# bespoke or beta plan asked of the team. This relay adds who asks, and nothing else.


def _holds(user: User) -> bool:
    """The subscriber: the account that holds the licence and pays."""
    return bool(user.holds_the_licence)


def _subscriber_only(user: User) -> None:
    if not _holds(user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            pick(
                "Seul le compte titulaire de l'abonnement change de formule.",
                "Only the account that holds the subscription changes plan.",
            ),
        )


async def _journal(user: User, action: str, details: dict) -> None:
    """🔴 A PLAN CHANGE IS AUDITED HERE TOO (« tout produit a son journal d'audit »): no row
    of this product changes, so the listeners write nothing. Its own session, so a line is
    written whatever the request's own unit of work does; never blocking."""
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                AuditLog(
                    id=uuid.uuid4(),
                    created_at=datetime.now(UTC),
                    user_id=str(user.id),
                    user_email=user.email,
                    action=action,
                    entity_type="subscription",
                    entity_id=str(user.id),
                    details=details,
                    ip_address=audit.current_actor().get("ip"),
                )
            )
            await session.commit()
    except Exception:  # noqa: BLE001 - the journal never undoes a change already made
        logger.warning("[audit] could not record %s", action, exc_info=True)


@router.get("/offer", summary="The plans this account may take, from Alice")
async def plan_offer(user: User = Depends(current_manager)) -> dict:
    """Alice's offer for this licence, and whether THIS account may act on it."""
    try:
        data = await alice_client.billing("GET", "plan-offer", user.id)
    except AliceUnavailable as exc:
        raise _unavailable(exc)
    if not isinstance(data, dict):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            pick(
                "Aucune licence Le Comptoir Invest n'est rattachée à ce compte.",
                "No Le Comptoir Invest licence is attached to this account.",
            ),
        )
    return {**data, "can_change": _holds(user)}


class _ChangeRequestIn(BaseModel):
    plan_id: str | None = Field(default=None, max_length=64)
    message: str | None = Field(default=None, max_length=2000)


@router.post(
    "/change-request", status_code=201, summary="Ask the team for a change of plan"
)
async def change_request(
    body: _ChangeRequestIn, user: User = Depends(current_manager)
) -> dict:
    """« Demander un changement »: for a plan the team hands out (bespoke, beta tester, on
    quotation), a free plan, or wherever online payment is off. Stored in Alice's
    « Demandes » and announced to the team."""
    _subscriber_only(user)
    try:
        answer = await alice_client.billing(
            "POST",
            "change-request",
            user.id,
            json={
                "plan_id": body.plan_id,
                "message": (body.message or "").strip() or None,
                "full_name": user.account_name or user.email,
                "email": user.email,
            },
        )
    except AliceUnavailable as exc:
        raise _unavailable(exc)
    await _journal(user, "subscription.change_requested", {"plan_id": body.plan_id})
    return answer or {"status": "received"}
