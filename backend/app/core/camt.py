"""Reading a CAMT.053 statement: the bank's own file, turned into movements.

🔴 THE RECONCILIATION ENGINE ALREADY EXISTED AND HAD NOTHING TO EAT. `matching.propose`
matches a transfer to a subscription by reference, by virtual IBAN and by payer name; the
only way to feed it was an operator retyping a statement. Retyped money is money with a typo
in it, and the typo lands on a reference — which is the single field the whole matching rests
on.

⚠️ THIS MODULE PARSES, IT DOES NOT DECIDE. It produces lines; whether a line is a
contribution, whose it is and what it settles stays with `treasury_service`. A parser that
also attributed would put the bank's own guess ahead of the fund's rule.

🔴 AND IT REFUSES RATHER THAN GUESSES, throughout. A file whose namespace it does not know,
an entry without an amount, a credit/debit marker it cannot read: each is reported by
position so somebody can look at the line, never silently dropped. A statement quietly short
of one entry reconciles to a number that is wrong and looks right.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

#: ISO 20022 ships a new minor version every few years and the tag names do not move. Rather
#: than list the ones seen so far — a list that is wrong the day the bank upgrades — the
#: namespace is stripped and the local names are read.
_NAMESPACE = re.compile(r"^\{[^}]*\}")

#: What the bank calls a credit and a debit. These two are the format's, not ours, and
#: reversing them turns money coming in into money going out.
_CREDIT = "CRDT"
_DEBIT = "DBIT"


@dataclass(frozen=True)
class StatementLine:
    """One entry of a statement, in this product's own vocabulary."""

    account_iban: str
    external_id: str | None
    direction: str
    amount: Decimal
    currency: str
    value_date: date
    label: str | None = None
    counterparty_name: str | None = None
    counterparty_iban: str | None = None


@dataclass
class Parsed:
    """What was read, and what could not be."""

    lines: list[StatementLine] = field(default_factory=list)
    #: One entry per line that could not be read, with its position and the reason. Never
    #: empty when something was skipped: a statement short of one entry reconciles to a
    #: figure that is wrong and looks right.
    refused: list[str] = field(default_factory=list)


def _local(tag: str) -> str:
    return _NAMESPACE.sub("", tag)


def _find(node, *names: str):
    """The first descendant whose local name matches, at any depth."""
    for child in node.iter():
        if _local(child.tag) in names:
            return child
    return None


def _find_direct(node, *names: str):
    """A DIRECT child only.

    ⚠️ THE DIFFERENCE MATTERS FOR AMOUNTS. An entry carries its own `<Amt>` and each of its
    details carries one too; a search at any depth would find the detail's amount when
    reading the entry, and the entry's when reading a detail. Both are real amounts, and
    picking the wrong one splits or merges somebody's payment.
    """
    for child in node:
        if _local(child.tag) in names:
            return child
    return None


def _text(node) -> str | None:
    if node is None or node.text is None:
        return None
    value = node.text.strip()
    return value or None


def _amount_of(node) -> tuple[Decimal, str] | None:
    amt = _find_direct(node, "Amt")
    if amt is None or not amt.text:
        return None
    try:
        value = Decimal(amt.text.strip())
    except InvalidOperation:
        return None
    currency = (amt.attrib.get("Ccy") or "").strip().upper()
    if len(currency) != 3:
        return None
    return value, currency


def _date_of(entry) -> date | None:
    """The VALUE date, and the booking date only as a fallback.

    🔴 THE TWO ARE NOT THE SAME DAY, and this product computes interest on the value date. A
    parser that took the booking date would shift every accrual by the settlement delay —
    two or three days per movement, silently, on every loan the fund holds.
    """
    for tag in ("ValDt", "BookgDt"):
        holder = _find(entry, tag)
        if holder is None:
            continue
        raw = _text(_find(holder, "Dt")) or _text(_find(holder, "DtTm"))
        if not raw:
            continue
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            continue
    return None


def _party_name(node, *roles: str) -> str | None:
    for role in roles:
        holder = _find(node, role)
        if holder is not None:
            name = _text(_find(holder, "Nm"))
            if name:
                return name
    return None


def _party_iban(node, *roles: str) -> str | None:
    for role in roles:
        holder = _find(node, role)
        if holder is not None:
            iban = _text(_find(holder, "IBAN"))
            if iban:
                return iban.replace(" ", "").upper()
    return None


def _label_of(node) -> str | None:
    """The remittance information: the text an investor types into the transfer.

    ⚠️ IT IS THE WHOLE POINT OF THE FILE. With no payment provider, the reference an investor
    copies into the label is the only thing tying their transfer to their call. Several
    `<Ustrd>` lines are joined rather than the first one kept: banks split a long reference
    across them, and keeping only the first truncates it exactly where it matters.
    """
    remittance = _find(node, "RmtInf")
    if remittance is None:
        return None
    parts = [
        child.text.strip()
        for child in remittance.iter()
        if _local(child.tag) == "Ustrd" and child.text and child.text.strip()
    ]
    if parts:
        return " ".join(parts)
    return _text(_find(node, "AddtlNtryInf"))


