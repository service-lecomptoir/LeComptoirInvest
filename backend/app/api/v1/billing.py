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
from app.core.firm_scope import firm_of
from app.services import alice_client, licence_state
from app.services.alice_client import AliceRefused, AliceUnavailable
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
    #: 🔴 ALICE DID NOT ANSWER (8 Nov 2026): an outage, or an answer other than 200/404.
    #: The screen says the information is unavailable, never « no plan ».
    unavailable: bool = False
    #: This account holds and pays the licence (`User.holds_the_licence`): the banners
    #: speak to it alone.
    is_holder: bool = False
    #: Blocked for an unpaid invoice (or by hand), not by a termination run out: the
    #: subscriber may come in, and reaches « Mon abonnement » alone.
    suspended: bool = False
    #: Blocked because the termination has run out (the owner, 9 Nov 2026): the subscriber
    #: reaches « Mon abonnement » alone, to read his invoices, settle what is due and
    #: subscribe again; the screen says « Votre abonnement a pris fin ».
    ended: bool = False
    #: Alice's billing calendar (her side, 8 Nov 2026), each null when she does not say
    #: (an older Alice sends none of them): when billing starts, whether a payment method
    #: is on file, when a debit failed, and the day of the suspension.
    billing_starts_on: str | None = None
    has_payment_method: bool | None = None
    payment_failed_on: str | None = None
    suspension_on: str | None = None


def _iso(day) -> str | None:
    return day.isoformat() if day else None


def _as_info(license_: dict | None) -> SubscriptionInfo:
    if not license_:
        return SubscriptionInfo(managed=False)
    state = licence_state.read(license_)
    return SubscriptionInfo(
        managed=True,
        suspended=bool(state and state.suspended),
        ended=bool(state and state.terminated),
        billing_starts_on=_iso(state.billing_starts_on) if state else None,
        has_payment_method=state.has_payment_method if state else None,
        payment_failed_on=_iso(state.payment_failed_on) if state else None,
        suspension_on=_iso(state.suspension_on) if state else None,
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
    """The FIRM's licence (`firm_of`), the one Alice files under the subscriber's id: a
    colleague reads the plan they work under, not an absent licence of their own."""
    if not alice_client.console_configured():
        return SubscriptionInfo(managed=False)
    try:
        licence = await alice_client.get_license(_payer(user), strict=True)
    except AliceUnavailable:
        return SubscriptionInfo(managed=True, unavailable=True, is_holder=_holds(user))
    return _as_info(licence).model_copy(update={"is_holder": _holds(user)})


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
    data = await alice_client.billing("GET", "status", _payer(user), strict=False)
    return data or {"stripe_enabled": False, "has_subscription": False}


@router.get("/plans", summary="Plans available to subscribe to")
async def available_plans(user: User = Depends(current_manager)) -> list:
    """The sellable « fund » plans, and only those.

    ⚠️ The console does the per-product filtering: asking for the list without saying who
    we are would surface the sister products' offers on this screen.
    """
    data = await alice_client.billing(
        "GET", "available-plans", _payer(user), strict=False
    )
    return data if isinstance(data, list) else []


class _PlanIn(BaseModel):
    plan_id: str | None = None
    #: The version of the terms of sale the screen showed and the subscriber ticked, when
    #: Alice publishes any. See `_sale_accepted`.
    cgv: str | None = None
    #: The version of the data processing agreement ticked beside it, on the same rule.
    dpa: str | None = None
    language: str = "fr"


def _owed_unreadable() -> HTTPException:
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        pick(
            "Les conditions générales de vente ne peuvent pas être chargées pour le "
            "moment : réessayez dans quelques minutes.",
            "The terms of sale cannot be loaded at the moment: try again in a few "
            "minutes.",
        ),
    )


