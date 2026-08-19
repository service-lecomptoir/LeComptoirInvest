"""What the fund actually writes to an investor: the call notice, and the reminder.

🔴 THIS IS THE FIRST TEXT THIS PRODUCT ADDRESSES TO SOMEBODY WHO IS NOT THE CALLER, and that
is why `i18n.use_lang` exists. Every other sentence here answers the person who made the
request, so `Accept-Language` is right. A notice is different: a manager clicks, an INVESTOR
reads. Rendering it in the manager's language would send a French letter to a British
investor and an English one to a French investor, and nothing in the product would look wrong.

⚠️ THE TWO LETTERS ARE NOT ONE LETTER WITH A FLAG. A first notice ASKS; a reminder says the
due date has passed. Merging them would either accuse an investor who was never asked - the
fund's own omission, which `LateCall.never_notified` exists to keep separate - or send a
demand with no wording about lateness after the date. `call_chasing_service.due_for_reminder`
refuses a reminder on a call that was never notified; this module refuses to write one.

🔴 THE REMINDER STATES WHAT IS STILL OUTSTANDING, NEVER THE ORIGINAL AMOUNT. Partial payment
is normal. An investor who paid four fifths and receives a demand for the whole reads it as
« they lost my transfer », and the next thing they do is stop trusting the fund's figures
rather than pay the fifth.

⚠️ AND THE RATE IS THE ONE THE CALL CARRIES. `CapitalCall.late_interest_rate` is stored per
call precisely so that changing a fund-wide parameter later cannot rewrite what an investor
was told when they received the demand. Reading a current setting here would do exactly that,
retroactively, for every call already out.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.core import money, references
from app.core.i18n import pick


@dataclass(frozen=True)
class Notice:
    """One letter, ready to be sent, and what could not be put in it.

    `qr_unavailable_reason` is not an error: the EPC standard is euro-only and this fund is
    multi-currency. The letter then names the account instead of showing a picture a bank
    would refuse, and the reason says which it did.
    """

    subject: str
    body: str
    qr_payload: str | None = None
    qr_unavailable_reason: str | None = None


@dataclass(frozen=True)
class CallFacts:
    """Everything a letter needs, and nothing from the database.

    ⚠️ PLAIN VALUES, NO ORM. The two builders below are pure: they can be read, tested and
    argued about without a session, and the same figures produce the same letter whoever
    assembled them.
    """

    investor_name: str
    fund_name: str
    reference: str
    amount: Decimal
    currency: str
    due_on: date
    iban: str | None
    #: The rate this call was issued under, as a fraction a year. None means this call
    #: carries no late interest, which is a decision and not an omission.
    late_interest_rate: float | None = None
    #: Reminder only: what arrived, what is still missing, and what the delay has cost.
    received: Decimal = Decimal("0")
    outstanding: Decimal = Decimal("0")
    late_interest: Decimal = Decimal("0")
    as_of: date | None = None


def _amount(value: Decimal, currency: str) -> str:
    """The figure, quantised to the currency's own minor units.

    ⚠️ NEVER `str(value)` STRAIGHT FROM THE COLUMN. `Numeric(18, 4)` renders « 1000.0000 »,
    and an investor reading four decimals on a euro amount wonders which two are the cents.
    """
    return f"{money.quantize(value, currency)} {currency}"


def _rate(fraction: float) -> str:
    return f"{fraction * 100:.2f} %"


def _account_lines(facts: CallFacts) -> str:
    """The reference and the account, on their own lines.

    🔴 THE REFERENCE IS THE WHOLE MECHANISM. With no payment provider, the only thing tying a
    transfer to a call is the text the investor copies into the label. It gets its own line,
    unmissable, and a sentence saying what happens without it - because « we could not
    identify your payment » is a conversation neither side wants.
    """
    lines = [
        pick(
            f"Référence à reporter dans le libellé du virement : {facts.reference}",
            f"Reference to quote in the transfer label: {facts.reference}",
        )
    ]
    if facts.iban:
        lines.append(
            pick(
                f"Compte à créditer : {facts.iban}",
                f"Account to credit: {facts.iban}",
            )
        )
    lines.append(
        pick(
            "Cette référence est le seul lien entre votre virement et cet appel : sans "
            "elle, le versement ne peut pas être imputé.",
            "That reference is the only link between your transfer and this call: without "
            "it, the payment cannot be attributed.",
        )
    )
    return "\n".join(lines)


def _qr(facts: CallFacts, amount: Decimal) -> tuple[str | None, str | None]:
    """The EPC payload, or the reason there is none. Never a silent absence."""
    if not facts.iban:
        return None, pick(
            "Le véhicule n'a pas de compte enregistré : aucun QR de virement ne peut être "
            "produit, et l'avis ne peut pas indiquer où payer.",
            "The vehicle has no account on record: no transfer QR can be produced, and the "
            "notice cannot say where to pay.",
        )
    try:
        payload = references.epc_qr_payload(
            beneficiary=facts.fund_name,
            iban=facts.iban,
            amount=str(money.quantize(amount, facts.currency)),
            currency=facts.currency,
            reference=facts.reference,
        )
    except ValueError as exc:
        # Euro-only by standard. The refusal already carries its own sentence, in the
        # reader's language, because `references` was converted too.
        return None, str(exc)
    return payload, None


def first_notice(facts: CallFacts) -> Notice:
    """The demand itself: what is asked, by when, and how to pay it."""
    subject = pick(
        f"Appel de fonds {facts.reference} - {facts.fund_name}",
        f"Capital call {facts.reference} - {facts.fund_name}",
    )
    due = facts.due_on.isoformat()
    parts = [
        # A name is a name in both languages; wrapping it in `pick` would only invite
        # somebody to translate one side of it.
        f"{facts.investor_name},",
        pick(
            f"Le fonds {facts.fund_name} appelle {_amount(facts.amount, facts.currency)} "
            f"au titre de votre souscription.",
            f"Fund {facts.fund_name} is calling "
            f"{_amount(facts.amount, facts.currency)} against your subscription.",
        ),
        pick(f"À régler avant le {due}.", f"Payable by {due}."),
        _account_lines(facts),
    ]
    if facts.late_interest_rate:
        parts.append(
            pick(
                f"À défaut de règlement au {due}, un intérêt de "
                f"{_rate(facts.late_interest_rate)} l'an court sur la part impayée.",
                f"If it is not settled by {due}, interest of "
                f"{_rate(facts.late_interest_rate)} a year runs on the unpaid part.",
            )
        )
    payload, why = _qr(facts, facts.amount)
    return Notice(
        subject=subject,
        body="\n\n".join(parts),
        qr_payload=payload,
        qr_unavailable_reason=why,
    )


def reminder(facts: CallFacts) -> Notice:
    """The call is past due and still short. Says by how much, and what that has cost.

    🔴 IT REFUSES TO BE WRITTEN WHEN NOTHING IS OUTSTANDING. A reminder for a settled call
    is not a harmless duplicate: it tells an investor who paid that their payment was not
    seen, which is the one message that makes them stop paying on the reference.
    """
    if facts.outstanding <= 0:
        raise ValueError(
            pick(
                f"L'appel {facts.reference} ne reste dû de rien : une relance dirait à cet "
                f"investisseur que son règlement n'a pas été vu.",
                f"Call {facts.reference} has nothing outstanding: a reminder would tell "
                f"this investor their payment was not seen.",
            )
        )

    subject = pick(
        f"Rappel - appel de fonds {facts.reference}",
        f"Reminder - capital call {facts.reference}",
    )
    due = facts.due_on.isoformat()
    parts = [
        f"{facts.investor_name},",
        pick(
            f"L'appel de fonds {facts.reference}, échu le {due}, reste dû de "
            f"{_amount(facts.outstanding, facts.currency)}.",
            f"Capital call {facts.reference}, due on {due}, is still short by "
            f"{_amount(facts.outstanding, facts.currency)}.",
        ),
    ]
    # ⚠️ ONLY WHEN SOMETHING ARRIVED. « Already received: 0 » reads as an accusation, and it
    # is also the line an investor who paid yesterday would find hardest to believe.
    if facts.received > 0:
        parts.append(
            pick(
                f"Déjà reçu sur cet appel : {_amount(facts.received, facts.currency)}.",
                f"Already received against this call: "
                f"{_amount(facts.received, facts.currency)}.",
            )
        )
    if facts.late_interest > 0 and facts.as_of is not None:
        rate = (
            pick(
                f", au taux de {_rate(facts.late_interest_rate)} l'an porté par cet appel",
                f", at the {_rate(facts.late_interest_rate)} a year this call carries",
            )
            if facts.late_interest_rate
            else ""
        )
        parts.append(
            pick(
                f"Intérêt de retard arrêté au {facts.as_of.isoformat()} : "
                f"{_amount(facts.late_interest, facts.currency)}{rate}.",
                f"Late interest to {facts.as_of.isoformat()}: "
                f"{_amount(facts.late_interest, facts.currency)}{rate}.",
            )
        )
    parts.append(_account_lines(facts))

    payload, why = _qr(facts, facts.outstanding)
    return Notice(
        subject=subject,
        body="\n\n".join(parts),
        qr_payload=payload,
        qr_unavailable_reason=why,
    )


__all__ = ["CallFacts", "Notice", "first_notice", "reminder"]
