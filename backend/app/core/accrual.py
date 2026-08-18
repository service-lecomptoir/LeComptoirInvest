"""What a lender is owed on a given day, computed and not estimated.

🔴 THIS IS THE ONLY PLACE THAT SAYS WHAT A LOAN IS OWED, and everything downstream depends
on it being right. `DISTRIBUTION_ORDER` says lenders are served first; that ordering is
worth nothing until something can answer « first in line for HOW MUCH ». Until this module
existed the constant was documented, tested for its identity, and applied nowhere.

⚠️ THE DAY COUNT IS A TERM OF THE CONTRACT, NOT A DETAIL. « 8 % a year » on 250 000 over a
half-year is one amount on ACT/365 and another on 30/360, and the difference is money owed.
The convention applied here is stated in `DAY_COUNT`, and a loan written on another one
must record it rather than be run through this.

🔴 AND WHAT CANNOT BE COMPUTED IS REFUSED, NEVER GUESSED. An amortising loan is repaid on
the schedule its contract sets; inventing a straight line because none was recorded would
produce a figure that looks like an amount owed and is not one. `amount_due` answers with a
reason instead, the same shape the sister product uses for a tax it cannot compute — an
unavailable answer is a state, and it must reach the screen as one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.core import money
from app.core.instruments import LoanTerms

#: Actual days over a fixed 365-day year. Stated rather than implied, and applied to every
#: loan this module sees. A contract on 30/360 or ACT/360 is a different arithmetic and must
#: carry its own convention before it is run through here.
DAY_COUNT = "ACT/365"
_YEAR_DAYS = Decimal("365")


@dataclass(frozen=True)
class Due:
    """What one loan is owed on a date, and what remains unknown.

    ⚠️ `interest` AND `capital` ARE SEPARATE, all the way down. A lender's interest is
    income and taxed as such; capital coming back is their own money. One figure here would
    make every downstream split a guess, and the tax statement wrong for everyone.
    """

    interest: Decimal
    capital: Decimal
    #: Filled when the amount could NOT be computed. When set, `interest` and `capital` are
    #: both zero and must not be read as « nothing is owed ».
    unavailable_reason: str | None = None

    @property
    def total(self) -> Decimal:
        return self.interest + self.capital

    @property
    def is_known(self) -> bool:
        return self.unavailable_reason is None


def interest_accrued(
    *,
    principal: Decimal,
    rate: float,
    since: date,
    until: date,
    currency: str,
) -> Decimal:
    """Interest run up between two dates, on `DAY_COUNT`.

    Rounded to the currency's real minor unit at the end and never mid-way: rounding each
    period and summing drifts, and on a monthly loan over five years it drifts by cents an
    investor will add up and ask about.
    """
    if until <= since or principal <= 0 or rate <= 0:
        return Decimal("0")
    days = Decimal((until - since).days)
    raw = principal * Decimal(str(rate)) * days / _YEAR_DAYS
    return money.quantize(raw, currency)


def amount_due(
    *,
    terms: LoanTerms | None,
    principal_contributed: Decimal,
    currency: str,
    drawn_on: date,
    matures_on: date | None,
    as_of: date,
    interest_already_paid: Decimal = Decimal("0"),
    capital_already_repaid: Decimal = Decimal("0"),
) -> Due:
    """What this loan is owed on `as_of`, net of what has already been served.

    ⚠️ NET OF WHAT WAS ALREADY PAID, and that is why both figures are arguments rather than
    something this function looks up. A run of this over a loan served for three years must
    not re-owe the first three years; a function that computed gross would be correct once
    and wrong every time after.

    ⚠️ INTEREST ACCRUES ON WHAT WAS ACTUALLY DRAWN, never on what was committed. A lender
    who committed 500 000 and has transferred 200 000 is owed interest on 200 000: charging
    the fund for money it never received is the mistake that flatters the lender, and it is
    just as wrong as the one that flatters the fund.
    """
    if terms is None:
        return Due(
            Decimal("0"),
            Decimal("0"),
            "Ce prêt ne porte aucune condition : ni taux, ni échéance, ni mode de "
            "remboursement. Rien ne peut être dû tant qu'elles ne sont pas enregistrées.",
        )
    if not terms.bullet:
        # A schedule is a contract, not a shape this module may assume. Straight-line and
        # annuity give different amounts on the same loan, and neither is « the » default.
        return Due(
            Decimal("0"),
            Decimal("0"),
            "Ce prêt est amortissable : son échéancier vient du contrat et n'est pas "
            "enregistré. Le montant dû ne se déduit pas du taux seul.",
        )

    outstanding = principal_contributed - capital_already_repaid
    if outstanding < 0:
        outstanding = Decimal("0")

    gross_interest = interest_accrued(
        principal=principal_contributed,
        rate=terms.rate,
        since=drawn_on,
        until=as_of,
        currency=currency,
    )
    interest = gross_interest - interest_already_paid
    if interest < 0:
        # Served ahead of the accrual: a real situation, and not a debt of the lender.
        interest = Decimal("0")

    # 🔴 CAPITAL IS OWED AT MATURITY AND NOT BEFORE. A bullet loan carries its principal to
    # the end; treating it as due earlier would put the fund in a self-declared default and
    # freeze every distribution to subscribers — the guard working off a false fact.
    capital = Decimal("0")
    if matures_on is not None and as_of >= matures_on:
        capital = outstanding

    return Due(money.quantize(interest, currency), money.quantize(capital, currency))


#: The basis the preferred return accrues on: the loans' day count, simple interest.
#:
#: It is a clause of the contract, not an implementation detail: over eight years at 8 %,
#: the compounded version owes nearly a third more than the simple one, and that gap is
#: exactly what the manager takes home less. A fund written on another basis must record it
#: rather than be run through this.
#:
#: ⚠️ DERIVED FROM `DAY_COUNT`, NEVER RESTATED. Two constants spelling the same convention
#: drift, and the one nobody reads is the one that stays wrong. It also keeps this string
#: out of the shape a stored domain value has — which it is not, and which the inventory
#: guard rightly refuses.
PREFERRED_RETURN_BASIS = f"{DAY_COUNT}, simple interest"


def preferred_return_accrued(
    *,
    capital_at_work: Decimal,
    rate: float,
    since: date,
    until: date,
    currency: str,
    already_served: Decimal = Decimal("0"),
) -> Decimal:
    """The preferred return still owed to a subscriber on a date.

    🔴 A HURDLE IS NOT A DEBT, and this function does not pretend otherwise. It computes a
    THRESHOLD: what subscribers must have received before the manager takes anything. If the
    fund earns nothing, nobody is owed anything, and the shortfall does not carry forward the
    way an unpaid coupon does. That is the whole difference with `amount_due`, which measures
    a claim the lender can enforce.

    ⚠️ IT ACCRUES ON CAPITAL AT WORK, never on capital subscribed. A subscriber whose money
    has already come halfway back cannot claim a preferred return on what they got back, and
    serving it to them comes out of the other subscribers' share.

    ⚠️ NET OF WHAT WAS ALREADY SERVED, for the same reason as with lenders: without it every
    distribution would re-owe the preference from inception, and the manager would never
    reach any carried interest at all.
    """
    gross = interest_accrued(
        principal=capital_at_work,
        rate=rate,
        since=since,
        until=until,
        currency=currency,
    )
    remaining = gross - already_served
    return remaining if remaining > 0 else Decimal("0")


def allocate(amount: Decimal, weights: list[Decimal], currency: str) -> list[Decimal]:
    """Split `amount` in proportion to `weights`, losing nothing.

    🔴 THE PARTS SUM BACK TO THE WHOLE, EXACTLY. Rounding each share independently leaves a
    remainder that has to go somewhere, and « somewhere » is the fund's account: a hundred
    investors and a few cents each is a real amount the fund quietly kept, and it reconciles
    to nothing. The largest remainders take the leftover minor units, one each — the method
    a registrar uses, and the one an auditor recognises.

    Equal weights get the leftover in order, which is arbitrary but STABLE: the same input
    always produces the same split, so a proposal shown on screen is the proposal recorded.
    """
    total_weight = sum(weights, Decimal("0"))
    if total_weight <= 0 or amount <= 0:
        return [Decimal("0") for _ in weights]

    step = Decimal(1).scaleb(-money.minor_units(currency))
    exact = [amount * w / total_weight for w in weights]
    # Floor every share first: `quantize` rounds half up, and a share rounded UP would make
    # the parts exceed the whole, which no leftover pass can repair.
    floored = [
        (x / step).to_integral_value(rounding="ROUND_FLOOR") * step for x in exact
    ]
    leftover = amount - sum(floored, Decimal("0"))

    units = int((leftover / step).to_integral_value())
    if units > 0:
        order = sorted(range(len(weights)), key=lambda i: (-(exact[i] - floored[i]), i))
        for i in order[:units]:
            floored[i] += step
    return [money.quantize(x, currency) for x in floored]