def _terms_sentence(kind: str) -> str:
    """What the subscriber is asked: a plan, changed OR paid in place, is a sale."""
    return (
        pick(
            "Acceptez l'accord de traitement des données en vigueur avant de payer ou "
            "de changer de formule.",
            "Accept the data processing agreement in force before paying or changing "
            "plan.",
        )
        if kind == terms_api.DPA
        else pick(
            "Acceptez les conditions générales de vente en vigueur avant de payer ou de "
            "changer de formule.",
            "Accept the terms of sale in force before paying or changing plan.",
        )
    )


def _tick_required(kind: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _terms_sentence(kind))


async def _sale_accepted(user: User, request: Request, body: _PlanIn) -> None:
    """Choosing a plan is subscribing: the terms of sale are accepted there and then.

    🔴 THE MANAGER, 2 OCT 2026: the subscriber accepts the terms of sale at subscription,
    a plan change included. Alice's plan change carries no terms, so the acceptance is
    recorded first (`method="plan"`), and a refusal (409, a version that changed while the
    page was open) stops the change before it reaches the payment. 🔴 THE OWNER, 13 OCT
    2026: the data processing agreement is ticked and recorded the same way, beside them.

    ⚠️ THE SERVER CHECKS, NOT ONLY THE BOX: a change sent without a tick while that
    document is still owed is refused, BEFORE anything is recorded (no half acceptance).
    🔴 ONLY WHAT IS STILL OWED (the owner, 1 Nov 2026, Immo's rule): the version in force
    already accepted is not asked again, a new one is (`terms.is_owed`); nothing owed, the
    change goes through without a tick.
    Only the subscriber is asked; another account is not the one Alice bills, and her own
    refusal answers it. An Alice that does not serve the agreement yet (no `dpa` in her
    status) asks nothing of it.
    """
    if not user.holds_the_licence:
        return
    ticked = {terms_api.SALE: body.cgv, terms_api.DPA: body.dpa}
    missing = [kind for kind in terms_api.SUBSCRIBER_KINDS if not ticked[kind]]
    if missing:
        owed = await alice_client.terms_status(
            user.id, audience=terms_api.AUDIENCES[user.role], subscriber=True
        )
        if owed is None:
            raise _owed_unreadable()
        for kind in missing:
            if terms_api.is_owed(owed.get(kind)):
                raise _tick_required(kind)
    for kind in terms_api.SUBSCRIBER_KINDS:
        version = ticked[kind]
        if version:
            await terms_api.record_acceptance(
                user,
                request,
                kind=kind,
                version=version,
                language=body.language,
                method="plan",
            )


#: Alice's `X-Refusal` on a Checkout asked before the terms were accepted, by document.
_TERMS_REFUSALS = {"terms_cgv": terms_api.SALE, "terms_dpa": terms_api.DPA}


def _unavailable(exc: AliceUnavailable) -> HTTPException:
    """What the subscriber reads when Alice did not do what was asked.

    🔴 THE OWNER, 8 NOV 2026: her key refused, her insides or the network give ONE sentence,
    503 « service de facturation indisponible », never hers (« Clé interne invalide » is
    about the link between two services). A business refusal she wrote for the subscriber
    (a cap under the use, a plan that cannot be taken) is relayed with her status; her
    refusal for terms not accepted (409 `X-Refusal: terms_cgv` / `terms_dpa`) is said in
    this product's words, in the reader's language.
    """
    if isinstance(exc, AliceRefused):
        kind = _TERMS_REFUSALS.get(exc.refusal or "")
        if kind is not None:
            return HTTPException(status.HTTP_409_CONFLICT, _terms_sentence(kind))
        return HTTPException(exc.status, str(exc))
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE, alice_client.billing_unavailable()
    )


