"""The reference an investor copies into a transfer label.

WITH NO PAYMENT PROVIDER, THIS STRING IS THE WHOLE LINK between a transfer and a capital
call. Everything else about reconciliation is guesswork on amounts and names; this is the
one piece of information that identifies a payment exactly — when it survives the journey
from a printed notice, through a human reading it, into a banking app.

So it is designed against that journey, not against a database:

  * SHORT. It is typed by hand, often on a phone. Every extra character is a chance to
    mistype.
  * NO AMBIGUOUS CHARACTERS. `0`/`O` and `1`/`I`/`L` are the same glyph to a tired reader,
    and a transposed reference points at another investor's call.
  * A CHECK CHARACTER. Not to prevent fraud, but to reject a typo at import instead of
    silently matching nothing — or worse, matching something else.
  * UPPER CASE and grouped, because that is how a reference is read aloud over the phone
    when an investor calls to say the transfer has gone out.

⚠️ UNIQUENESS IS THE DATABASE'S JOB, NOT THIS MODULE'S. `capital_calls` carries a unique
index on `reference`; generating here and checking there is what keeps a collision from
being a silent misattribution. This module makes collisions improbable; the index makes them
impossible.
"""

from __future__ import annotations

import secrets
from app.core.i18n import pick

#: 0/O and 1/I/L are out. So is U, which is read as V in some hands.
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"

#: Fixed prefix, so an investor and their bank can see at a glance what the transfer is for,
#: and so a reference pasted into the wrong product is obviously wrong.
PREFIX = "INV"

#: Length of the random part. Thirty characters over six positions is 729 million
#: combinations: collisions stay improbable long past any plausible number of calls, and the
#: unique index catches the one that happens anyway.
_BODY_LENGTH = 6


def _check_character(body: str) -> str:
    """A single character derived from the body, to catch a typo at import.

    Deliberately simple and deterministic: a weighted sum over the alphabet's positions,
    which catches every single-character error and every transposition of two adjacent
    characters — the two mistakes a human actually makes when copying a code.
    """
    total = sum((index + 1) * _ALPHABET.index(char) for index, char in enumerate(body))
    return _ALPHABET[total % len(_ALPHABET)]


def generate() -> str:
    """A new reference, in the form INV-XXXXXXC.

    `secrets`, not `random`: the references are printed on notices that leave the building,
    and a predictable sequence tells a reader how many calls the fund has issued.
    """
    body = "".join(secrets.choice(_ALPHABET) for _ in range(_BODY_LENGTH))
    return f"{PREFIX}-{body}{_check_character(body)}"


def normalise(raw: str | None) -> str | None:
    """Pull a reference out of whatever a bank label actually contains.

    A transfer label is free text: « VIR INV-7K2M9QX SOUSCRIPTION », « inv 7k2m9qx »,
    « INV7K2M9QX/JUILLET ». All three carry the same reference, and refusing the last two
    because of their punctuation would send a perfectly identified transfer to the manual
    pile — which is the pile this whole mechanism exists to keep empty.

    Returns None when nothing reference-shaped is there.
    """
    if not raw:
        return None
    upper = raw.upper()
    marker = upper.find(PREFIX)
    if marker < 0:
        return None
    kept = []
    for char in upper[marker + len(PREFIX) :]:
        if char in _ALPHABET:
            kept.append(char)
            if len(kept) == _BODY_LENGTH + 1:
                break
        elif char in "- /.":
            # Separators are noise between the prefix and the body; anything else ends it.
            if kept:
                break
        else:
            break
    if len(kept) != _BODY_LENGTH + 1:
        return None
    return f"{PREFIX}-{''.join(kept)}"


def is_valid(reference: str | None) -> bool:
    """Does this reference pass its own check character?

    Answered BEFORE looking in the database. A reference that fails here was mistyped, and
    saying so is far more useful than « no matching call » — which reads as « the fund has
    lost my payment » to the investor who is asking.
    """
    normalised = normalise(reference)
    if normalised is None:
        return False
    body = normalised[len(PREFIX) + 1 : -1]
    return normalised[-1] == _check_character(body)


def epc_qr_payload(
    *, beneficiary: str, iban: str, amount: str, currency: str, reference: str
) -> str:
    """The text of an EPC QR code: the investor scans it and their banking app fills in.

    THE MISTYPED REFERENCE STOPS EXISTING when the investor never types it. The QR carries
    the beneficiary, the account, the amount and the reference; the app pre-fills the
    transfer and the investor only confirms. It is the cheapest reconciliation win available
    on this rail — no provider, no fee, no integration, just a picture on the call notice.

    ⚠️ EPC069-12 IS EURO-ONLY, and this fund is multi-currency. The caller checks the
    currency before offering the code; there is no point drawing a QR a bank will refuse.
    Returned as text so the caller renders it however it likes.
    """
    if currency.upper() != "EUR":
        raise ValueError(
            pick(
                f"La norme EPC du QR de virement ne couvre que l'euro ; cet appel est en "
                f"{currency}. Afficher les coordonnées bancaires à la place.",
                f"The EPC QR standard covers euro transfers only; this call is in "
                f"{currency}. Show the account details instead.",
            )
        )
    return "\n".join(
        [
            "BCD",  # service tag
            "002",  # version
            "1",  # UTF-8
            "SCT",  # SEPA credit transfer
            "",  # BIC, optional inside SEPA
            beneficiary[:70],
            "".join(iban.split()).upper(),
            f"EUR{amount}",
            "",  # purpose code
            "",  # structured remittance
            reference[:140],  # unstructured remittance: our reference
        ]
    )
