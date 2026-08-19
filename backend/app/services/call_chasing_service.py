"""Capital calls that are late: what is still owed, since when, and what it costs.

🔴 `due_on` WAS STORED, INDEXED, DISPLAYED — AND ACTED ON BY NOTHING. A fund could issue a
call, watch the date pass, and the only trace was a row in a list sorted by a date nobody
compared to today. Calling capital is how a fund funds itself; not knowing which calls are
unpaid is not a reporting gap, it is not knowing whether the money is coming.

⚠️ WHAT IS OWED ON A CALL IS NOT ITS AMOUNT. It is the amount minus what actually arrived
against it, and partial payment is the norm on large sums. A chaser that reminded people of
the full figure would dun an investor who paid ninety per cent of it, and the letter would
be wrong in the one way that destroys the fund's credibility with its own investors.

⚠️ AND A CALL NOBODY RECEIVED IS NOT A LATE INVESTOR. `notified_on` empty means the notice
never went out: the fund is late, not the investor. Those two are separated here rather than
summed, because a chasing list that mixes them sends a reminder for a letter never sent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import accrual, money
from app.models.investor import Investor
from app.models.subscription import Subscription
from app.models.treasury import CapitalCall, Contribution
from app.core.i18n import pick


@dataclass(frozen=True)
class LateCall:
    """One call past its due date, with what is still missing and what that has cost."""

    call_id: uuid.UUID
    reference: str
    investor_id: uuid.UUID
    investor_name: str
    subscription_id: uuid.UUID
    currency: str
    called: Decimal
    #: What arrived against this call. Partial is normal.
    received: Decimal
    due_on: date
    days_late: int
    #: Interest run up on the unpaid part since the day after the due date. Zero when the
    #: call carries no rate — which is a decision the call records, not an omission.
    late_interest: Decimal
    #: True when the notice was never sent: the fund is late, not the investor.
    never_notified: bool
    last_reminded_on: date | None

    @property
    def outstanding(self) -> Decimal:
        return self.called - self.received


def late_interest_on(call: CapitalCall, *, received: Decimal, as_of: date) -> Decimal:
    """What the delay on this call has cost, on `as_of`.

    🔴 ONE HOME FOR THE FIGURE. The chasing list shows it and the reminder letter states it
    to the investor; computing it twice would let the screen and the letter disagree about
    what somebody owes, and the letter is the one they would act on.

    🔴 INTEREST RUNS FROM THE DAY AFTER THE DUE DATE. Charging the due date itself would bill
    an investor who paid on the last day they were given, which is the one day the notice
    told them they still had.

    ⚠️ AND NO RATE MEANS NO INTEREST, not a default one. `late_interest_rate` is NULL when
    the call was issued without one, which is a decision the call records; substituting a
    fund-wide figure would charge an investor something they were never told about.
    """
    outstanding = call.amount - received
    if outstanding <= 0 or not call.late_interest_rate:
        return Decimal("0")
    return money.quantize(
        accrual.interest_accrued(
            principal=outstanding,
            rate=call.late_interest_rate,
            since=call.due_on,
            until=as_of,
            currency=call.currency,
        ),
        call.currency,
    )


async def late_calls(db: AsyncSession, *, as_of: date) -> list[LateCall]:
    """Every call still short on `as_of`, oldest first.

    ⚠️ A CALL PAID IN FULL NEVER APPEARS, whatever its date. Being late and having paid are
    different states, and a list that kept settled rows « for the record » is a list nobody
    can work from.
    """
    rows = (
        await db.execute(
            select(CapitalCall, Subscription, Investor)
            .join(Subscription, Subscription.id == CapitalCall.subscription_id)
            .join(Investor, Investor.id == Subscription.investor_id)
            .where(CapitalCall.due_on < as_of)
            .order_by(CapitalCall.due_on)
        )
    ).all()
    if not rows:
        return []

    received: dict[uuid.UUID, Decimal] = {}
    for call_id, amount in (
        await db.execute(
            select(Contribution.capital_call_id, Contribution.amount).where(
                Contribution.capital_call_id.in_([c.id for c, _, _ in rows])
            )
        )
    ).all():
        if call_id is None:
            continue
        received[call_id] = received.get(call_id, Decimal("0")) + amount

    out: list[LateCall] = []
    for call, subscription, investor in rows:
        paid = received.get(call.id, Decimal("0"))
        outstanding = call.amount - paid
        if outstanding <= 0:
            continue
        interest = late_interest_on(call, received=paid, as_of=as_of)
        out.append(
            LateCall(
                call_id=call.id,
                reference=call.reference,
                investor_id=investor.id,
                investor_name=investor.display_name,
                subscription_id=subscription.id,
                currency=call.currency,
                called=call.amount,
                received=paid,
                due_on=call.due_on,
                days_late=(as_of - call.due_on).days,
                late_interest=interest,
                never_notified=call.notified_on is None,
                last_reminded_on=call.last_reminded_on,
            )
        )
    return out


def due_for_reminder(
    late: LateCall, *, as_of: date, every_days: int = 15
) -> tuple[bool, str | None]:
    """Should a reminder go out for this call today, and if not, why not?

    🔴 A REMINDER FOR A NOTICE THAT WAS NEVER SENT IS NOT A REMINDER. It tells an investor
    they are late for a demand they never received, which is the fund's own failure dressed
    up as theirs. Those are reported so somebody sends the first notice instead.

    ⚠️ AND ONE REMINDER IS NOT A CAMPAIGN. Without a floor between two, a nightly job writes
    to the same investor every morning until they pay — which is how a fund teaches its
    investors to filter its e-mails.
    """
    if late.never_notified:
        return False, pick(
            f"L'appel {late.reference} n'a jamais été notifié : c'est le premier avis qui "
            f"manque, pas une relance.",
            f"Call {late.reference} has never been notified: what is missing is the first "
            f"notice, not a reminder.",
        )
    if late.last_reminded_on is not None:
        next_allowed = late.last_reminded_on + timedelta(days=every_days)
        if as_of < next_allowed:
            return False, pick(
                f"Dernière relance le {late.last_reminded_on.isoformat()} : la suivante "
                f"n'est pas due avant le {next_allowed.isoformat()}.",
                f"Last reminded on {late.last_reminded_on.isoformat()}: the next one is not "
                f"due before {next_allowed.isoformat()}.",
            )
    return True, None


__all__ = ["LateCall", "due_for_reminder", "late_calls", "late_interest_on"]
