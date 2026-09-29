"""Every amount, day and rate a sentence shows is written for its reader, by ONE helper.

🔴 THE DEFECT (29 Sept 2026): the capital-call letter wrote « 10000.00 EUR » and
« 2026-10-31 ». The figures were right; the text was the database's. It had been written that
way in the notice, in its reminder, in the annual statement and in eight refusals, each on
its own, which is why fixing one letter would have fixed nothing.

These guards read the SOURCE, so a sentence added tomorrow is held to the rule too:

  * a sentence (`pick(...)`) never formats a figure itself: no `.isoformat()`, no `:.2f`,
    no `{amount} {currency}` side by side;
  * a module that writes a letter or a document never does either, anywhere.

`app/core/display.py` is the one place allowed to, and its own output is pinned below.
"""

from __future__ import annotations

import ast
import pathlib
from datetime import date
from decimal import Decimal

from app.core import display, i18n

APP = pathlib.Path(__file__).resolve().parents[1] / "app"

#: The one module allowed to turn a figure into text.
HELPER = APP / "core" / "display.py"

#: What leaves the building for an investor: the letters, their envelope, the statement.
LETTER_MODULES = (
    APP / "core" / "notices.py",
    APP / "core" / "email_envelope.py",
    APP / "services" / "notice_service.py",
    APP / "services" / "statement_pdf.py",
    APP / "services" / "statement_service.py",
)

NB = display.NBSP
NN = display.NNBSP


def _is_isoformat(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "isoformat"
    )


def _decimal_spec(value: ast.FormattedValue) -> bool:
    """`{x:.2f}`, `{x:,.2f}`: a figure given its decimals by hand."""
    spec = value.format_spec
    if not isinstance(spec, ast.JoinedStr):
        return False
    text = "".join(part.value for part in spec.values if isinstance(part, ast.Constant))
    return "." in text and text.rstrip().endswith("f")


def _faults_in_fstring(node: ast.JoinedStr) -> list[str]:
    faults = []
    parts = node.values
    for index, part in enumerate(parts):
        if not isinstance(part, ast.FormattedValue):
            continue
        if _is_isoformat(part.value):
            faults.append("a day written with .isoformat()")
        if _decimal_spec(part):
            faults.append("a figure given its decimals with a format spec")
        # `{amount} {currency}`: an amount glued to its code by hand.
        nxt = parts[index + 1 : index + 3]
        if (
            len(nxt) == 2
            and isinstance(nxt[0], ast.Constant)
            and nxt[0].value == " "
            and isinstance(nxt[1], ast.FormattedValue)
            and ast.unparse(nxt[1].value).endswith("currency")
        ):
            faults.append("an amount and its currency code side by side")
    return faults


def _sources():
    for path in sorted(APP.rglob("*.py")):
        if path != HELPER:
            yield path, ast.parse(path.read_text(encoding="utf-8"))


def test_no_sentence_formats_a_figure_by_itself():
    faults = []
    for path, tree in _sources():
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "pick"
            ):
                continue
            for arg in node.args:
                for inner in ast.walk(arg):
                    if isinstance(inner, ast.JoinedStr):
                        for fault in _faults_in_fstring(inner):
                            faults.append(
                                f"{path.relative_to(APP)}:{inner.lineno} {fault}"
                            )
    assert not faults, (
        "A sentence formats a figure by itself; use app.core.display (amount, day, "
        "percent, number):\n  " + "\n  ".join(sorted(set(faults)))
    )


def test_no_letter_module_formats_a_figure_by_itself():
    faults = []
    for path in LETTER_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if _is_isoformat(node):
                faults.append(f"{path.relative_to(APP)}:{node.lineno} .isoformat()")
            if isinstance(node, ast.JoinedStr):
                for fault in _faults_in_fstring(node):
                    faults.append(f"{path.relative_to(APP)}:{node.lineno} {fault}")
    assert not faults, (
        "A letter or a document formats a figure by itself; use app.core.display:\n  "
        + "\n  ".join(sorted(set(faults)))
    )


def test_the_guard_sees_what_it_forbids():
    """⚠️ A GUARD THAT CANNOT FAIL PROVES NOTHING: it is shown the three shapes once."""
    source = (
        'f"{due.isoformat()}"\n'
        'f"{rate * 100:.2f} %"\n'
        'f"{call.amount} {call.currency}"\n'
    )
    found = [
        fault
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.JoinedStr)
        for fault in _faults_in_fstring(node)
    ]
    assert len(found) == 3


# ── The helper's own output ──────────────────────────────────────────────────────────


def test_an_amount_in_french():
    assert display.amount(Decimal("10000"), "EUR", "fr") == f"10{NN}000,00{NB}€"
    assert display.amount(Decimal("-1234.5"), "EUR", "fr") == f"-1{NN}234,50{NB}€"
    assert (
        display.amount(Decimal("3000000"), "XOF", "fr")
        == f"3{NN}000{NN}000{NB}F{NB}CFA"
    )
    assert display.amount(Decimal("12.5"), "CHF", "fr") == f"12,50{NB}CHF"


def test_an_amount_in_english():
    assert display.amount(Decimal("10000"), "EUR", "en") == "€10,000.00"
    assert display.amount(Decimal("10000"), "USD", "en") == "US$10,000.00"
    assert display.amount(Decimal("12.5"), "CHF", "en") == f"CHF{NB}12.50"
    assert display.amount(Decimal("-7"), "GBP", "en") == "-£7.00"


def test_an_unknown_currency_prints_its_code_never_a_wrong_sign():
    assert display.amount(Decimal("5"), "NOK", "fr") == f"5,00{NB}NOK"
    assert display.amount(Decimal("5"), "NOK", "en") == f"NOK{NB}5.00"


def test_a_day_in_words():
    assert display.day(date(2026, 10, 31), "fr") == f"31{NB}octobre{NB}2026"
    assert display.day(date(2026, 3, 1), "fr") == f"1er{NB}mars{NB}2026"
    assert display.day(date(2026, 10, 31), "en") == f"31{NB}October{NB}2026"


def test_a_rate():
    assert display.percent(0.05, lang="fr") == f"5,00{NB}%"
    assert display.percent(0.05, lang="en") == "5.00%"


def test_the_language_in_force_is_the_default():
    with i18n.use_lang("en"):
        assert display.amount(Decimal("1"), "EUR") == "€1.00"
    with i18n.use_lang("fr"):
        assert display.amount(Decimal("1"), "EUR") == f"1,00{NB}€"
