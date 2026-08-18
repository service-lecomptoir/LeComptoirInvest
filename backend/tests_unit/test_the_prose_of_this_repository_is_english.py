"""Comments and docstrings are written in English. The messages people read are not.

🔴 WHY THIS GUARD EXISTS, AND WHY IT WAS WRITTEN AFTER THE DRIFT AND NOT BEFORE. Nine files
of this product were committed on 18 August 2026 with their prose in French — every one of
them written that same day, by the same hand, in a repository whose rule is English. Nothing
failed: prose has no compiler, the tests were green, and the drift was found by a person
reading the code rather than by anything automatic.

That is exactly the shape this repository has paid for before, in the sister products: a
convention that lives only in someone's memory holds until the day it is busy. The two
existing anti-French ratchets there cover identifiers and blocks of prose; this product had
neither, being younger. It has one now.

⚠️ THE LINE THIS GUARD DOES NOT CROSS. A refusal an operator reads, an error message, a
label — those stay French until they go through i18n, and touching them would break the
product for its users to satisfy a rule about source code. So the guard reads ONLY comments
and docstrings, and it says so by construction: it strips string literals before looking.
"""

from __future__ import annotations

import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCANNED = ("app", "tests", "tests_unit")

#: Function words that are French and are not English. « Note », « double », « point » and
#: their kind are deliberately absent: they are words in both languages, and a guard that
#: fires on them teaches people to disable it.
_FRENCH = re.compile(
    r"\b(le|la|les|une|des|dans|pour|qui|que|est|sont|avec|sur|par|cette|leur|aux|"
    r"du|au|ses|nous|vous|elle|ils|elles|ainsi|donc|alors|parce|jamais|toujours|"
    r"chaque|tant|lorsque|puisque|celui|celle|ceux)\b",
    re.I,
)

#: Three function words on one line. One or two catch « la » in a quoted French message and
#: « des » in an accented name; three together are a sentence, and a sentence in a comment
#: is prose.
_THRESHOLD = 3


def _prose_lines(source: str) -> list[tuple[int, str]]:
    """Every comment line and docstring line, with string literals left out.

    Docstrings are read through the AST rather than by pattern, so an ordinary string that
    merely looks like one — a French refusal spanning three lines, for instance — is never
    mistaken for prose.
    """
    found: list[tuple[int, str]] = []

    for number, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            found.append((number, stripped))

    try:
        tree = ast.parse(source)
    except SyntaxError:  # pragma: no cover - a file that does not parse fails elsewhere
        return found
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        doc = ast.get_docstring(node, clean=False)
        if not doc:
            continue
        start = getattr(node, "lineno", 1)
        for offset, line in enumerate(doc.splitlines()):
            found.append((start + offset, line.strip()))
    return found


def _offenders() -> list[str]:
    faults: list[str] = []
    for directory in SCANNED:
        for path in sorted((ROOT / directory).rglob("*.py")):
            if "__pycache__" in path.parts or path.name == pathlib.Path(__file__).name:
                continue
            source = path.read_text(encoding="utf-8")
            for number, line in _prose_lines(source):
                if len(_FRENCH.findall(line)) >= _THRESHOLD:
                    faults.append(
                        f"{path.relative_to(ROOT).as_posix()}:{number} {line}"
                    )
    return faults


def test_no_comment_or_docstring_is_written_in_french():
    faults = _offenders()
    assert not faults, (
        f"{len(faults)} ligne(s) de prose en français dans le code. Les commentaires et les "
        "docstrings s'écrivent en anglais ; seuls les messages lus par un utilisateur "
        "restent en français.\n  " + "\n  ".join(faults)
    )


def test_the_guard_would_actually_catch_something():
    """🔴 A GUARD THAT CANNOT FAIL PROTECTS NOTHING, and this repository has shipped one
    before: a check comparing two empty sets passed for ever. So the detector is exercised
    on a line that must trip it, and on one that must not."""
    prose = "# Le montant est calculé pour chaque investisseur du fonds"
    assert len(_FRENCH.findall(prose)) >= _THRESHOLD

    english = "# The amount is computed for every investor in the fund"
    assert len(_FRENCH.findall(english)) < _THRESHOLD


def test_a_french_message_a_user_reads_is_not_prose():
    """⚠️ THE LINE THE GUARD MUST NOT CROSS. A refusal shown on screen is French on
    purpose; if the guard fired on those, the only way to satisfy it would be to break the
    product for the people using it."""
    source = (
        "def refuse():\n"
        "    raise ValueError(\n"
        '        "Les prêteurs restent dus : aucune somme ne peut aller aux souscripteurs "\n'
        '        "tant que cette dette n\'est pas couverte."\n'
        "    )\n"
    )
    assert _prose_lines(source) == []
