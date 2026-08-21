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

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import kyc
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


async def count_investors(db: AsyncSession) -> int:
    """How many investors this installation carries. THE BILLING QUANTITY.

    🔴 THE GUARD AND THE INVOICE COUNT THE SAME THING BECAUSE THEY CALL THE SAME FUNCTION.
    This used to live inside `internal_admin.py`, where only the console could reach it.
    Had the guard grown its own `select(count())` it would have been right the day it was
    written and wrong at the first change to either — and the symptom would have been a
    fund refused at forty-nine while being billed for fifty-one, each number defensible on
    its own.

    🔴 A REFUSED FILE IS NOT AN INVESTOR UNDER MANAGEMENT. They were assessed and turned
    away: they hold nothing, they receive nothing, and no capital call will ever go to
    them. Counting them would bill a fund for the people it declined — and the more
    carefully it screens, the more it would pay.

    ⚠️ EVERYTHING ELSE COUNTS, including a file still pending or under review. The work is
    done the moment the file exists, which is exactly what is being billed; waiting for an
    acceptance would make the quantity lag the effort by weeks.
    """
    return int(
        (
            await db.execute(select(func.count(Investor.id)).where(COUNTABLE))
        ).scalar_one()
    )


async def count_investors_by_firm(db: AsyncSession) -> dict:
    """The same quantity, per management company, in ONE query.

    🔴 FOR THE CONSOLE, AND ONLY FOR IT. Every other caller runs inside a firm, so the
    injected scope already answers the question; the console reads across firms on purpose
    and must therefore say which count belongs to whom.

    🔴 THIS EXISTS BECAUSE THE PER-FIRM ISOLATION MADE THE OLD ANSWER WRONG, AND IT WAS
    MONEY. Until 21 August this product had one register for the whole installation, so the
    console reported the SAME count to every manager account -- documented, and true at the
    time. The day two firms shared an installation, that number billed each of them for the
    other's investors, and nothing anywhere would have looked broken.

    ⚠️ ONE QUERY, NOT ONE PER MANAGER. The console lists every account of the platform; a
    count per row is a screen that slows down exactly as the business grows.

    ⚠️ AND IT COUNTS THE SAME THING AS `count_investors`, by construction: both read
    `COUNTABLE`. Two predicates would eventually disagree, and the fund would be refused at
    forty-nine while being billed for fifty-one.
    """
    rows = (
        await db.execute(
            select(Investor.firm_id, func.count(Investor.id))
            .where(COUNTABLE)
            .group_by(Investor.firm_id)
        )
    ).all()
    return {firm: int(total) for firm, total in rows}


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
        "price": float((licence or {}).get("overage_price") or 0),
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
        licence = await alice_client.get_license(user.id, strict=True)
    except alice_client.AliceUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
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
    return outlook(licence, await count_investors(db), adding)


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

    view = outlook(licence, await count_investors(db), adding)
    if view["verdict"] == OK:
        return

    current, limit, price = view["current"], view["limit"], view["price"]
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
                f"investisseur au-delà est facturé {price:g} €/mois, ajouté à votre "
                "abonnement. Confirmez pour continuer.",
                f"Registering this investor exceeds your plan ({current}/{limit}). Each "
                f"investor beyond it is billed {price:g} €/month, added to your "
                "subscription. Confirm to continue.",
            )
        else:
            detail = pick(
                f"Cette opération dépasse votre forfait de {view['excess']} "
                f"investisseur(s) ({current}/{limit}). Chacun au-delà est facturé "
                f"{price:g} €/mois, ajouté à votre abonnement. Confirmez pour continuer.",
                f"This exceeds your plan by {view['excess']} investor(s) "
                f"({current}/{limit}). Each one beyond it is billed {price:g} €/month, "
                "added to your subscription. Confirm to continue.",
            )
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, detail)


__all__ = [
    "BLOCKED",
    "OK",
    "OVERAGE",
    "UNKNOWN",
    "check_investor_quota",
    "count_investors",
    "outlook",
    "quota_outlook",
]
