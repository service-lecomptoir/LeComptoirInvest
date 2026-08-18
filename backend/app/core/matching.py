"""Whose money is this? The rule that reads a bank line and proposes an attribution.

THIS IS THE HEART OF A TRANSFER-ONLY FUND. A statement line carries an amount, a date, a
label and a payer name, and none of them is an investor identifier. Everything the tool is
for — a portfolio that is true, a statement an investor can check, a treasury that
reconciles — rests on getting this right, and on being honest when it cannot.

🔴 IT PROPOSES, IT NEVER DECIDES. The output is a proposal with the evidence that produced
it. A human attributes, and `Contribution.attributed_by` records who. Automatic attribution
of a 200 000 € transfer on a name that looked close is not a time saving, it is a mistake
nobody will find until an investor reads a statement that is not theirs.

THE EVIDENCE, IN DESCENDING ORDER OF WHAT IT ACTUALLY PROVES:

  1. THE ACCOUNT IT ARRIVED ON. A virtual IBAN issued to one investor identifies them with
     no interpretation at all. Nothing else comes close, and it is the reason to ask a bank
     for them.
  2. THE REFERENCE IN THE LABEL. Identifies the CALL, therefore the subscription and the
     investor. Strong — it carries a check character — but it travels through a human
     retyping it, and it can be the reference of a call the investor already paid.
  3. THE PAYER'S ACCOUNT. Identifies the INVESTOR, never the call: a lender with four open
     calls pays them all from the same account.
  4. THE AMOUNT. On its own, evidence of nothing. Two investors called for 50 000 € in the
     same week is not a coincidence, it is a Tuesday.

⚠️ THE NAME IS NOT EVIDENCE, IT IS A CHECK. A payer name that does NOT match the investor
is a third-party payment and a finding in its own right; a name that does match adds almost
nothing, since anyone can label a transfer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

#: The account it landed on belongs to exactly one investor.
BY_VIRTUAL_IBAN = "virtual_iban"
#: A valid reference was found in the label.
BY_REFERENCE = "reference"
#: The payer's account is one we hold for an investor.
BY_PAYER_IBAN = "payer_iban"
#: Nothing identified it.
UNMATCHED = "unmatched"


@dataclass(frozen=True)
class Candidate:
    """One investor, and what we know that could tie a transfer to them."""

    investor_id: str
    display_name: str
    #: The dedicated account this investor was told to pay into, if any.
    virtual_iban: str | None = None
    #: Fingerprint of the account they pay FROM, if known. Never the IBAN itself: matching
    #: works on fingerprints so nothing has to be decrypted to reconcile a statement.
    iban_fingerprint: str | None = None
    #: References of their calls that are still open, and the call each belongs to.
    open_call_references: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Proposal:
    """What the rule believes, and on what evidence. Never an attribution in itself."""

    investor_id: str | None
    capital_call_id: str | None
    basis: str
    #: True when the payer is not the investor. A FINDING, surfaced for a human — money from
    #: a spouse, a company paying for its director, a notary — legitimate more often than
    #: not, and exactly what identification rules exist to see.
    third_party_payer: bool = False
    #: Why, in the operator's language. Shown beside the proposal: an attribution nobody can
    #: explain is one nobody should confirm.
    explanation: str = ""

    @property
    def is_identified(self) -> bool:
        return self.investor_id is not None


def _names_agree(payer: str | None, investor: str) -> bool:
    """Loose comparison: case, accents and word order are noise on a bank label.

    Deliberately generous, because this is used to RAISE a third-party flag, not to confirm
    a match. Being strict here would flag « ALPHANOR RAYMONDE » against « Raymonde
    Alphanor » and teach an operator to dismiss the warning — and a warning that is usually
    wrong is a warning nobody reads on the day it is right.
    """
    if not payer:
        return False

    def words(text: str) -> set[str]:
        import unicodedata

        stripped = unicodedata.normalize("NFD", text.lower())
        clean = "".join(c for c in stripped if not unicodedata.combining(c))
        return {
            w
            for w in "".join(c if c.isalnum() else " " for c in clean).split()
            if len(w) > 2
        }

    a, b = words(payer), words(investor)
    return bool(a & b)


def propose(
    *,
    received_on_iban: str | None,
    label: str | None,
    payer_name: str | None,
    payer_iban_fingerprint: str | None,
    amount: Decimal,
    candidates: list[Candidate],
) -> Proposal:
    """Read one bank line against what we know, and say what it probably is.

    `amount` is taken and deliberately NOT used to identify anybody — it is there so the
    signature does not have to change when the screen starts showing « and the amount
    matches the call exactly », which is a comfort for the human, never a reason.
    """
    from app.core import references

    by_id = {c.investor_id: c for c in candidates}

    # 1. THE ACCOUNT IT ARRIVED ON. No interpretation, nothing to get wrong.
    if received_on_iban:
        target = "".join(received_on_iban.split()).upper()
        for candidate in candidates:
            if (
                candidate.virtual_iban
                and "".join(candidate.virtual_iban.split()).upper() == target
            ):
                return Proposal(
                    investor_id=candidate.investor_id,
                    capital_call_id=None,
                    basis=BY_VIRTUAL_IBAN,
                    third_party_payer=not _names_agree(
                        payer_name, candidate.display_name
                    ),
                    explanation=(
                        f"Virement reçu sur le compte dédié de {candidate.display_name}. "
                        f"Reste à choisir l'appel de fonds qu'il règle."
                    ),
                )

    # 2. THE REFERENCE. Identifies the call, so the subscription and the investor with it.
    found = references.normalise(label)
    if found and references.is_valid(found):
        for candidate in candidates:
            call_id = candidate.open_call_references.get(found)
            if call_id:
                return Proposal(
                    investor_id=candidate.investor_id,
                    capital_call_id=call_id,
                    basis=BY_REFERENCE,
                    third_party_payer=not _names_agree(
                        payer_name, candidate.display_name
                    ),
                    explanation=f"Référence {found} trouvée dans le libellé.",
                )

    # 3. THE PAYER'S ACCOUNT. Identifies the investor, never which call.
    if payer_iban_fingerprint:
        matches = [
            c for c in candidates if c.iban_fingerprint == payer_iban_fingerprint
        ]
        if len(matches) == 1:
            candidate = matches[0]
            return Proposal(
                investor_id=candidate.investor_id,
                capital_call_id=None,
                basis=BY_PAYER_IBAN,
                third_party_payer=False,
                explanation=(
                    f"Compte émetteur connu : celui de {candidate.display_name}. "
                    f"L'appel de fonds réglé reste à désigner."
                ),
            )
        if len(matches) > 1:
            # Two investors sharing an account — a couple, a holding and its subsidiary.
            # Refusing to choose is the answer: guessing here attributes one person's money
            # to another, and the two are exactly the pair nobody would double-check.
            names = ", ".join(sorted(m.display_name for m in matches))
            return Proposal(
                investor_id=None,
                capital_call_id=None,
                basis=UNMATCHED,
                explanation=(
                    f"Ce compte émetteur est enregistré pour plusieurs investisseurs "
                    f"({names}) : l'imputation doit être choisie."
                ),
            )

    # 4. NOTHING. Said plainly, with what was looked at, so the operator knows what to fix.
    tried = []
    if found:
        tried.append(f"la référence {found} ne correspond à aucun appel ouvert")
    elif label:
        tried.append("aucune référence exploitable dans le libellé")
    if payer_iban_fingerprint:
        tried.append("compte émetteur inconnu")
    if not by_id:
        tried.append("aucun investisseur candidat")
    return Proposal(
        investor_id=None,
        capital_call_id=None,
        basis=UNMATCHED,
        explanation="Non identifié : "
        + (", ".join(tried) if tried else "aucun indice exploitable")
        + ".",
    )
