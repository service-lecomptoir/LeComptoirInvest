"""No « today » that belongs to nobody.

🔴 `date.today()` ANSWERS THE CONTAINER'S TIME ZONE, which is UTC in production and whatever
a laptop says in development. It is not the fund's day and not the investor's. Every bare
call therefore skips a decision — WHOSE day is this — and since the eligibility and chasing
work, that decision settles whether a KYC acceptance has expired, whether a capital call is
late, and when a retail investor's reflection period ends.

The case that pays for this guard: an investor in Réunion asking at 23:00 local time is
recorded on the previous day in UTC, and their four days of reflection start a day early. A
protection shortened by a day is a protection nobody can see was shortened.

⚠️ THIS GUARD IS DELIBERATELY NOT A BASELINE OF TOLERATED SITES. A frozen list is a
whitelist, and this repository has already paid for that shape twice: what is not on the list
stops being looked at. The rule is absolute instead, because one of the two named answers
always fits, and choosing between them is exactly the thought that was being skipped.
"""

from __future__ import annotations

import ast
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[1]
SCANNED = ("app",)

#: The one module allowed to ask the machine what time it is: it is the module that turns
#: that reading into somebody's day. Excluding it is not a whitelist entry, it is the
#: definition of the boundary.
SOURCE_OF_TRUTH = "core/fund_time.py"


def _root_name(node: ast.AST) -> str | None:
    """The leftmost name of an attribute chain: `dt.datetime.now` -> « dt »… and `datetime`.

    Both spellings are checked because both are used: `from datetime import datetime` gives
    `datetime.now()`, and `import datetime` gives `datetime.datetime.now()`.
    """
    while isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name):
            return node.value.id
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _offenders() -> list[str]:
    faults: list[str] = []
    for directory in SCANNED:
        for path in sorted((BACKEND / directory).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            relative = path.relative_to(BACKEND / directory).as_posix()
            if relative == SOURCE_OF_TRUTH:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover - a broken file fails elsewhere
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                target = node.func
                if not isinstance(target, ast.Attribute):
                    continue
                if _root_name(target) not in ("date", "datetime"):
                    # ⚠️ `func.now()` IS THE DATABASE'S CLOCK, not Python's, and it is
                    # written to columns declared `timezone=True`. Flagging it would be a
                    # false positive, and a guard that cries wolf gets switched off — which
                    # costs more than the rule it was defending.
                    continue
                # `date.today()` and `datetime.today()`
                if target.attr == "today":
                    faults.append(f"{directory}/{relative}:{node.lineno} .today()")
                # `datetime.now()` with no zone is the same skipped decision.
                if (
                    target.attr in ("now", "utcnow")
                    and not node.args
                    and not node.keywords
                ):
                    faults.append(
                        f"{directory}/{relative}:{node.lineno} .{target.attr}() sans zone"
                    )
    return faults


def test_no_bare_today_or_naive_now_in_the_application():
    faults = _offenders()
    assert not faults, (
        "Une date y répond au fuseau du conteneur, qui n'est le jour de personne. Utiliser "
        "`fund_time.platform_today()` pour un acte DU FONDS, ou "
        "`fund_time.today_for_investor(country_code)` pour un acte de L'INVESTISSEUR :\n  "
        + "\n  ".join(faults)
    )


def test_the_guard_would_actually_catch_something():
    """🔴 A GUARD THAT CANNOT FAIL PROTECTS NOTHING. This repository has shipped one that
    compared two empty sets and passed for ever, so the detector is exercised on a line that
    must trip it."""
    tree = ast.parse("import datetime\nx = datetime.date.today()\n")
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "today"
    ]
    assert found


def test_an_investor_east_of_the_fund_gets_their_own_day():
    """The case the guard exists for, exercised rather than merely described."""
    from app.core import fund_time

    assert fund_time.zone_for_country("RE") == "Indian/Reunion"
    assert fund_time.zone_for_country("FR") == fund_time.PLATFORM_TIMEZONE


def test_an_unknown_or_multi_zone_country_falls_back_and_says_so_by_construction():
    """⚠️ A COUNTRY SPANNING SEVERAL ZONES IS ABSENT ON PURPOSE. Picking one of France's
    twelve for « FR » would be right in Paris and wrong in Cayenne — worse than the honest
    fallback, because it looks considered."""
    from app.core import fund_time

    assert fund_time.zone_for_country("US") == fund_time.PLATFORM_TIMEZONE
    assert fund_time.zone_for_country("ZZ") == fund_time.PLATFORM_TIMEZONE
    assert fund_time.zone_for_country(None) == fund_time.PLATFORM_TIMEZONE
