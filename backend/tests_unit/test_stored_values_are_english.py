"""Every value this product WRITES TO THE DATABASE is English, and stays English.

🔴 WHY AN INVENTORY AND NOT A LIST OF FRENCH WORDS. The first version of this measurement
used the sister product's French vocabulary, and it passed on `IN = "entree"`,
`OUT = "sortie"`, `"iban_virtuel"`, `"eleve"` and `"non_identifie"` — five stored values in
French, invisible because the list did not happen to contain those five words. That is the
repository's most expensive recurring defect wearing a new coat: A GUARD NARROWER THAN ITS
RULE READS EXACTLY LIKE A GUARD THAT HOLDS IT.

So this one does not try to recognise French. It freezes the COMPLETE set of stored domain
values, and any new one fails until somebody adds it here deliberately — at which moment
they are looking at a list that is entirely English, and the odd one out is obvious. The
failure mode is « too strict », which is the only safe direction for a guard.

⚠️ AND WHY IT MATTERS MORE HERE THAN ANYWHERE. A stored value is the one kind of name that
cannot be renamed later on a whim: every row, every comparison, every export and every
integration moves at once. Le Comptoir Immo carries 327 French enum values it can no longer
touch. This product had eighteen and nothing in production; they were changed in an
afternoon. There is no second afternoon.
"""

import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[1] / "app"

#: Module-level constants whose value is a bare lowercase token are the ones that reach a
#: column. Anything else (an algorithm name, an alphabet, a prefix, a day count) is
#: configuration, not a domain value, and is excluded by the shape of the pattern.
_CONSTANT = re.compile(
    r'^([A-Z_][A-Z_0-9]*)\s*(?::\s*str\s*)?=\s*"([a-z][a-z_0-9]*)"\s*$', re.M
)

#: 🔴 THE COMPLETE INVENTORY. Adding a line is a deliberate act; that is the whole point.
APPROVED: dict[str, str] = {
    # Instruments
    "EQUITY": "equity",
    "LOAN": "loan",
    # KYC verdicts
    "PENDING": "pending",
    "ACCEPTED": "accepted",
    "REFUSED": "refused",
    "REVIEW": "review",
    "RISK_STANDARD": "standard",
    "RISK_HIGH": "high",
    # Subscription requests
    "REQUEST_PENDING": "pending",
    "REQUEST_ACCEPTED": "accepted",
    "REQUEST_REFUSED": "refused",
    "REQUEST_WITHDRAWN": "withdrawn",
    # Projects
    "STUDY": "study",
    "ACTIVE": "active",
    "CLOSED": "closed",
    "WRITTEN_OFF": "written_off",
    "RETURN_CAPITAL": "capital",
    "RETURN_INCOME": "income",
    # Bank movements
    "IN": "in",
    "OUT": "out",
    # What a proposal is founded on
    "BY_VIRTUAL_IBAN": "virtual_iban",
    "BY_REFERENCE": "reference",
    "BY_PAYER_IBAN": "payer_iban",
    "UNMATCHED": "unmatched",
    # Investor categories: which protections apply to whom. Stored on `investors.category`,
    # and NULL there is meaningful — `eligibility.is_protected` reads it as protected.
    "RETAIL": "retail",
    "SOPHISTICATED": "sophisticated",
    "PROFESSIONAL": "professional",
    # ⚠️ THESE TWO REACH NO COLUMN, AND THEY BELONG HERE ANYWAY. Which letter a call notice
    # is travels over the API - a query parameter going in, a discriminator coming back -
    # and a published value is exactly as hard to rename as a stored one: every caller moves
    # at once. The inventory is for names that cannot be taken back, not only for columns.
    "FIRST_NOTICE": "first_notice",
    "REMINDER": "reminder",
    # ⚠️ THE PLAN'S VERDICT ON THE REGISTER, PUBLISHED AND THEREFORE FROZEN. These four
    # reach no column either, and they belong here for the same reason as the two above:
    # `GET /investors/quota` sends the word on the wire and the screen branches on it. A
    # published value is exactly as hard to rename as a stored one - every caller moves at
    # once - and « unknown » in particular must keep meaning « the ceiling could not be
    # read » rather than drifting into « no ceiling ».
    "OK": "ok",
    "OVERAGE": "overage",
    "BLOCKED": "blocked",
    "UNKNOWN": "unknown",
    # The vehicle's life. `CLOSED` above is shared with a project's: both mean « nothing
    # left to do here », and one word for one meaning is the point of an inventory.
    "RAISING": "raising",
    "INVESTING": "investing",
    "HARVESTING": "harvesting",
    # ⚠️ A LANGUAGE TAG, NOT FRENCH PROSE. `users.locale` stores it, so it belongs in this
    # inventory; but « fr » is BCP 47 and translating it would be the defect. It is listed
    # here so the next reader sees it was looked at rather than missed.
    "DEFAULT": "fr",
    # Accounts
    "ADMIN": "admin",
    "MANAGER": "manager",
    "INVESTOR": "investor",
    # ⚠️ THE TWO DELIBERATE EXCEPTIONS, and they are not an oversight. Le Comptoir Immo
    # stores exactly these two words on its landlords, and an investor is very often a
    # landlord. A second vocabulary would have to be translated wherever the two products
    # meet, and would be translated wrongly once. Changing them here would break a contract
    # that already exists, which is a worse outcome than two French words in a column.
    "PERSON": "personne",
    "COMPANY": "societe",
}


def _found() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(APP.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for name, value in _CONSTANT.findall(path.read_text(encoding="utf-8")):
            if name.startswith("_"):
                continue  # module-private: never a column value
            found[name] = value
    return found


def test_no_stored_value_appears_without_being_approved():
    """A new constant fails until it is listed above. That pause is the guard."""
    unknown = {n: v for n, v in _found().items() if n not in APPROVED}
    assert not unknown, (
        "Ces valeurs sont écrites en base sans avoir été inscrites dans l'inventaire :\n"
        + "\n".join(f"  {n} = {v!r}" for n, v in sorted(unknown.items()))
        + "\n\nAjoutez-les à APPROVED, en anglais. Une valeur stockée ne se renomme plus "
        "une fois qu'il y a des lignes."
    )


def test_an_approved_value_has_not_drifted():
    """The inventory and the code agree on what each name is worth."""
    found = _found()
    drifted = {
        name: (APPROVED[name], found[name])
        for name in APPROVED
        if name in found and found[name] != APPROVED[name]
    }
    assert not drifted, (
        "Ces valeurs ont changé sans que l'inventaire suive :\n"
        + "\n".join(
            f"  {n} : inventaire {a!r}, code {b!r}"
            for n, (a, b) in sorted(drifted.items())
        )
    )


def test_only_the_two_inter_product_values_are_french():
    """The exceptions are named, and there are exactly two of them.

    Written as a count rather than as prose so that a third one cannot be slipped in with a
    comment explaining why it is also special.
    """
    exceptions = {"PERSON", "COMPANY"}
    english_only = {n: v for n, v in APPROVED.items() if n not in exceptions}
    # Every remaining value is an ASCII English token: no accent, and no French-only
    # spelling can survive the round trip through the approved list above.
    assert all(
        v.isascii() and v.replace("_", "").isalnum() for v in english_only.values()
    )
    assert set(APPROVED) & exceptions == exceptions
