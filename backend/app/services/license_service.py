"""The investor allowance the plan pays for, checked in ONE single place.

🔴 THIS PRODUCT EMITTED THE QUANTITY AND NEVER READ THE CEILING. `internal_admin.py` has
reported `managed_count` to the console since the first day, and `billing.py` shows the
`managed_limit` that comes back on the subscription screen — but nothing between the two
ever compared them. A fund on a plan of fifty could register five hundred investors and
the only trace was on the invoice. That is this repository's recurring defect: a rule
written down, and applied nowhere. The cure is an APPLIED rule with CALLERS, not a better
comment.

WHAT THE VERDICT IS, AND WHO DECIDES IT. Not this file: the plan does.

  - no console configured       -> no ceiling, nothing to check (a self-hosted fund)
  - console unreachable         -> 503
  - no licence for this account -> 403
  - within the allowance        -> pass
  - ceiling reached, overage forbidden by the plan  -> 400 (change plan)
  - ceiling reached, overage allowed, not confirmed -> 402 + the monthly price

🔴 THE 402 IS THE WHOLE POINT AND IT IS NOT A FAILURE. It means « this will cost more, say
yes ». Billing a fund for an investor it added without being told the price is the one
outcome this module exists to prevent — and refusing outright when the plan actually
ALLOWS the overage would be just as wrong, since that freedom is part of what they bought.

⚠️ A GUARD IS NOT A SCREEN, and this file therefore departs from `alice_client`'s house
rule that everything degrades softly. A subscription panel that cannot reach the console
shows « unknown » and the fund keeps running; a QUOTA that cannot reach the console knows
nothing about the ceiling, and answering « fine » would make every plan unlimited for as
long as the console is down. The escape hatch for a fund with no console at all is the
first line of the list above, and it is decided on CONFIGURATION, never on a failed call.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import display, kyc
from app.core.firm_scope import firm_of
from app.core.i18n import pick
from app.models.investor import Investor
from app.models.user import MANAGER, User
from app.services import alice_client

#: Only a fund manager carries an investor allowance. An admin account is the platform's
#: own, holds no licence at the console, and adding a register entry from it must not fail
#: on a plan nobody ever sold them.
_LICENSED_ROLES: tuple[str, ...] = (MANAGER,)

#: 🔴 WHO COUNTS AS « UNDER MANAGEMENT », WRITTEN ONCE. The guard that refuses and the
#: figure that bills read this same predicate; two copies of it would drift, and the fund
#: would be refused at forty-nine while being invoiced for fifty-one.
COUNTABLE = Investor.kyc_status != kyc.REFUSED

#: Every verdict this module can return, so a caller branches on the word rather than
#: re-deriving it from a status code.
OK = "ok"
OVERAGE = "overage"
BLOCKED = "blocked"
UNKNOWN = "unknown"


async def billable_investor_counts(
    db: AsyncSession, firm: uuid.UUID | None = None
) -> dict[uuid.UUID, int]:
    """THE BILLING QUANTITY: investors per management company. THE ONE COUNT.

    🔴 ONE FUNCTION FOR EVERY READER (the owner, 8 Nov 2026): the ceiling and its 402
    (`check_investor_quota`), the screen's « 48 / 50 » (`quota_outlook`) and the
    `managed_count` Alice bills and lists (`/internal/managers`). Two copies would drift, and
    the fund would be refused at forty-nine while invoiced for fifty-one.

    - **by the firm that manages**: `investors.firm_id`, stamped with the firm of the
      account that registered them (`firm_scope`), so an investor counts ONCE, for the firm
      whose register holds them, whichever colleague typed them in;
    - **a refused file frees its place** (`COUNTABLE`): assessed and turned away, they hold
      nothing and receive nothing. Reversing the refusal asks the place back
      (`investors.record_verdict`, the second door);
    - everything else counts, a file pending or under review included: the work is done
      the moment the file exists.

    ⚠️ This product has no archive and no exit of an investor (8 Nov 2026): the refusal is
    the only way a place is freed.

    `firm` narrows to one firm; without it, every firm in reach of the caller's scope (all
    of them under `/internal`, which opens it on the console's key). ONE query either way.
    """
    query = (
        select(Investor.firm_id, func.count(Investor.id))
        .where(COUNTABLE)
        .group_by(Investor.firm_id)
    )
    if firm is not None:
        query = query.where(Investor.firm_id == firm)
    rows = (await db.execute(query)).all()
    return {owner: int(total) for owner, total in rows if owner is not None}


async def count_investors(db: AsyncSession, firm: uuid.UUID) -> int:
    """`billable_investor_counts` for one firm, as a number."""
    return (await billable_investor_counts(db, firm)).get(firm, 0)


def billing_currency() -> str:
    """The currency this product's subscription is billed in.

    Invest asks Alice's Checkout and plan change in euros (`api/v1/billing.py`): the price
    of the overage is read and written in that currency, with its decimals.
    """
    return "EUR"


def overage_price(licence: dict | None) -> float:
    """The monthly price of one investor beyond the plan, in `billing_currency()`.

    Alice's `overage_prices` (per currency) first, her single `overage_price` (the euro)
    when the plan names none for the currency.
    """
    lic = licence or {}
    prices = lic.get("overage_prices")
    if isinstance(prices, dict):
        found = prices.get(billing_currency()) or prices.get(billing_currency().lower())
        if isinstance(found, int | float):
            return float(found)
    return float(lic.get("overage_price") or 0)


def outlook(licence: dict | None, current: int, adding: int) -> dict:
    """What `adding` more investors would do to the allowance, deciding nothing.

    🔴 THE SCREEN THAT ANNOUNCES AND THE GUARD THAT REFUSES READ THIS SAME FUNCTION. A
    panel promising an overage at 8 €/month while the guard refuses the registration is
    worse than announcing nothing at all: the reader stops believing either one.
    """
    # 🔴 THE CONTRACT'S NAME, NOT OURS. Alice sends `managed_limit`: one key for five
    # products, counting properties at Immo, homes at Sejour, shops at Market, investors
    # here. Read under any other name it comes back EMPTY — and an empty ceiling reads as
    # « unlimited », so every check would answer « fine » and nothing would ever fail.
    limit = (licence or {}).get("managed_limit")
    after = current + adding
    base = {
        "current": current,
        "limit": limit,
        "adding": adding,
        "after": after,
        "excess": 0,
        "price": overage_price(licence),
        "monthly_cost": 0.0,
    }
    # ⚠️ `None` IS A VALUE HERE, NOT AN ABSENCE: « unlimited » travels as null on the wire.
    if limit is None or after <= limit:
        return {**base, "verdict": OK}

    excess = after - limit
    return {
        **base,
        "excess": excess,
        "monthly_cost": round(excess * base["price"], 2),
        "verdict": OVERAGE if (licence or {}).get("overage_allowed") else BLOCKED,
    }


async def _licence_of(user: User) -> dict | None:
    """The caller's licence, or None when no console drives this installation.

    ⚠️ « NO CONSOLE » AND « THE CONSOLE DID NOT ANSWER » ARE NOT THE SAME STATE, and this
    is the seam where they part. The first is a fund hosted on its own and a legitimate way
    to run the product; the second is a ceiling nobody can read, and it raises.
    """
    if not alice_client.console_configured():
        return None
    try:
        # 🔴 THE FIRM'S LICENCE, for every account of its team (8 Nov 2026). It was read on
        # the caller's own id: a colleague, whose id Alice files no licence under, met a
        # 403 where the subscriber met the ceiling and its 402.
        licence = await alice_client.get_license(firm_of(user), strict=True)
    except alice_client.AliceUnavailable as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, alice_client.billing_unavailable()
        ) from exc
    if licence is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            pick(
                "Aucun abonnement n'est rattaché à ce compte. Contactez l'administrateur.",
                "No subscription is attached to this account. Contact the administrator.",
            ),
        )
    return licence


async def quota_outlook(db: AsyncSession, user: User, *, adding: int = 1) -> dict:
    """Read-only verdict: it informs, it never refuses.

    The screen calls this to say « 48 of 50 » BEFORE anybody opens a form, so a manager
    raises their plan on their own terms instead of meeting a refusal the moment they press
    « save ». An unreadable allowance is `unknown` here and NOT an error — the guard, for
    its part, will still refuse.
    """
    empty = {
        "verdict": OK,
        "current": 0,
        "limit": None,
        "adding": adding,
        "after": adding,
        "excess": 0,
        "price": 0.0,
        "monthly_cost": 0.0,
    }
    if user.role not in _LICENSED_ROLES:
        return empty
    try:
        licence = await _licence_of(user)
    except HTTPException:
        return {**empty, "verdict": UNKNOWN}
    if licence is None:
        return empty
    return outlook(licence, await count_investors(db, firm_of(user)), adding)


async def check_investor_quota(
    db: AsyncSession,
    user: User,
    *,
    adding: int = 1,
    accept_overage: bool = False,
) -> None:
    """Refuse, or ask for consent, before `adding` more investors become countable.

    ⚠️ `adding == 0` IS A REAL CASE AND PASSES WITHOUT A SINGLE CALL. A KYC verdict that
    refuses an investor, or one that leaves a countable file countable, changes nothing the
    plan bills — and reaching out to the console to learn that would make a compliance
    decision fail on a subscription outage.
    """
    if adding <= 0 or user.role not in _LICENSED_ROLES:
        return

    licence = await _licence_of(user)
    if licence is None:
        return  # No console drives this installation: there is no ceiling to enforce.
    if licence.get("managed_limit") is None:
        return  # Unlimited allowance.

    view = outlook(licence, await count_investors(db, firm_of(user)), adding)
    if view["verdict"] == OK:
        return

    current, limit = view["current"], view["limit"]
    # 🔴 IN THE ACCOUNT'S CURRENCY, WITH ITS DECIMALS, IN THE READER'S LANGUAGE (8 Nov
    # 2026): « 12,50 € » to a French reader, « €12.50 » to an English one, never « 12.5 € ».
    price = display.amount(view["price"], billing_currency())
    if view["verdict"] == BLOCKED:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            pick(
                f"Limite d'investisseurs atteinte ({current}/{limit})"
                + (f" : cette opération en ajouterait {adding}." if adding > 1 else ".")
                + " Passez à une offre supérieure pour en enregistrer d'autres.",
                f"Investor limit reached ({current}/{limit})"
                + (f": this would add {adding}." if adding > 1 else ".")
                + " Move to a larger plan to register more.",
            ),
        )

    if not accept_overage:
        # 402 = consent required. The screen confirms, then sends the same request again
        # with `accept_overage=true`. The COUNT and the PRICE are both announced: nobody
        # should discover a supplement on their next invoice.
        #
        # ⚠️ EACH BRANCH IS A WHOLE SENTENCE INSIDE `pick`, never a French fragment joined
        # to a translated tail. The guard that reads this file looks for prose OUTSIDE
        # `pick`, and it is right to: a half-sentence assembled above cannot be seen to
        # have an English twin, and that is how one ships untranslated.
        if adding == 1:
            detail = pick(
                f"Cet enregistrement dépasse votre forfait ({current}/{limit}). Chaque "
                f"investisseur au-delà est facturé {price} par mois, ajouté à votre "
                "abonnement. Confirmez pour continuer.",
                f"Registering this investor exceeds your plan ({current}/{limit}). Each "
                f"investor beyond it is billed {price} a month, added to your "
                "subscription. Confirm to continue.",
            )
        else:
            detail = pick(
                f"Cette opération dépasse votre forfait de {view['excess']} "
                f"investisseur(s) ({current}/{limit}). Chacun au-delà est facturé "
                f"{price} par mois, ajouté à votre abonnement. Confirmez pour continuer.",
                f"This exceeds your plan by {view['excess']} investor(s) "
                f"({current}/{limit}). Each one beyond it is billed {price} a month, "
                "added to your subscription. Confirm to continue.",
            )
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, detail)


__all__ = [
    "BLOCKED",
    "OK",
    "OVERAGE",
    "UNKNOWN",
    "billable_investor_counts",
    "billing_currency",
    "check_investor_quota",
    "count_investors",
    "overage_price",
    "outlook",
    "quota_outlook",
]
