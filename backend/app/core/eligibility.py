"""Who may commit how much, and what must happen before a commitment binds them.

🔴 THIS IS NOT A KYC CHECK, AND CONFUSING THE TWO IS THE POINT OF A SEPARATE MODULE. KYC
answers « may the fund do business with this person at all »: identity, sanctions, source of
funds. Eligibility answers a different question about somebody already accepted — « is this
amount, for this person, an investment they are allowed to make ». A cleared investor can
still be over their cap, and a refused one is not merely over it.

⚠️ THE PARAMETERS ARE CONSTANTS, NAMED, AND THEY ARE NOT LAW ITSELF. The European
crowdfunding regulation sets a warning threshold for retail investors at the greater of a
flat amount or a share of their loss-bearing capacity, and a reflection period during which
they may step back without penalty. Those are recorded below as figures a fund can point at
and an auditor can check. A fund under another regime, or one whose national rules moved,
changes the constant — it does not go hunting for the rule spread across five endpoints.

🔴 AND WHAT IS NOT DECLARED IS NOT ASSUMED. An investor who never stated a loss-bearing
capacity has not thereby stated a large one. The threshold is then UNKNOWN, the answer says
so, and the caller decides — exactly the shape `accrual.amount_due` uses for a loan it
cannot measure. Treating silence as « no cap applies » would let the one investor nobody
assessed commit the most.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from app.core.i18n import pick

#: An individual investing their own savings. The category the protections exist for.
RETAIL = "retail"
#: An individual or entity that has been assessed and opted out of retail protections.
SOPHISTICATED = "sophisticated"
#: A regulated or qualifying entity: the protections do not apply.
PROFESSIONAL = "professional"

CATEGORIES: tuple[str, ...] = (RETAIL, SOPHISTICATED, PROFESSIONAL)

#: Categories the retail protections apply to. Written as a set rather than as « not
#: professional »: a category added later must be placed here on purpose, and a test written
#: by exclusion answers « unprotected » for every category invented after it.
PROTECTED_CATEGORIES: frozenset[str] = frozenset({RETAIL})

#: Below this, no warning is required whatever the investor's capacity: a small amount is
#: not made risky by a modest net worth.
FLAT_THRESHOLD = Decimal("1000")
#: Above the flat amount, the threshold is this share of declared loss-bearing capacity.
CAPACITY_SHARE = Decimal("0.05")
#: Calendar days a retail investor may step back in, from the day the request is made.
REFLECTION_DAYS = 4


@dataclass(frozen=True)
class Threshold:
    """What this investor may commit before a warning and an explicit consent are required.

    `amount` is None when it could not be established, and `unavailable_reason` then says
    which fact is missing. None is never « no limit ».
    """

    amount: Decimal | None
    unavailable_reason: str | None = None

    @property
    def is_known(self) -> bool:
        return self.unavailable_reason is None


def is_protected(category: str | None) -> bool:
    """Do the retail protections apply to this investor?

    ⚠️ AN UNKNOWN CATEGORY IS TREATED AS PROTECTED. The failure mode of a protection must be
    « too much protection », never « none »: an investor whose category was never recorded is
    exactly the one nobody assessed.
    """
    return (category or RETAIL) in PROTECTED_CATEGORIES


def warning_threshold(
    *, category: str | None, loss_bearing_capacity: Decimal | None
) -> Threshold:
    """The amount above which a retail investor must be warned and must consent explicitly.

    The greater of the flat amount and a share of declared capacity: a small saver is not
    held to five per cent of very little, and a larger one is not waved through on the flat
    figure alone.
    """
    if not is_protected(category):
        return Threshold(amount=None, unavailable_reason=None)
    if loss_bearing_capacity is None:
        return Threshold(
            amount=None,
            unavailable_reason=pick(
                "La capacité de perte de cet investisseur n'a pas été déclarée : le seuil "
                "au-delà duquel un avertissement est requis ne peut pas être établi.",
                "This investor's loss-bearing capacity has not been declared: the threshold "
                "above which a warning is required cannot be established.",
            ),
        )
    if loss_bearing_capacity < 0:
        return Threshold(
            amount=None,
            unavailable_reason=pick(
                "La capacité de perte déclarée est négative.",
                "The declared loss-bearing capacity is negative.",
            ),
        )
    return Threshold(amount=max(FLAT_THRESHOLD, loss_bearing_capacity * CAPACITY_SHARE))


def needs_explicit_consent(
    *,
    category: str | None,
    amount: Decimal,
    loss_bearing_capacity: Decimal | None,
) -> tuple[bool, str | None]:
    """Does this commitment require a risk warning and an acknowledged consent?

    Returns `(required, reason)`. `reason` is filled when the answer could not be computed,
    and the caller must then refuse rather than proceed: an unmeasured threshold is not a
    threshold that was met.
    """
    threshold = warning_threshold(
        category=category, loss_bearing_capacity=loss_bearing_capacity
    )
    if not is_protected(category):
        return False, None
    if not threshold.is_known:
        return False, threshold.unavailable_reason
    return amount > threshold.amount, None


def reflection_period_ends(*, requested_on: date, category: str | None) -> date | None:
    """The last day a protected investor may step back, or None when none applies.

    🔴 THE PERIOD RUNS FROM THE REQUEST, NOT FROM THE FUND'S DECISION. A fund that took a
    fortnight to answer would otherwise start the clock a fortnight late, and one that
    answered within the hour would bind the investor before they had it. The delay belongs to
    the investor; it cannot depend on how fast the fund works.
    """
    if not is_protected(category):
        return None
    return requested_on + timedelta(days=REFLECTION_DAYS)


def may_bind(
    *, requested_on: date, category: str | None, on: date
) -> tuple[bool, str | None]:
    """May a commitment be signed on `on`, given when it was asked for?

    ⚠️ THE REFLECTION PERIOD IS NOT ADVISORY. A screen that displayed the date but let the
    commitment be signed anyway would record a binding engagement the investor could still
    revoke — and the fund would have called capital on it.
    """
    ends = reflection_period_ends(requested_on=requested_on, category=category)
    if ends is None or on > ends:
        return True, None
    return False, pick(
        f"Le délai de réflexion de cet investisseur court jusqu'au {ends.isoformat()} : "
        f"aucun engagement ne peut être signé avant, et il peut se rétracter d'ici là.",
        f"This investor's reflection period runs until {ends.isoformat()}: no commitment may "
        f"be signed before then, and they may step back until it ends.",
    )


__all__ = [
    "CATEGORIES",
    "CAPACITY_SHARE",
    "FLAT_THRESHOLD",
    "PROFESSIONAL",
    "PROTECTED_CATEGORIES",
    "REFLECTION_DAYS",
    "RETAIL",
    "SOPHISTICATED",
    "Threshold",
    "is_protected",
    "may_bind",
    "needs_explicit_consent",
    "reflection_period_ends",
    "warning_threshold",
]
