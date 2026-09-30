"""A French sentence of the server puts a no-break space before its colons.

A plain one lets the colon wrap alone to the start of the next line on a phone. The rule is
applied in `pick`, where every sentence the reader sees passes (customer recipe, 30 Sept
2026: seventy refusals written with a plain space).
"""

from __future__ import annotations

from app.core.i18n import NBSP, pick, use_lang


def test_the_french_sentence_gets_a_no_break_space_before_its_colon():
    said = pick("Trop de demandes d'un coup : réessayez.", "Too many requests: retry.")
    assert said == f"Trop de demandes d'un coup{NBSP}: réessayez."


def test_the_english_sentence_is_left_as_written():
    with use_lang("en"):
        assert pick("Un : deux", "One: two") == "One: two"


def test_a_sentence_already_right_is_not_touched():
    assert pick(f"Un{NBSP}: deux", "One: two") == f"Un{NBSP}: deux"
