"""What kind of account this is: a fund run for itself, or a firm that runs funds for clients.

🔴 THE CONSOLE SPEAKS A NEUTRAL WORD, EACH PRODUCT TRANSLATES IT INTO ITS OWN. Alice used to
send `role = "gestionnaire"` or `"gestionnaire_proprio"`, which are real-estate words: this
product had no such role and refused the account, which blocked self-service sign-up. Since
28 September 2026 Alice sends `acts_for`, which says only WHO the account works for, and each
product keeps the kind that means something in its own trade:

  * `self`    -> `single_fund`        : a club or a fund managing its own money;
  * `clients` -> `management_company` : a firm managing money on behalf of clients.

⚠️ THIS IS THE ONLY PLACE THE MAPPING IS WRITTEN. The route, the serializer and `/auth/me`
all read it from here; a second copy of « self means single_fund » is how the console and
the screen come to disagree about what an account is.

⚠️ NULL MEANS « NOT KNOWN », AND IT STAYS NULL. Accounts created before this column, or by an
older console that still sends only a role, have no kind. Guessing one from the legacy role
would assert something nobody said: « gestionnaire » never meant « works for clients ».

⚠️ THE LABEL IS A FUNCTION, NEVER A MODULE-LEVEL DICT: a label computed at import freezes the
language of the first reader for every later one (see `core.i18n`).
"""

from __future__ import annotations

from app.core.i18n import pick

#: What Alice sends.
SELF = "self"
CLIENTS = "clients"
ACTS_FOR: tuple[str, ...] = (SELF, CLIENTS)

#: What this product stores.
SINGLE_FUND = "single_fund"
MANAGEMENT_COMPANY = "management_company"
KINDS: tuple[str, ...] = (SINGLE_FUND, MANAGEMENT_COMPANY)

_KIND_BY_ACTS_FOR: dict[str, str] = {SELF: SINGLE_FUND, CLIENTS: MANAGEMENT_COMPANY}
_ACTS_FOR_BY_KIND: dict[str, str] = {
    kind: acts_for for acts_for, kind in _KIND_BY_ACTS_FOR.items()
}


def kind_for(acts_for: str) -> str | None:
    """The kind this product stores for the console's word, or None when the word is not
    one of the two it speaks. The caller refuses; this function only answers."""
    return _KIND_BY_ACTS_FOR.get(acts_for)


def acts_for_of(kind: str | None) -> str | None:
    """The console's word for a stored kind, so what Alice wrote is what Alice reads back."""
    return _ACTS_FOR_BY_KIND.get(kind) if kind else None


def label_of(kind: str | None) -> str | None:
    """The kind as a reader sees it, in their language. None when the kind is not known."""
    if kind == SINGLE_FUND:
        return pick("Club ou fonds", "Club or fund")
    if kind == MANAGEMENT_COMPANY:
        return pick("Société de gestion", "Management company")
    return None


def refusal_for(acts_for: str) -> str:
    """Why a value of `acts_for` is refused, naming the two that are accepted."""
    return pick(
        f"Valeur « {acts_for} » inconnue pour acts_for : les deux valeurs acceptées "
        f"sont « {SELF} » (le compte travaille pour lui-même) et « {CLIENTS} » (il "
        f"travaille pour des clients).",
        f"Unknown value « {acts_for} » for acts_for: the two accepted values are "
        f"« {SELF} » (the account works for itself) and « {CLIENTS} » (it works for "
        f"clients).",
    )
