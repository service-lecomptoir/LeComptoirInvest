"""The code is written in ENGLISH -- comments and docstrings included.

🔴 THE RULE EXISTED AND NOTHING APPLIED IT. It is written down, it is repeated, and it is
still broken every few sessions: over one session six French docstrings were written
without noticing, and the rule was reported as respected twice while it was not. A rule
enforced by somebody's attention is a rule the reader has to re-check by hand, which is
not a rule. This file is the rule made mechanical.

⚠️ THE UI STAYS FRENCH. What the screen shows goes through i18n and is a VALUE, not prose
about the code. So string literals are never read here, and French quoted between « » or
"" inside an English sentence is allowed: naming a real button in English would describe
something that does not exist.

⚠️ A RATCHET, NOT A CLEAN SWEEP. These repositories still hold French comments written
before the rule. A guard demanding zero would fail the day it lands and be switched off
within the hour. `english_only_baseline.txt` therefore freezes what exists TODAY, by
fingerprint, and only NEW prose fails. Cleaning up stays free: translate the block, drop
its fingerprint.

⚠️ THE FINGERPRINT IS ON THE TEXT, NOT THE FILE. Moving or renaming a file must not
resurrect an entry nobody touched.

To re-freeze after a deliberate bulk change:
    python -m tests_unit.test_english_only        (or: python <this file>)
"""

from __future__ import annotations

import ast
import hashlib
import pathlib
import re
import sys
import unittest

#: Where the code lives, relative to this file's repository root. Configured per
#: repository; everything else in this file is identical everywhere on purpose -- one
#: implementation, six configurations, so a fix travels instead of being re-invented.
PY_ROOTS: tuple[str, ...] = (
    "backend/app",
    "backend/tests",
    "backend/tests_unit",
)
TS_ROOTS: tuple[str, ...] = ("frontend/src",)

#: Resolved from this file so the guard runs from any working directory.
REPO = pathlib.Path(__file__).resolve().parents[2]
BASELINE = pathlib.Path(__file__).with_name("english_only_baseline.txt")

# Function words with no English meaning of their own. Deliberately NOT here: `on`,
# `par`, `son`, `sans`, `plus`; `pour` is fine but `part`, `point`, `force` are not --
# a false positive is exactly how a guard gets switched off.
FRENCH_WORDS = set(
    """
    le la les des une dans pour avec donc qui que est sont pas leur cette ces nous vous
    aux ses tout tous quand alors mais ainsi cela chaque entre vers depuis jamais
    toujours celui celle ceux elles ils dont encore déjà aussi être était étaient
    parce lorsque puisque afin cet ceci celà lequel laquelle plutôt sinon néanmoins
    """.split()
)

# Two distinct markers, never one: a lone « la » in an English sentence is noise, two of
# them is French. This is what keeps the guard quiet enough to survive.
MIN_MARKERS = 2

_QUOTED = re.compile(r"«[^»]*»|\"[^\"]*\"|“[^”]*”|'[^']{4,}'")
_WORD = re.compile(r"[a-zà-ÿ]+", re.IGNORECASE)


def _is_french(text: str) -> bool:
    """Does this READ as French, once every quotation is taken out?"""
    stripped = _QUOTED.sub(" ", text)
    found = {w.lower() for w in _WORD.findall(stripped) if w.lower() in FRENCH_WORDS}
    return len(found) >= MIN_MARKERS


def fingerprint(text: str) -> str:
    """Stable key for one block of prose: whitespace-normalised, then hashed."""
    return hashlib.sha1(" ".join(text.split()).encode("utf-8")).hexdigest()[:12]


def _python_blocks(path: pathlib.Path) -> list[tuple[str, int]]:
    """(text, line) of every comment, docstring and assertion message in a Python file."""
    source = path.read_text(encoding="utf-8")
    out: list[tuple[str, int]] = []

    for number, line in enumerate(source.splitlines(), start=1):
        # `#` inside a string is not a comment; requiring the line to START with it
        # leaves trailing comments out, which is a deliberate narrowing: they are short,
        # and short text rarely reaches two markers anyway.
        stripped = line.strip()
        if stripped.startswith("#"):
            out.append((stripped.lstrip("# "), number))

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return out

    for node in ast.walk(tree):
        if isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            doc = ast.get_docstring(node, clean=True)
            if doc:
                out.append((doc, getattr(node, "lineno", 1)))
        elif isinstance(node, ast.Assert) and isinstance(node.msg, ast.Constant):
            if isinstance(node.msg.value, str):
                out.append((node.msg.value, node.lineno))
        elif isinstance(node, ast.Assert) and isinstance(
            node.msg, ast.JoinedStr | ast.BinOp
        ):
            # `assert x, ("a" "b")` -- an implicitly joined message, which is how every
            # long one is written. Without this branch the guard would miss exactly the
            # messages long enough to be French prose.
            pieces = [
                sub.value
                for sub in ast.walk(node.msg)
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str)
            ]
            if pieces:
                out.append((" ".join(pieces), node.lineno))
    return out


