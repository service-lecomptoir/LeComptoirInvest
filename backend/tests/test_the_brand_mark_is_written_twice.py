"""The Invest brand mark is written TWICE, and both copies stay one drawing.

The compass mark (the Comptoir C, the needle wearing the family pin's orange)
was chosen by the user on 5 September -- the grammar shared with the other
Comptoir products. It lives in LogoMark (React) and favicon.svg (static): a
catalogue written twice drifts one side at a time, so this guard pins the
geometry signatures shared by both files.
"""

import pathlib

FRONT = pathlib.Path(__file__).resolve().parents[2] / "frontend"

SIGNATURES = [
    "M41.5 22.8a13.2 13.2 0 0 0-9.4-3.8",
    "rotate(38 32 32)",
    "M32 17.2 L36 32 L32 46.8 L28 32 Z",
    "M32 17.2 L36 32 H28 Z",
    'cx="50.8" cy="40.8"',
]


def test_both_copies_carry_every_signature():
    logo = (FRONT / "src" / "components" / "common" / "Logo.tsx").read_text(encoding="utf-8")
    favicon = (FRONT / "public" / "favicon.svg").read_text(encoding="utf-8")
    for sig in SIGNATURES:
        assert sig in logo, f"LogoMark lost the element {sig!r}"
        assert sig in favicon, f"favicon.svg lost the element {sig!r}"
