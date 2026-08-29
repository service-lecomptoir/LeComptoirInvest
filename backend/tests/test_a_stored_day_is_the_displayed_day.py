"""A day stored in the database is the day displayed. The schema says which columns are days.

🔴 THE RULE: a `Date` column is three numbers, not an instant. It carries no hour, so no
zone, so nothing to convert. Every defect in this family came from treating one as a point
in time, and they arrive in two mirrored halves:

  * READING -- `new Date('2025-04-01')` is parsed as UTC by specification, so WEST of
    Greenwich it renders the day before. Reported from the screen: a lease starting on
    1 April read as 31 March.
  * WRITING -- `toISOString().slice(0, 10)` reads a local moment back in UTC, so EAST of
    Greenwich, in the hours after midnight, it STORES the day before. Worse, a date built
    as `new Date(y, m, 1)` is LOCAL midnight, which in Paris is 22:00 UTC the previous
    day: a statistics page that opened on the wrong month every single time, in France.

⚠️ THIS GUARD READS THE SCHEMA, NOT A NAMING HABIT. Three earlier versions guessed at
names -- `_date`, then also `_from`/`_on`/`_start`/`_end` -- and each passed green over
live defects: first `period_start` and `installed_on`, then `established_at`,
`expires_at`, `issued_at`, which are `Date` columns wearing an instant's name. Excluding
`_at` by convention is precisely how the third version went wrong. Nothing is excluded by
name here; the models are the only authority on which columns are days.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODELS = ROOT / "app" / "models"
FRONT = ROOT.parent / "frontend" / "src"
DAY_LIB = ("day.ts",)
MIN_COLUMNS = 20

_DECLARED = re.compile(r"^\s*(\w+):\s*Mapped\[[^\]]*\bdate\b(?!time)[^\]]*\]", re.M)
_COLUMN = re.compile(
    r"^\s*(\w+):\s*Mapped\[[^\]]*\]\s*=\s*mapped_column\(\s*Date\b(?!Time)", re.M
)

WRITTEN_IN_UTC = re.compile(
    r"toISOString\(\)\s*\.\s*(?:slice|substring)\(\s*0\s*,\s*10\s*\)"
    r"|toISOString\(\)\s*\.\s*split\(\s*['\"]T['\"]\s*\)\s*\[\s*0\s*\]"
)

_DECLARES = re.compile(r"(export\s+)?(?:const|function)\s+(\w+)\s*=?\s*\(?\s*(\w+)")


def day_columns() -> set[str]:
    names: set[str] = set()
    for path in MODELS.rglob("*.py"):
        source = path.read_text(encoding="utf-8", errors="ignore")
        names |= set(_DECLARED.findall(source)) | set(_COLUMN.findall(source))
    return names


_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _code_only(source: str) -> str:
    """The code, with the prose stripped out.

    🔴 A GUARD THAT READS COMMENTS REFUSES THE TEXT EXPLAINING THE DEFECT IT PREVENTS.
    This one flagged its own fix: the comment above the repaired line quotes
    `new Date(value)` to say what used to be there and why it was wrong, and the scan
    read it as the offence. Every note in this repository explaining a past defect would
    have to be deleted or contorted to keep the suite green -- which is how the reasons
    for a fix get erased, and the fix reverted a year later by someone who never saw them.
    """
    without_blocks = _BLOCK_COMMENT.sub("", source)
    return chr(10).join(
        line
        for line in without_blocks.splitlines()
        if not line.lstrip().startswith(("//", "*"))
    )


def front_sources() -> list[tuple[pathlib.Path, str]]:
    if not FRONT.exists():
        return []
    return [
        (p, _code_only(p.read_text(encoding="utf-8", errors="ignore")))
        for p in sorted(FRONT.rglob("*.ts*"))
        if ".test." not in p.name and p.name not in DAY_LIB
    ]


def _suspects(sources):
    """Helpers building their own Date, split by how far they reach.

    ⚠️ SCOPE IS PART OF THE MEASUREMENT. `fmtDate` is declared privately in half a dozen
    pages; treating the name as global made ONE bad copy indict nine innocent call sites,
    and a guard that cries wolf gets an exception written into it, then another. A helper
    that is not exported cannot reach past its own file, so it is only held against it.

    ⚠️ THE WINDOW IS TAKEN AFTER THE MATCH, NEVER INSIDE IT. A single pattern with a
    greedy tail swallows the NEXT declaration into the previous match, and `finditer`
    never revisits it: the first version missed `dateFr` -- four live sites, including
    `acquisition_date` -- while reporting itself green.
    """
    exported: dict[str, str] = {}
    private: dict[str, dict[str, str]] = {}
    for path, src in sources:
        key = str(path.relative_to(FRONT))
        for match in _DECLARES.finditer(src):
            is_export, name, param = match.group(1), match.group(2), match.group(3)
            window = src[match.end() : match.end() + 300]
            if not re.search(r"new Date\(\s*" + re.escape(param) + r"\s*[)+]", window):
                continue
            if is_export:
                exported.setdefault(name, key)
            else:
                private.setdefault(key, {}).setdefault(name, key)
    return exported, private


def test_the_guard_knows_which_columns_are_days() -> None:
    """⚠️ A guard reading an empty model tree would be green for ever."""
    columns = day_columns()
    assert len(columns) >= MIN_COLUMNS, (
        f"only {len(columns)} date-only columns found under {MODELS}: watching nothing"
    )


def test_no_stored_day_is_parsed_as_an_instant() -> None:
    """🔴 Shows THE DAY BEFORE to every reader west of Greenwich."""
    columns, sources = day_columns(), front_sources()
    if not sources or not columns:
        return
    builder = re.compile(
        r"(?:new Date|parseISO|Date\.parse)\([^()]{0,80}?\b(?:"
        + "|".join(sorted(map(re.escape, columns)))
        + r")\b[^()]{0,20}?\)"
    )
    offenders = [
        f"{p.relative_to(FRONT)}: {hit}"
        for p, src in sources
        for hit in builder.findall(src)
        if "T00:00" not in hit
    ]
    assert not offenders, (
        "These build a Date from a column the schema says is a DAY. Parsed as UTC, they "
        "render the previous day west of Greenwich:\n" + "\n".join(offenders)
    )


def test_no_day_is_computed_through_utc() -> None:
    """🔴 WORSE: this half is a WRITE, and it is wrong in France too. The day that reaches
    the database is not the day that was chosen."""
    offenders = [
        f"{p.relative_to(FRONT)}: {hit}"
        for p, src in front_sources()
        for hit in WRITTEN_IN_UTC.findall(src)
    ]
    assert not offenders, (
        "`toISOString()` is UTC. Assemble the day from its local parts:\n"
        + "\n".join(offenders)
    )


def test_no_helper_that_receives_a_day_builds_its_own_instant() -> None:
    """⚠️ THE INDIRECT ROUTE, and it is how ONE shared helper hid five call sites at once.

    🔴 ANCHORED TO THE SCHEMA, NOT TO THE HELPER'S NAME. Flagging every function called
    `fmtDate` catches ones that only ever receive `starts_at` or `current_period_end` --
    real instants, correctly parsed. What matters is not what a helper is called but
    whether a DAY reaches it.
    """
    columns, sources = day_columns(), front_sources()
    if not sources or not columns:
        return
    exported, private = _suspects(sources)
    days = "|".join(sorted(map(re.escape, columns)))
    offenders: list[str] = []
    for path, src in sources:
        key = str(path.relative_to(FRONT))
        reachable = {**exported, **private.get(key, {})}
        if not reachable:
            continue
        calls = re.compile(
            r"\b("
            + "|".join(sorted(map(re.escape, reachable)))
            + r")\(\s*[^()]{0,60}?\b(?:"
            + days
            + r")\b"
        )
        for match in calls.finditer(src):
            offenders.append(
                f"{key}: {match.group(0)}  [declare dans {reachable[match.group(1)]}]"
            )
    assert not offenders, (
        "A column the schema calls a DAY reaches a helper that builds the Date itself, so "
        "it is parsed as UTC and every caller inherits it:\n"
        + "\n".join(sorted(set(offenders)))
    )


def test_the_guard_still_recognises_both_halves() -> None:
    """⚠️ MUTATION-PROOF BY CONSTRUCTION: a loosened pattern passes over live defects."""
    assert WRITTEN_IN_UTC.findall("d.toISOString().slice(0, 10)")
    assert WRITTEN_IN_UTC.findall("d.toISOString().split('T')[0]")
    assert not WRITTEN_IN_UTC.findall("d.toISOString()")


def test_the_guard_reads_code_and_not_the_prose_explaining_it() -> None:
    """🔴 IT FLAGGED ITS OWN FIX ONCE. A comment quoting the old, wrong line is exactly
    what a repaired file contains, and refusing it would force every explanation out of
    the codebase."""
    sample = _code_only(
        "// the old line was new Date(value), parsed as UTC"
        + chr(10)
        + "/* and here too: toISOString().slice(0, 10) */"
        + chr(10)
        + "const d = dayOf(value)"
        + chr(10)
    )
    assert "new Date(value)" not in sample
    assert "toISOString" not in sample
    assert "dayOf(value)" in sample
