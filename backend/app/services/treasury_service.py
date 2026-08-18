"""Reading a statement, proposing attributions, and recording the ones a human confirms.

This is where the pure rules of `app.core.matching` meet the database. The split is
deliberate: the rule that decides whose money a transfer is has no business knowing about
sessions, and it is tested without one.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import kyc
from app.core.matching import Candidate, Proposal, propose
from app.models.investor import Investor
from app.models.subscription import Subscription
from app.models.treasury import IN, BankMovement, CapitalCall, Contribution


async def _candidates(db: AsyncSession) -> list[Candidate]:
    """Every investor, with the three things that could tie a transfer to them.

    Loaded in three queries rather than per investor: a fund with two hundred investors and
    a statement of eighty lines would otherwise issue sixteen thousand.
    """
    investors = (await db.execute(select(Investor))).scalars().all()
    calls = (
        await db.execute(
            select(
                CapitalCall.reference, CapitalCall.id, Subscription.investor_id
            ).join(Subscription, Subscription.id == CapitalCall.subscription_id)
        )
    ).all()
    by_investor: dict[uuid.UUID, dict[str, str]] = {}
    for reference, call_id, investor_id in calls:
        by_investor.setdefault(investor_id, {})[reference] = str(call_id)

    return [
        Candidate(
            investor_id=str(i.id),
            display_name=i.display_name,
            virtual_iban=i.virtual_iban,
            iban_fingerprint=i.iban_fingerprint,
            open_call_references=by_investor.get(i.id, {}),
        )
        for i in investors
    ]


async def propose_for(db: AsyncSession, movement: BankMovement) -> Proposal:
    """What this statement line probably is. A proposal, never an attribution."""
    from app.core import crypto

    return propose(
        received_on_iban=movement.account_iban,
        label=movement.label,
        payer_name=movement.counterparty_name,
        payer_iban_fingerprint=crypto.fingerprint(movement.counterparty_iban),
        amount=movement.amount,
        candidates=await _candidates(db),
    )


async def unattributed(db: AsyncSession) -> list[BankMovement]:
    """Incoming lines with nothing imputed against them yet.

    THE PILE THAT MUST STAY SHORT. Money the fund holds and cannot name is money it cannot
    deploy, cannot report, and cannot answer an investor about. Everything else in this
    module exists to keep this list empty.
    """
    attributed = select(Contribution.bank_movement_id).distinct().scalar_subquery()
    rows = await db.execute(
        select(BankMovement)
        .where(BankMovement.direction == IN, BankMovement.id.not_in(attributed))
        .order_by(BankMovement.value_date)
    )
    return list(rows.scalars().all())


async def attribute(
    db: AsyncSession,
    *,
    movement: BankMovement,
    subscription: Subscription,
    amount: Decimal,
    capital_call: CapitalCall | None,
    attributed_by: str,
    #: ⚠️ THE DAY THE CHECK IS MADE, PASSED IN. Whether an acceptance has aged out depends on
    #: a date, and a service that read the machine's own clock would answer differently for
    #: two callers in different timezones, on the same file.
    today: date,
    third_party_reason: str | None = None,
) -> Contribution:
    """Record that this share of this transfer belongs to this subscription.

    🔴 THE KYC VERDICT IS CHECKED HERE, at the one place money actually enters. A check on
    the screen that offers the button is a check that is missing from every other way in —
    an import, a correction, a script — and the whole point of a verdict is that it stops
    something.

    ⚠️ THE MOVEMENT IS NOT OVER-ATTRIBUTED. A transfer split across several subscriptions is
    normal; a transfer split into more than it carried is money the fund never received,
    and it would reconcile to nothing at the bank while looking perfectly balanced here.
    """
    investor = await db.get(Investor, subscription.investor_id)
    if investor is None:
        raise ValueError("Souscription sans investisseur : imputation impossible.")
    # 🔴 ONE HOME FOR THE RULE, and it now covers an acceptance that aged out. Reading the
    # status alone let a file whose review was three years overdue keep taking money, with
    # the due date displayed on the record the whole time.
    refusal = kyc.refusal_reason(
        status=investor.kyc_status,
        accepted_on=investor.kyc_decided_on,
        risk_level=investor.kyc_risk_level,
        today=today,
    )
    if refusal:
        raise ValueError(f"{investor.display_name} : {refusal}")
    if movement.currency != subscription.currency:
        raise ValueError(
            f"Le virement est en {movement.currency} et la souscription en "
            f"{subscription.currency}. Une conversion est un événement daté, à un cours "
            f"donné, pas une imputation."
        )

    already = (
        (
            await db.execute(
                select(Contribution.amount).where(
                    Contribution.bank_movement_id == movement.id
                )
            )
        )
        .scalars()
        .all()
    )
    remaining = movement.amount - sum(already, Decimal("0"))
    if amount > remaining:
        raise ValueError(
            f"Ce virement ne porte plus que {remaining} {movement.currency} à imputer, "
            f"et {amount} sont demandés."
        )

    # A payer who is not the investor is recorded as such rather than blocked: it is often
    # legitimate, and it is exactly what identification rules exist to surface.
    from app.core.matching import _names_agree

    is_third_party = not _names_agree(movement.counterparty_name, investor.display_name)

    contribution = Contribution(
        bank_movement_id=movement.id,
        subscription_id=subscription.id,
        capital_call_id=capital_call.id if capital_call else None,
        amount=amount,
        currency=movement.currency,
        third_party_payer=is_third_party,
        third_party_reason=third_party_reason,
        attributed_by=attributed_by,
    )
    db.add(contribution)
    await db.flush()
    return contribution


async def treasury_by_currency(db: AsyncSession) -> dict[str, Decimal]:
    """The invariant, evaluated. One balance per currency, never a single total.

    A figure mixing euros and CFA francs is not a treasury: it is a number that is a balance
    nowhere, and it looks plausible because it sums real amounts.
    """

    out: dict[str, Decimal] = {}
    rows = await db.execute(
        select(BankMovement.currency, BankMovement.direction, BankMovement.amount)
    )
    for currency, direction, amount in rows.all():
        sign = Decimal("1") if direction == IN else Decimal("-1")
        out[currency] = out.get(currency, Decimal("0")) + sign * amount
    return out


async def next_call_reference(db: AsyncSession) -> str:
    """A reference no open call already carries.

    The database's unique index is what makes a collision impossible; this loop only makes
    it improbable enough that the index never has to fire.
    """
    from app.core import references

    for _ in range(10):
        candidate = references.generate()
        exists = (
            await db.execute(
                select(CapitalCall.id).where(CapitalCall.reference == candidate)
            )
        ).first()
        if exists is None:
            return candidate
    raise RuntimeError(
        "Impossible de générer une référence libre après dix tentatives."
    )


async def open_call(
    db: AsyncSession,
    *,
    subscription: Subscription,
    amount: Decimal,
    due_on: date,
    called_on: date,
) -> CapitalCall:
    """Ask an investor for part of what they committed.

    ⚠️ A CALL IS NOT MONEY, and this function creates no contribution. It creates a demand
    with a reference on it; the money arrives later, on a statement, and is attributed then.
    """
    call = CapitalCall(
        subscription_id=subscription.id,
        reference=await next_call_reference(db),
        amount=amount,
        currency=subscription.currency,
        called_on=called_on,
        due_on=due_on,
    )
    db.add(call)
    await db.flush()
    return call