def _ts_blocks(path: pathlib.Path) -> list[tuple[str, int]]:
    """(text, line) of every comment in a TypeScript/JavaScript file.

    🔴 A REAL SCAN, NOT A LINE FILTER. A first version elsewhere judged lines starting
    with « // » or « * », and the MIDDLE line of a block comment starts with neither: it
    reported the very sentence explaining a fix. A guard that shouts at its own comment
    teaches the next reader to ignore it.

    ⚠️ STRINGS AND TEMPLATES ARE SKIPPED, not merely ignored: the scanner must ENTER them
    to know where they end, otherwise an apostrophe in a French UI label would swallow the
    rest of the file as if it were a string. That is the difference between skipping a
    string and being lost inside one.
    """
    source = path.read_text(encoding="utf-8")
    out: list[tuple[str, int]] = []
    i, n, line = 0, len(source), 1
    while i < n:
        ch = source[i]
        two = source[i : i + 2]
        if two == "//":
            start, j = line, i + 2
            while j < n and source[j] != "\n":
                j += 1
            out.append((source[i + 2 : j].strip(), start))
            i = j
        elif two == "/*":
            start, j = line, i + 2
            while j < n and source[j : j + 2] != "*/":
                if source[j] == "\n":
                    line += 1
                j += 1
            body = source[i + 2 : j]
            # Strip the decorative leading « * » of a JSDoc block, so the text reads as
            # a sentence rather than as a column of stars.
            text = " ".join(ln.strip().lstrip("*").strip() for ln in body.splitlines())
            out.append((text.strip(), start))
            i = j + 2
        elif ch in "\"'`":
            quote, j = ch, i + 1
            while j < n:
                if source[j] == "\\":
                    j += 2
                    continue
                if source[j] == "\n":
                    line += 1
                if source[j] == quote:
                    break
                j += 1
            i = j + 1
        else:
            if ch == "\n":
                line += 1
            i += 1
    return out


def collect_offenders() -> dict[str, str]:
    """{fingerprint: "path:line  first words"} for every French block found."""
    offenders: dict[str, str] = {}
    plan = [
        (PY_ROOTS, ("*.py",), _python_blocks),
        (TS_ROOTS, ("*.ts", "*.tsx"), _ts_blocks),
    ]
    for roots, patterns, reader in plan:
        for root in roots:
            base = REPO / root
            if not base.exists():
                continue
            for pattern in patterns:
                for path in sorted(base.rglob(pattern)):
                    if any(
                        part in {"node_modules", ".venv", "dist", "build"}
                        for part in path.parts
                    ):
                        continue
                    for text, line in reader(path):
                        if _is_french(text):
                            where = path.relative_to(REPO).as_posix()
                            extract = " ".join(text.split())[:70]
                            offenders.setdefault(
                                fingerprint(text), f"{where}:{line}  {extract}"
                            )
    return offenders


def _allowed() -> set[str]:
    if not BASELINE.exists():
        return set()
    return {
        line.split("#", 1)[0].strip()
        for line in BASELINE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


class EnglishOnly(unittest.TestCase):
    """⚠️ A `TestCase` RATHER THAN PLAIN FUNCTIONS, so that the very same file runs under
    pytest and under Django's unittest runner. Five of these products use pytest and one
    does not; writing the guard twice would have given the rule two spellings on day one.
    """

    def test_no_french_prose_beyond_the_baseline(self) -> None:
        fresh = {
            key: where
            for key, where in collect_offenders().items()
            if key not in _allowed()
        }
        self.assertFalse(
            fresh,
            "New French comment(s) or docstring(s). The code of this product is written "
            "in ENGLISH -- comments and docstrings included; only the UI stays French, "
            "through i18n. French QUOTED between « » is fine: it names what the screen "
            "really shows."
            + chr(10)
            + "  "
            + (chr(10) + "  ").join(
                f"{k}  {v}" for k, v in sorted(fresh.items(), key=lambda kv: kv[1])
            ),
        )

    def test_the_guard_reads_something_at_all(self) -> None:
        """⚠️ A ratchet reading zero file passes for ever, and silently. It has happened
        in this house with another guard whose regular expression had stopped matching:
        two empty sets agree perfectly."""
        seen = 0
        for roots, patterns in ((PY_ROOTS, ("*.py",)), (TS_ROOTS, ("*.ts", "*.tsx"))):
            for root in roots:
                base = REPO / root
                if base.exists():
                    seen += sum(1 for pattern in patterns for _ in base.rglob(pattern))
        self.assertGreater(
            seen,
            10,
            f"Only {seen} source file(s) in reach: the guard no longer reads the code.",
        )


if __name__ == "__main__":
    # Re-freeze the baseline after a deliberate bulk change.
    found = collect_offenders()
    BASELINE.write_text(
        "# Fingerprints of the FRENCH prose that predates this guard. Only new prose\n"
        "# fails; translating a block and dropping its line here is always welcome.\n"
        "# Regenerate with:  python "
        + pathlib.Path(__file__).name
        + "\n"
        + "".join(
            f"{k}  # {v}\n" for k, v in sorted(found.items(), key=lambda kv: kv[1])
        ),
        encoding="utf-8",
    )
    print(f"{len(found)} French block(s) frozen in {BASELINE.name}", file=sys.stderr)
