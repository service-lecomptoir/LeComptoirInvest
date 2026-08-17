"""What an investor legally is: the two values, named once.

THE SAME TWO WORDS AS THE REST OF THE HOUSE — Le Comptoir Immo stores exactly these on its
landlords, and an investor is very often a landlord too. A second vocabulary would have to
be translated wherever the two products meet, and would be translated wrongly once.

They are French because they are STORED VALUES, not labels: renaming one means migrating
every row and every comparison at once, for no reader's benefit. Display goes through i18n.
"""

PERSON = "personne"
COMPANY = "societe"

KINDS: tuple[str, ...] = (PERSON, COMPANY)


def is_company(value: str | None) -> bool:
    """True only for a legal person. Unknown is NOT a company."""
    return (value or "").strip().lower() == COMPANY
