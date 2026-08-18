"""How an investment actually performed: the four figures every fund is asked for.

🔴 THE HARD PART IS NOT THE ARITHMETIC, IT IS SAYING WHAT IS NOT KNOWN. Three of the four
standard measures need the RESIDUAL VALUE of what is still held, and this product does not
value anything: it records what came in and what went out. A tool that quietly treated the
residual as zero would publish an IRR and a TVPI that are systematically too low for every
open fund, and both would look perfectly reasonable — an under-stated return is the error
nobody disputes.

So the split is explicit and it runs through the whole module:

  * DPI and the REALISED IRR are computed from facts alone. They are complete answers to
    the question « what has actually come back », and they need no valuation.
  * TVPI, RVPI and the full IRR need a valuation. Without one they are UNAVAILABLE, with a
    reason, in the same shape `accrual.Due` uses for a loan it cannot measure. Passing a
    valuation in makes them appear; inventing one here never will.

⚠️ AN IRR IS A RATE, NOT A RANKING. Two investors who put the same money into the same
fund on different dates have different IRRs and neither is doing better than the other.
It is reported per investor because that is what they ask for, and it is not comparable
between them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

#: The day count an IRR is computed on. Stated rather than implied: an annualised rate
#: means nothing until the length of a year is agreed, and ACT/365 is the convention this
#: product already applies to its loans (`accrual.DAY_COUNT`).
IRR_DAY_COUNT = "ACT/365"
_YEAR_DAYS = Decimal("365")

#: A rate below −100 % has no meaning: an investor cannot lose more than everything they
#: put in, so the solver never looks there.
_LOWER_BOUND = -0.9999
#: Ten thousand per cent a year. Not a plausible answer, a bracket: a search that has to go
#: past it is not converging on anything, and saying so beats returning the bound.
_UPPER_BOUND = 100.0
_MAX_ITERATIONS = 200
#: Half a minor unit on a million: close enough that no reader could act on the difference.
_TOLERANCE = Decimal("0.000001")


@dataclass(frozen=True)
class Flow:
    """One dated movement, from the INVESTOR'S point of view.

    ⚠️ THE SIGN IS THE INVESTOR'S, NOT THE FUND'S, and getting it backwards produces a
    plausible rate of the wrong sign. Money they paid in is negative — it left them; money
    they received is positive. The fund's books read the mirror image, which is exactly why
    the convention is written here rather than assumed at each call site.
    """

    on: date
    amount: Decimal


@dataclass(frozen=True)
class Performance:
    """What came back, and what can honestly be said about what has not yet.

    Every ratio is `None` when it could not be computed, and `unavailable_reason` says
    which fact was missing. A zero would read as « no return », which is a different
    statement and a false one.
    """

    currency: str
    as_of: date
    #: Money the investor actually put in.
    paid_in: Decimal
    #: Money actually paid back to them, capital and income together, before withholding.
    distributed: Decimal
    #: The valuation of what is still held, when one was supplied.
    residual_value: Decimal | None = None

    #: Distributions over paid-in. Computable from facts alone: what has come back.
    dpi: Decimal | None = None
    #: Residual over paid-in. Needs a valuation.
    rvpi: Decimal | None = None
    #: (Distributions + residual) over paid-in. Needs a valuation.
    tvpi: Decimal | None = None
    #: Annualised money-weighted return. Realised when no valuation was supplied, and
    #: `irr_is_realised_only` then says so.
    irr: Decimal | None = None
    irr_is_realised_only: bool = True
    #: Why a figure is missing, when one is. Reaches the screen; never swallowed.
    unavailable_reason: str | None = None

    @property
    def moic(self) -> Decimal | None:
        """Multiple on invested capital. The same number as TVPI, under the name a
        crowdfunding investor is more likely to recognise. Exposed rather than left to be
        recomputed on a screen, where the two would eventually drift apart."""
        return self.tvpi


def _npv(rate: float, flows: list[Flow], origin: date) -> Decimal:
    """Present value of the flows at `rate`, discounted from the first one."""
    total = Decimal("0")
    for flow in flows:
        years = Decimal((flow.on - origin).days) / _YEAR_DAYS
        total += flow.amount / Decimal(str((1.0 + rate) ** float(years)))
    return total


def internal_rate_of_return(flows: list[Flow]) -> tuple[Decimal | None, str | None]:
    """The annualised money-weighted return of a set of dated flows, or why there is none.

    🔴 IT REFUSES RATHER THAN RETURNS A BOUND. A bisection that never brackets a root has
    not found a rate; handing back the edge of the search would publish « 10 000 % » or
    « −99.99 % » as a performance. Both are shapes of « no answer », and a fund report is
    the last place to dress one up as a figure.

    ⚠️ FLOWS ALL OF ONE SIGN HAVE NO IRR, and that is a real and frequent state: an
    investor who has paid in and received nothing yet. The answer is not zero, not minus a
    hundred per cent — it is that the question has no solution yet, and the reason says so.
    """
    if len(flows) < 2:
        return None, (
            "Un taux de rendement demande au moins deux mouvements datés : un versement et "
            "un retour."
        )
    ordered = sorted(flows, key=lambda f: f.on)
    if all(f.amount >= 0 for f in ordered) or all(f.amount <= 0 for f in ordered):
        return None, (
            "Tous les mouvements vont dans le même sens : tant que rien n'est revenu (ou "
            "que rien n'a été versé), aucun taux de rendement n'existe."
        )
    origin = ordered[0].on
    if ordered[-1].on == origin:
        return None, (
            "Tous les mouvements portent la même date : un rendement annualisé n'a pas de "
            "sens sur une durée nulle."
        )

    low, high = _LOWER_BOUND, _UPPER_BOUND
    value_low = _npv(low, ordered, origin)
    value_high = _npv(high, ordered, origin)
    if value_low * value_high > 0:
        # No sign change across the whole bracket: nothing to converge on. Non-conventional
        # flows (several sign changes) can genuinely have several roots or none, and
        # picking one would be arbitrary.
        return None, (
            "Aucun taux ne rend la valeur actuelle nulle sur la plage recherchée : la suite "
            "de mouvements n'admet pas de rendement unique."
        )

    for _ in range(_MAX_ITERATIONS):
        middle = (low + high) / 2
        value = _npv(middle, ordered, origin)
        if abs(value) < _TOLERANCE:
            return Decimal(str(round(middle, 6))), None
        if value * value_low > 0:
            low, value_low = middle, value
        else:
            high, value_high = middle, value
    # Bisection always narrows; reaching here means the bracket collapsed without the value
    # ever getting small, which is a degenerate flow set rather than a slow one.
    if abs(high - low) < 1e-9:
        return Decimal(str(round((low + high) / 2, 6))), None
    return None, "Le taux de rendement n'a pas convergé sur cette suite de mouvements."


def measure(
    *,
    currency: str,
    as_of: date,
    flows: list[Flow],
    residual_value: Decimal | None = None,
) -> Performance:
    """The four figures, computed from what is known and silent about what is not.

    `residual_value` is what the investor still holds, valued. Supply it and TVPI, RVPI and
    a full IRR appear; leave it out and the answer is limited to what actually came back,
    which is stated rather than implied.
    """
    paid_in = -sum((f.amount for f in flows if f.amount < 0), Decimal("0"))
    distributed = sum((f.amount for f in flows if f.amount > 0), Decimal("0"))

    if paid_in <= 0:
        return Performance(
            currency=currency,
            as_of=as_of,
            paid_in=Decimal("0"),
            distributed=distributed,
            residual_value=residual_value,
            unavailable_reason=(
                "Aucun versement n'a encore été constaté : il n'y a pas de capital investi "
                "sur lequel mesurer un rendement."
            ),
        )

    dpi = distributed / paid_in
    rvpi = tvpi = None
    if residual_value is not None:
        rvpi = residual_value / paid_in
        tvpi = (distributed + residual_value) / paid_in

    # ⚠️ THE VALUATION ENTERS THE IRR AS A FLOW ON `as_of`, not as a correction afterwards.
    # It is what the investor would receive if everything were realised that day, and that
    # is precisely a cash flow on that date.
    irr_flows = list(flows)
    realised_only = residual_value is None
    if residual_value is not None and residual_value > 0:
        irr_flows.append(Flow(on=as_of, amount=residual_value))

    irr, irr_reason = internal_rate_of_return(irr_flows)

    reason = None
    if residual_value is None:
        reason = (
            "Aucune valorisation des positions ouvertes n'a été enregistrée : le TVPI, le "
            "RVPI et le rendement complet ne peuvent pas être calculés. Les chiffres "
            "affichés ne portent que sur ce qui est déjà revenu."
        )
    if irr_reason:
        reason = f"{reason} {irr_reason}".strip() if reason else irr_reason

    return Performance(
        currency=currency,
        as_of=as_of,
        paid_in=paid_in,
        distributed=distributed,
        residual_value=residual_value,
        dpi=dpi,
        rvpi=rvpi,
        tvpi=tvpi,
        irr=irr,
        irr_is_realised_only=realised_only,
        unavailable_reason=reason,
    )


__all__ = [
    "IRR_DAY_COUNT",
    "Flow",
    "Performance",
    "internal_rate_of_return",
    "measure",
]
