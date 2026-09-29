"""Amounts, days and rates as the READER writes them: the one place a figure becomes text.

🔴 A LETTER WROTE « 10000.00 EUR » AND « 2026-10-31 » (29 Sept 2026). Both are the database
speaking: four digits nobody groups, a point a French reader takes for a thousands mark,
a currency code instead of its sign, a date in the order no investor writes. Nothing was
wrong with the figures, which is why nobody saw it; everything was wrong with the text.

🔴 ONE HELPER, EVERY SENTENCE. The capital-call notice, its reminder, the annual statement
and every refusal the server words go through here, in the language in force
(`i18n.current_lang`, which `use_lang` sets to the reader's for a letter). A guard
(`tests_unit/test_figures_are_written_for_their_reader.py`) refuses a sentence that formats
a figure by itself: `.isoformat()`, `:.2f`, or `{amount} {currency}` side by side.

    fr   10 000,00 €     31 octobre 2026     5,00 %
    en   €10,000.00      31 October 2026     5.00%

⚠️ THE CURRENCY IS THE AMOUNT'S, NEVER ASSUMED. This fund is multi-currency: an XOF call has
no centime (`money.minor_units`) and prints « 3 000 000 F CFA », not « 3 000 000,00 € ». A
currency this table does not name prints its ISO code, which is never wrong.

⚠️ THE SPACES ARE NOT ORDINARY. French groups thousands with a NARROW no-break space and puts
a no-break space before the sign and before « % »: an ordinary space lets a phone break
« 10 000,00 » into « 10 » and « 000,00 € » on two lines, which reads as two amounts.

⚠️ NOT FOR MACHINES. The EPC QR payload, a CSV export or a JSON field keeps its plain decimal:
a bank parses them, and « 10 000,00 » is not a number to a parser.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.core import i18n, money

NBSP = " "
NNBSP = " "

#: The sign each language writes for a currency. Missing: the ISO code, which is never wrong.
_SIGNS: dict[str, dict[str, str]] = {
    "fr": {
        "EUR": "€",
        "USD": "$US",
        "GBP": "£GB",
        "CAD": "$CA",
        "CHF": "CHF",
        "XOF": f"F{NBSP}CFA",
        "XAF": f"F{NBSP}CFA",
    },
    "en": {
        "EUR": "€",
        "USD": "US$",
        "GBP": "£",
        "CAD": "CA$",
        "CHF": "CHF",
        "XOF": f"F{NBSP}CFA",
        "XAF": f"F{NBSP}CFA",
    },
}

_MONTHS: dict[str, tuple[str, ...]] = {
    "fr": (
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ),
    "en": (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
}


def _lang(lang: str | None) -> str:
    return i18n.normalise(lang) if lang else i18n.current_lang()


def number(
    value: Decimal | float | int, places: int = 2, lang: str | None = None
) -> str:
    """A plain figure, grouped and with the reader's decimal mark. No currency."""
    lang = _lang(lang)
    step = Decimal(1).scaleb(-places)
    quantized = Decimal(str(value)).quantize(step, rounding=ROUND_HALF_UP)
    sign = "-" if quantized < 0 else ""
    whole, _, fraction = f"{abs(quantized):.{places}f}".partition(".")
    group = NNBSP if lang == "fr" else ","
    grouped = ""
    while len(whole) > 3:
        grouped = group + whole[-3:] + grouped
        whole = whole[:-3]
    grouped = whole + grouped
    mark = "," if lang == "fr" else "."
    return sign + grouped + (mark + fraction if fraction else "")


def amount(value: Decimal | float | int, currency: str, lang: str | None = None) -> str:
    """An amount in its own currency, to that currency's minor unit."""
    lang = _lang(lang)
    code = (currency or "").upper()
    quantized = money.quantize(value, code)
    figure = number(abs(quantized), money.minor_units(code), lang)
    sign = "-" if quantized < 0 else ""
    mark = _SIGNS[lang].get(code, code)
    if lang == "fr":
        return f"{sign}{figure}{NBSP}{mark}"
    # English puts the sign first; a sign ending in a letter (« CHF », « F CFA ») keeps a
    # space from the figure, a symbol (« € », « US$ ») sticks to it.
    joint = NBSP if mark[-1:].isalpha() else ""
    return f"{sign}{mark}{joint}{figure}"


def day(value: date, lang: str | None = None) -> str:
    """A day in words: « 31 octobre 2026 », « 1er mars 2026 », « 31 October 2026 »."""
    lang = _lang(lang)
    month = _MONTHS[lang][value.month - 1]
    if lang == "fr":
        first = "1er" if value.day == 1 else str(value.day)
        return f"{first}{NBSP}{month}{NBSP}{value.year}"
    return f"{value.day}{NBSP}{month}{NBSP}{value.year}"


def percent(fraction: float | Decimal, places: int = 2, lang: str | None = None) -> str:
    """A rate given as a fraction: 0.05 is « 5,00 % » in French, « 5.00% » in English."""
    lang = _lang(lang)
    figure = number(Decimal(str(fraction)) * 100, places, lang)
    return f"{figure}{NBSP}%" if lang == "fr" else f"{figure}%"


__all__ = ["NBSP", "NNBSP", "amount", "day", "number", "percent"]
