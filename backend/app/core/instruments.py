"""What an investor holds, in what order they are paid, and how one becomes the other.

THE FUND IS EQUITY FIRST, AND THE LENDER IS PAID FIRST. Those are not in tension: the first
says what the vehicle is FOR — investors subscribe, loans are a bridge until they convert —
and the second says who is served when money moves. A bridge is not what the returns are
for, and it is still owed before them.

TWO ORDERINGS, NOT ONE, and only one of them is the fund's to choose. The first version of
this file held a single `PAYMENT_RANK`, and it was wrong in the way that only shows up on
the worst day: it made one tuple answer two different questions.

  * WHO IS PAID FIRST WHEN THE FUND WINDS DOWN is not a contractual choice. A lender is a
    creditor, and creditors rank ahead of members in an insolvency whatever any agreement
    says. `LIQUIDATION_RANK` records that, and it is not editable by preference.
  * WHO IS SERVED FIRST OUT OF A VOLUNTARY DISTRIBUTION, while the fund is solvent and
    paying everybody, IS the fund's choice. `DISTRIBUTION_ORDER` records that one.

Conflating them produces a tool that shows an order the law will not honour on the one day
the order decides who loses money. Same shape as the sister product's « a base to declare »
against « the tax itself »: two facts, one word, and the word wins until it costs something.

⚠️ AND THE TRAP THAT FOLLOWS FROM HAVING BOTH. Distributing to subscribers the cash that
was to serve a lender's next instalment does not merely reorder anything — it CAUSES the
default. A distribution has to be checked against what is contractually owed before it is
paid, not ranked against it.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The investor SUBSCRIBES to the fund. The primary instrument: this is what the fund is.
EQUITY = "equity"
#: The investor LENDS to the fund. Secondary, and convertible into a subscription.
LOAN = "loan"

INSTRUMENTS: tuple[str, ...] = (EQUITY, LOAN)


#: IMPOSED, NOT CHOSEN. A creditor is paid before a member in a wind-down, and no clause
#: reorders that. Recorded here so the tool never displays an order the law will refuse.
LIQUIDATION_RANK: tuple[str, ...] = (LOAN, EQUITY)

#: THE FUND'S OWN CHOICE, and it applies only while the fund is solvent and current on what
#: it owes. Lenders first (user, 17 August 2026), which is also the usual order: a lender
#: accepted a capped return in exchange for being served first, and paying subscribers out
#: of the cash owed on the next instalment does not reorder a default — it causes one.
#:
#: ⚠️ IDENTICAL TO `LIQUIDATION_RANK` TODAY, AND STILL A SEPARATE CONSTANT. The temptation
#: to merge two tuples holding the same two words is exactly what must be resisted: one is
#: IMPOSED by insolvency law and may not be edited, the other is the fund's CONTRACT and
#: may. They agree because the contract chose the usual order, not because they are the
#: same fact. Merging them would make a future change to the distribution order silently
#: rewrite what the law imposes — a line nobody would read as doing that.
DISTRIBUTION_ORDER: tuple[str, ...] = (LOAN, EQUITY)


def _position(order: tuple[str, ...], instrument: str) -> int:
    try:
        return order.index(instrument)
    except ValueError:
        raise ValueError(
            f"Unknown instrument {instrument!r}: it has no place in this order. Add it "
            f"deliberately before any distribution or wind-down can run."
        ) from None


def liquidation_rank(instrument: str) -> int:
    """Position in a WIND-DOWN. Lower is served first. Not configurable."""
    return _position(LIQUIDATION_RANK, instrument)


def distribution_rank(instrument: str) -> int:
    """Position in a VOLUNTARY distribution. Lower is served first. The fund's choice."""
    return _position(DISTRIBUTION_ORDER, instrument)


@dataclass(frozen=True)
class LoanTerms:
    """What a lender is owed and when — and what happens when the loan converts.

    A CONVERTIBLE LOAN IS STILL DEBT UNTIL IT CONVERTS. Until that date the lender is a
    creditor, owed their instalments whatever the projects do, and ranking ahead of every
    subscriber in a wind-down. The conversion is a future event, not a present state, and
    treating the loan as « nearly equity » is how a fund misses an instalment it always owed.
    """

    #: Annual nominal rate, as a fraction (0.08 = 8 %).
    rate: float
    #: Whole months from the first drawdown to the last instalment.
    term_months: int
    #: Months between instalments (1 = monthly, 3 = quarterly, 12 = yearly).
    period_months: int = 12
    #: True when capital is repaid in one go at the end, interest served meanwhile.
    bullet: bool = True
    #: May this loan become a subscription? The fund's loans are meant to.
    convertible: bool = True
    #: Does interest accrued up to conversion convert too, or is it paid in cash?
    #: A term of the contract, and a real amount: on a bullet loan it is every coupon.
    interest_converts: bool = True


@dataclass(frozen=True)
class EquityTerms:
    """What a subscriber holds, and what they are owed before the manager takes anything.

    ⚠️ `preferred_return` is a HURDLE, not a promise: the return subscribers must receive
    before carried interest begins. Nothing guarantees the fund earns it. Stored beside a
    lender's `rate` without saying so is how the two come to sit on one screen under one
    word — and one of them is owed whatever happens, the other is not.
    """

    #: Annual return served to subscribers before any carried interest, as a fraction.
    preferred_return: float = 0.0
    #: The manager's share of what exceeds the hurdle, as a fraction.
    carried_interest: float = 0.0


def terms_kind(instrument: str) -> type[LoanTerms] | type[EquityTerms]:
    """The terms class an instrument requires. One place answers it."""
    if instrument == LOAN:
        return LoanTerms
    if instrument == EQUITY:
        return EquityTerms
    raise ValueError(f"Unknown instrument {instrument!r}.")


def may_convert(instrument: str, terms: LoanTerms | EquityTerms | None) -> bool:
    """Can this holding become a subscription?

    ONE DIRECTION ONLY. A loan converts into a subscription; a subscription does not become
    a loan. Turning equity back into debt would move an investor ahead of the others in a
    wind-down after the fact, which is not a conversion — it is a preference given to one
    creditor, and those get unwound.
    """
    return instrument == LOAN and bool(getattr(terms, "convertible", False))
