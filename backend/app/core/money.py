"""Money, and the one arithmetic rule a multi-currency fund may not break.

THE FUND IS MULTI-CURRENCY FROM THE FIRST LINE (user, 17 August 2026), and that decision was
taken knowing what the sister product paid for the opposite one: Le Comptoir Immo shipped
with the euro written into its formatting, its schemas and twenty-seven local helpers, and
undoing it took a sweep across the whole front end.

🔴 THE INVARIANT HOLDS PER CURRENCY, NEVER ACROSS THEM.

    treasury(X) = Σ contributions(X) − Σ deployments(X) + Σ returns(X) − Σ distributions(X)

One equation for each currency the fund touches. A single total mixing euros and shillings
is not a treasury: it is a number that is nothing anywhere, and it will look plausible
because it is the sum of real amounts. This is the same defect the sister product refused in
its tax returns — « totalling a French allowance with a Kenyan rate produces a number that
is a tax nowhere ».

⚠️ AND CONVERSION IS AN EVENT, NOT A FORMULA. Presenting a portfolio in one currency needs a
rate, and a rate belongs to a moment. A figure converted at today's rate and stored is a
figure that quietly becomes false tomorrow; a figure converted at the transaction's own rate
is history and stays true. Only the DISPLAY converts, and it says at which rate.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from app.core.i18n import pick

#: Currencies whose minor unit is not the hundredth. Rounding a Japanese yen to two decimals
#: invents a subdivision that does not exist, and a Kuwaiti dinar to two loses one.
_MINOR_UNITS: dict[str, int] = {
    "JPY": 0,
    "KRW": 0,
    "VND": 0,
    "XOF": 0,
    "XAF": 0,
    "XPF": 0,
    "CLP": 0,
    "ISK": 0,
    "BHD": 3,
    "KWD": 3,
    "OMR": 3,
    "TND": 3,
    "JOD": 3,
}


def minor_units(currency: str) -> int:
    """Decimal places this currency actually has. Two unless the currency says otherwise.

    ⚠️ XOF IS IN THIS TABLE, and it is not exotic here: it is the currency of Côte d'Ivoire,
    a market this house already serves. A CFA franc has no centime, and showing « 3 000 000,00 »
    to an Ivorian investor is not a formatting detail, it is a number their bank never writes.
    """
    return _MINOR_UNITS.get((currency or "").upper(), 2)


def quantize(amount: Decimal | float | int, currency: str) -> Decimal:
    """Round to the currency's own precision, half up, the way an invoice does.

    `Decimal`, not `float`: a fund adds thousands of amounts and a float loses a cent every
    few thousand additions, which is precisely the drift the treasury invariant is meant to
    detect. Detecting your own rounding error as a discrepancy is worse than useless.
    """
    places = Decimal(1).scaleb(-minor_units(currency))
    return Decimal(str(amount)).quantize(places, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Money:
    """An amount AND its currency, inseparably.

    THE PAIR IS THE POINT. An amount without its currency is the bug this class exists to
    make impossible: it adds, it compares, it totals, and nothing complains until an
    investor is paid in the wrong unit. Every arithmetic operation below refuses to work
    across currencies, loudly, at the moment of the mistake rather than at the audit.
    """

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", (self.currency or "").upper())
        if len(self.currency) != 3:
            raise ValueError(
                pick(
                    f"La devise {self.currency!r} n'est pas un code ISO 4217.",
                    f"Currency {self.currency!r} is not an ISO 4217 code.",
                )
            )
        object.__setattr__(self, "amount", quantize(self.amount, self.currency))

    def _same(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"Refusing to mix {self.currency} and {other.currency}. The treasury "
                f"invariant holds per currency; a total across two is a number that is a "
                f"balance nowhere. Convert explicitly, at a stated rate and date, if a "
                f"single figure is really wanted."
            )

    def __add__(self, other: "Money") -> "Money":
        self._same(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._same(other)
        return Money(self.amount - other.amount, self.currency)

    def __lt__(self, other: "Money") -> bool:
        self._same(other)
        return self.amount < other.amount

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"


def total(amounts: list[Money]) -> dict[str, Money]:
    """Sum a mixed list INTO ONE TOTAL PER CURRENCY. Never into one number.

    Returns a mapping rather than a figure, and that shape is the whole argument: a caller
    that wanted a single total has to decide, in the open, what to do with the second
    currency. A function returning one number would make that decision for them, silently,
    and always the same wrong way.
    """
    out: dict[str, Money] = {}
    for money in amounts:
        current = out.get(money.currency)
        out[money.currency] = money if current is None else current + money
    return out