@router.post("/checkout", summary="Pay by card or SEPA direct debit")
async def checkout(
    request: Request,
    body: _PlanIn | None = None,
    user: User = Depends(current_manager),
) -> dict:
    """Opens a payment session and returns the address where the manager completes it.

    A plan named here is a subscription to it: its terms of sale are accepted first.
    🔴 AND PAYING THE PLAN IN PLACE IS A SALE TOO (the owner, 8 Nov 2026): the terms of sale
    and the agreement still owed are checked here as for a plan change, BEFORE Alice's
    Checkout (she refuses it otherwise, 409 `X-Refusal`). This path checked nothing.
    """
    payload: dict = {"currency": "eur"}
    if body and body.plan_id:
        _subscriber_only(user)
    await _sale_accepted(user, request, body or _PlanIn())
    if body and body.plan_id:
        await _journal(user, "subscription.checkout_started", {"plan_id": body.plan_id})
        payload["plan_id"] = body.plan_id
    try:
        return (
            await alice_client.billing("POST", "checkout", _payer(user), json=payload)
            or {}
        )
    except AliceUnavailable as exc:
        raise _unavailable(exc)


@router.post("/portal", summary="Manage the payment method")
async def portal(user: User = Depends(current_manager)) -> dict:
    """The portal where a card is changed, receipts read, and the subscription stopped."""
    try:
        return await alice_client.billing("POST", "portal", _payer(user)) or {}
    except AliceUnavailable as exc:
        raise _unavailable(exc)


@router.post("/declare-transfer", summary="Declare a payment made by transfer")
async def declare_transfer(user: User = Depends(current_manager)) -> dict:
    """The manager reports having sent the transfer: the console waits and reconciles.

    ⚠️ THIS DECLARATION IS NOT A PAYMENT and unblocks nothing on its own. It is an
    announcement, matched afterwards by the console against the actual bank movement.
    """
    try:
        return (
            await alice_client.billing("POST", "declare-transfer", _payer(user)) or {}
        )
    except AliceUnavailable as exc:
        raise _unavailable(exc)


@router.post("/cancel-transfer", summary="Cancel a declared transfer")
async def cancel_transfer(user: User = Depends(current_manager)) -> dict:
    try:
        return await alice_client.billing("POST", "cancel-transfer", _payer(user)) or {}
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
                _payer(user),
                json={"plan_id": body.plan_id, "currency": "eur"},
            )
            or {}
        )
    except AliceUnavailable as exc:
        raise _unavailable(exc)
    # The ceiling changed with the plan: what this process remembers is stale.
    alice_client.invalidate_license_cache(_payer(user))
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
        _payer(user),
        json={"plan_id": body.plan_id, "currency": "eur"},
        strict=False,
    )
    return data or {}


@router.get("/invoices", summary="The manager's own invoices")
async def invoices(user: User = Depends(current_manager)) -> list:
    return await alice_client.invoices(_payer(user))


@router.get("/invoices/{invoice_id}/pdf", summary="An invoice as a PDF")
async def invoice_pdf(
    invoice_id: str, user: User = Depends(current_manager)
) -> Response:
    """⚠️ THE MANAGER'S ID IS THE SESSION'S, never a parameter. The console files invoices
    by manager: accepting an id from the request would let another fund's invoice be read
    by changing one digit in the address."""
    return _pdf(await alice_client.invoice_pdf(_payer(user), invoice_id))


@router.get("/invoices/credit-notes/{note_id}/pdf", summary="A credit note as a PDF")
async def credit_note_pdf(
    note_id: uuid.UUID, user: User = Depends(current_manager)
) -> Response:
    """A credit note on one of the manager's subscription invoices, shown in
    « Mon abonnement » (the owner, 6 Nov 2026). The manager's id is the SESSION's, as for
    an invoice: Alice refuses a note that is not on one of theirs."""
    return _pdf(await alice_client.credit_note_pdf(_payer(user), note_id))


def _pdf(found: tuple[bytes, str] | None) -> Response:
    """An invoice or a credit note relayed with Alice's filename; one refusal for both."""
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
    data = await alice_client.billing("GET", "payments", _payer(user), strict=False)
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


def _payer(user: User) -> uuid.UUID:
    """The id Alice files the licence under: the FIRM's (`firm_of`), whoever asks.

    ⚠️ ALWAYS THE SESSION'S FIRM, never an id from the request: another fund's invoice
    must not be one digit away in an address. For the subscriber it is their own id."""
    return firm_of(user)


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
        data = await alice_client.billing("GET", "plan-offer", _payer(user))
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
            _payer(user),
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