def parse(content: bytes | str) -> Parsed:
    """Read a CAMT.053 document into statement lines.

    ⚠️ A BATCHED ENTRY IS SPLIT, NOT SUMMED. One `<Ntry>` can bundle several transfers, each
    with its own reference and payer. Recording the entry's total would merge several
    investors' payments into one line, and the matching would fail on all of them at once —
    or worse, attribute the lot to whoever the first reference names.

    ⚠️ A REVERSED ENTRY IS SKIPPED AND SAID. `<RvslInd>true` marks money that came in and
    went back out; counting it as a contribution credits an investor with a payment their
    bank recalled.
    """
    parsed = Parsed()
    try:
        root = ElementTree.fromstring(
            content if isinstance(content, bytes) else content.encode("utf-8")
        )
    except ElementTree.ParseError as exc:
        parsed.refused.append(f"Le fichier n'est pas un XML lisible : {exc}")
        return parsed

    statements = [node for node in root.iter() if _local(node.tag) == "Stmt"]
    if not statements:
        parsed.refused.append(
            "Aucun relevé (<Stmt>) dans ce fichier : ce n'est pas un CAMT.053."
        )
        return parsed

    for statement_index, statement in enumerate(statements, 1):
        account = _find(statement, "Acct")
        iban = _text(_find(account, "IBAN")) if account is not None else None
        if not iban:
            parsed.refused.append(
                f"Relevé {statement_index} : aucun IBAN de compte. Un mouvement sans compte "
                f"ne peut pas être rapproché."
            )
            continue
        iban = iban.replace(" ", "").upper()

        entries = [node for node in statement.iter() if _local(node.tag) == "Ntry"]
        for entry_index, entry in enumerate(entries, 1):
            where = f"Relevé {statement_index}, écriture {entry_index}"

            if (_text(_find(entry, "RvslInd")) or "").lower() == "true":
                parsed.refused.append(
                    f"{where} : contre-passation, ignorée volontairement."
                )
                continue

            indicator = _text(_find(entry, "CdtDbtInd"))
            if indicator not in (_CREDIT, _DEBIT):
                parsed.refused.append(
                    f"{where} : sens du mouvement illisible ({indicator!r}). Il ne sera pas "
                    f"importé plutôt que deviné."
                )
                continue
            direction = "in" if indicator == _CREDIT else "out"

            entry_amount = _amount_of(entry)
            if entry_amount is None:
                parsed.refused.append(f"{where} : montant ou devise illisible.")
                continue

            value_date = _date_of(entry)
            if value_date is None:
                parsed.refused.append(
                    f"{where} : aucune date exploitable. Un mouvement sans date ne peut ni "
                    f"porter d'intérêt ni entrer dans un relevé daté."
                )
                continue

            entry_reference = _text(_find(entry, "NtryRef")) or _text(
                _find(entry, "AcctSvcrRef")
            )

            details = [node for node in entry.iter() if _local(node.tag) == "TxDtls"]
            if not details:
                parsed.lines.append(
                    StatementLine(
                        account_iban=iban,
                        external_id=entry_reference,
                        direction=direction,
                        amount=entry_amount[0],
                        currency=entry_amount[1],
                        value_date=value_date,
                        label=_label_of(entry),
                        counterparty_name=_party_name(entry, "Dbtr", "Cdtr"),
                        counterparty_iban=_party_iban(entry, "DbtrAcct", "CdtrAcct"),
                    )
                )
                continue

            for detail_index, detail in enumerate(details, 1):
                detail_amount = _amount_of(detail) or entry_amount
                reference = (
                    _text(_find(detail, "EndToEndId"))
                    or _text(_find(detail, "TxId"))
                    or (
                        f"{entry_reference}#{detail_index}"
                        if entry_reference and len(details) > 1
                        else entry_reference
                    )
                )
                parsed.lines.append(
                    StatementLine(
                        account_iban=iban,
                        external_id=reference,
                        direction=direction,
                        amount=detail_amount[0],
                        currency=detail_amount[1],
                        value_date=value_date,
                        label=_label_of(detail) or _label_of(entry),
                        counterparty_name=_party_name(detail, "Dbtr", "Cdtr")
                        or _party_name(entry, "Dbtr", "Cdtr"),
                        counterparty_iban=_party_iban(detail, "DbtrAcct", "CdtrAcct")
                        or _party_iban(entry, "DbtrAcct", "CdtrAcct"),
                    )
                )

    return parsed


__all__ = ["Parsed", "StatementLine", "parse"]
