"""A label that comes from the SERVER is translated at the SERVER, and stays that way.

🔴 TWO MEASUREMENTS, BECAUSE ONE OF THEM CANNOT BE TRUSTED ALONE.

The obvious guard is « find French prose that is not inside `pick` ». It works, and it is
built below - but it is built second, on purpose. Recognising French means recognising its
orthography, and « Statut inconnu : {status}. Attendus : ... » carries no accent and no
article. It sat in two `raise` sites through an entire sweep and was only found because a
patch aimed at one of them reported zero matches. A DETECTOR OF FRENCH IS A GOOD SIGNAL AND
A BAD TEST, which is this repository's most expensive recurring shape: a guard narrower than
its rule reads exactly like a guard that holds it.

So the first measurement does not look at language at all. It looks at the SLOTS a message
reaches a reader through - the detail of an `HTTPException`, the message of a raised
`ValueError`, the `unavailable_reason` of an answer that refuses - and requires every literal
sitting in one to be a `pick(fr, en)` call. A message written in flawless English in one of
those slots fails too, and that is correct: an English-only refusal is untranslated for the
French reader this product was built for.

⚠️ WHAT NEITHER ONE CATCHES: a message assembled into a local variable and handed on later,
if it happens to be accent-free. Written down rather than left to be discovered.
"""

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[1] / "app"

#: Where a sentence goes when a reader is meant to see it. Positional for the exceptions
#: (`HTTPException(status, detail)`), by name for everything the domain returns.
READER_KEYWORDS = frozenset(
    {
        "detail",
        "unavailable_reason",
        "blocked_reason",
        "explanation",
        "refusal_reason",
    }
)
#: Raised, then turned into a 4xx by the route that called it. The message travels.
READER_EXCEPTIONS = frozenset({"HTTPException", "ValueError"})

#: 🔴 THE VERDICTS. Two strings stay French, and each one is a decision rather than a
#: remainder. A sweep that leaves things behind without naming them reports itself as
#: complete; this is what stops that.
SETTLED: dict[str, str] = {
    # The brand. It is a name, and a name is not translated - Le Comptoir Immo does not
    # become The Property Counter in an English browser.
    "Le Comptoir Invest": "brand name",
    # The account name written into the database when a fund is bootstrapped with nobody
    # able to administer it. ⚠️ IT IS DATA, NOT A LABEL: a seed is written once and read
    # for ever after, so it can never re-translate itself at read time - the sister product
    # paid for that lesson. Translating it would take a migration for one row that its
    # holder renames in a single click.
    "Gestion du fonds": "seeded data, renamed by its holder",
}

#: 🔴 RAISED WHEN A CALLER IS BROKEN, NOT WHEN A USER ASKED FOR SOMETHING IMPOSSIBLE, and
#: the difference decides who the sentence is addressed to. None of these can be provoked
#: from a screen: the routes validate before they get here. They report a defect to whoever
#: maintains the product, and a bilingual version would imply a reader who is not there.
#:
#: ⚠️ THE TEST BELOW MATCHES ON A PREFIX, so the entry names enough of the sentence to be
#: unmistakable and stops before anything that might be reworded.
PROGRAMMING_ERRORS: dict[str, str] = {
    "Unknown instrument {}: it has no place in this order": (
        "an instrument was added without being placed in the distribution order"
    ),
    "Unknown instrument {}.": "terms_kind is called with something the routes reject first",
    "Unknown KYC status {}.": "the dataclass invariant; the API validates before this",
    "Refusing to mix {} and {}": (
        "the per-currency treasury invariant: a caller totalling two currencies"
    ),
}

_ACCENTS = "àâäéèêëîïôöùûüçÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ«»"


def _is_pick(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and (getattr(node.func, "id", None) or getattr(node.func, "attr", None))
        == "pick"
    )


def _literal(node: ast.AST) -> str | None:
    """The text of a plain string or an f-string, or None when it is neither."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            p.value if isinstance(p, ast.Constant) else "{}" for p in node.values
        )
    return None


def _sources() -> list[tuple[pathlib.Path, ast.Module]]:
    out = []
    for path in sorted(APP.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        out.append((path, ast.parse(path.read_text(encoding="utf-8"))))
    return out


def _reader_slots(tree: ast.Module):
    """Every expression this file puts in front of a reader, with where it is."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name in READER_EXCEPTIONS:
            for arg in node.args:
                yield node.lineno, arg
        for keyword in node.keywords:
            if keyword.arg in READER_KEYWORDS:
                yield node.lineno, keyword.value


def test_every_reader_facing_message_is_written_in_both_languages():
    """The measurement that does not care what language anything is in."""
    untranslated = []
    for path, tree in _sources():
        for lineno, node in _reader_slots(tree):
            text = _literal(node)
            if text is None:
                continue  # a variable, a status code, an already-built message
            if len(text) < 12 or text in SETTLED:
                continue
            if any(text.startswith(prefix) for prefix in PROGRAMMING_ERRORS):
                continue
            untranslated.append(f"{path.name}:{lineno}  {text[:70]}")

    assert not untranslated, (
        "Ces messages atteignent un lecteur sans passer par pick(fr, en) :\n  "
        + "\n  ".join(untranslated)
        + "\n\nUn libelle qui vient du serveur se traduit au serveur : ni le PDF, ni "
        "l'e-mail, ni l'export CSV n'ont de front-end pour le faire a leur place."
    )


def test_no_french_prose_survives_outside_pick_without_a_verdict():
    """The second measurement, and the weaker one. It reads orthography, so it misses
    French that happens to carry no accent - which is precisely why it is not alone."""
    stray = []
    for path, tree in _sources():
        settled_ids = set()
        for node in ast.walk(tree):
            if _is_pick(node):
                for arg in node.args:
                    settled_ids.update(id(inner) for inner in ast.walk(arg))
            if isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ) and ast.get_docstring(node):
                settled_ids.add(id(node.body[0].value))

        for node in ast.walk(tree):
            if id(node) in settled_ids:
                continue
            text = _literal(node)
            if text is None or len(text) < 12 or text in SETTLED:
                continue
            if any(char in _ACCENTS for char in text):
                stray.append(f"{path.name}:{node.lineno}  {text[:70]}")

    assert not stray, (
        "Ces chaines francaises ne sont ni traduites ni classees :\n  "
        + "\n  ".join(stray)
        + "\n\nSoit elles passent par pick(fr, en), soit elles rejoignent SETTLED avec le "
        "motif qui les y garde."
    )


def test_a_verdict_that_names_nothing_is_removed():
    """SETTLED must describe what exists. An entry left behind after its string was
    translated would quietly excuse the next string that happens to match it."""
    blob = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(APP.rglob("*.py"))
        if "__pycache__" not in path.parts
    )
    verdicts = list(SETTLED) + [
        # The prefixes carry `{}` where the source has an interpolation, so the comparison
        # is made on the half that is literal.
        prefix.split("{")[0]
        for prefix in PROGRAMMING_ERRORS
    ]
    stale = [text for text in verdicts if text not in blob]
    assert not stale, "Ces verdicts ne correspondent plus a rien :\n  " + "\n  ".join(
        stale
    )
