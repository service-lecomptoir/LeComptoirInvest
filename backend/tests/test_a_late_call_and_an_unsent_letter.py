"""Late capital calls: what is really owed, and who is actually late.

🔴 `due_on` WAS STORED, INDEXED AND DISPLAYED, AND NOTHING COMPARED IT TO TODAY. A fund
could issue a call, watch the date go by, and the only trace was a row in a list sorted by a
date nobody read. Calling capital is how a fund funds itself; not knowing which calls are
short is not a reporting gap, it is not knowing whether the money is coming.

The two mistakes this guards are both the kind that destroy a fund's standing with its own
investors, and neither looks like a bug:

  * dunning somebody for the FULL amount when they paid most of it — partial payment is the
    norm on large sums, and the letter is wrong in the one way an investor never forgets;
  * chasing somebody for a notice THE FUND NEVER SENT — the fund's own omission, presented
    to the investor as their lateness.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.core import instruments, kyc
from app.core.landlord_kind_values import PERSON
from app.models.investor import Investor
from app.models.subscription import Subscription
from app.models.treasury import IN, BankMovement, CapitalCall, Contribution
from app.services import call_chasing_service

CURRENCY = "EUR"
DUE_ON = date(2026, 3, 1)
#: Sixty days after the due date, so the arithmetic is checkable by hand.
TODAY = date(2026, 4, 30)


async def _call(
    db,
    *,
    amount: str = "100000",
    late_rate: float | None = None,
    notified: bool = True,
    last_reminded_on: date | None = None,
) -> CapitalCall:
    investor = Investor(
        id=uuid.uuid4(), kind=PERSON, last_name="Bernard", kyc_status=kyc.ACCEPTED
    )
    db.add(investor)
    await db.flush()
    subscription = Subscription(
        id=uuid.uuid4(),
        investor_id=investor.id,
        instrument=instruments.EQUITY,
        amount=Decimal(amount),
        currency=CURRENCY,
        signed_on=date(2026, 1, 1),
    )
    db.add(subscription)
    await db.flush()
    call = CapitalCall(
        id=uuid.uuid4(),
        subscription_id=subscription.id,
        reference=f"INV{uuid.uuid4().hex[:8].upper()}",
        amount=Decimal(amount),
        currency=CURRENCY,
        called_on=date(2026, 2, 1),
        due_on=DUE_ON,
        notified_on=date(2026, 2, 2) if notified else None,
        late_interest_rate=late_rate,
        last_reminded_on=last_reminded_on,
    )
    db.add(call)
    await db.flush()
    return call


async def _pay(db, call: CapitalCall, amount: str) -> None:
    movement = BankMovement(
        id=uuid.uuid4(),
        account_iban="FR7630006000011234567890189",
        direction=IN,
        amount=Decimal(amount),
        currency=CURRENCY,
        value_date=date(2026, 3, 15),
    )
    db.add(movement)
    await db.flush()
    db.add(
        Contribution(
            id=uuid.uuid4(),
            bank_movement_id=movement.id,
            subscription_id=call.subscription_id,
            capital_call_id=call.id,
            amount=Decimal(amount),
            currency=CURRENCY,
        )
    )
    await db.flush()


async def test_a_call_paid_in_full_never_appears(db):
    """Being late and having paid are different states. A list that kept settled rows
    « for the record » is a list nobody can work from."""
    call = await _call(db)
    await _pay(db, call, "100000")

    assert await call_chasing_service.late_calls(db, as_of=TODAY) == []


async def test_what_is_owed_is_the_shortfall_never_the_called_amount(db):
    """🔴 THE LETTER THAT DESTROYS A FUND'S CREDIBILITY. Ninety per cent paid, and the
    reminder asks for the whole hundred."""
    call = await _call(db, amount="100000")
    await _pay(db, call, "90000")

    [late] = await call_chasing_service.late_calls(db, as_of=TODAY)

    assert late.called == Decimal("100000")
    assert late.received == Decimal("90000")
    assert late.outstanding == Decimal("10000")


async def test_late_interest_runs_on_the_shortfall_from_the_day_after_the_due_date(db):
    """8 % a year on 10 000 unpaid, sixty days: 131.51 on ACT/365.

    ⚠️ FROM THE DAY AFTER. Charging the due date itself bills an investor who paid on the
    last day they were given, which is the one day the notice told them they still had.
    """
    call = await _call(db, amount="100000", late_rate=0.08)
    await _pay(db, call, "90000")

    [late] = await call_chasing_service.late_calls(db, as_of=TODAY)

    assert late.days_late == 60
    assert late.late_interest == Decimal("131.51")


async def test_a_call_with_no_rate_costs_nothing_extra(db):
    """NULL is a decision the call records, not an omission to be filled in later."""
    call = await _call(db, amount="100000", late_rate=None)
    await _pay(db, call, "40000")

    [late] = await call_chasing_service.late_calls(db, as_of=TODAY)

    assert late.late_interest == Decimal("0")
    assert late.outstanding == Decimal("60000")


async def test_a_call_that_was_never_notified_is_flagged_and_not_chased(db):
    """🔴 THE FUND IS LATE, NOT THE INVESTOR. A reminder here tells somebody they are late
    for a demand they never received."""
    await _call(db, amount="50000", notified=False)

    [late] = await call_chasing_service.late_calls(db, as_of=TODAY)
    assert late.never_notified is True

    due, why = call_chasing_service.due_for_reminder(late, as_of=TODAY)
    assert due is False
    assert "jamais été notifié" in why


async def test_a_reminder_sent_recently_holds_the_next_one_back(db):
    """⚠️ ONE REMINDER IS NOT A CAMPAIGN. Without a floor, a nightly job writes to the same
    investor every morning until they pay, which teaches them to filter the fund's mail."""
    await _call(db, amount="50000", last_reminded_on=date(2026, 4, 25))

    [late] = await call_chasing_service.late_calls(db, as_of=TODAY)
    due, why = call_chasing_service.due_for_reminder(late, as_of=TODAY)

    assert due is False
    assert "2026-05-10" in why


async def test_a_reminder_is_due_once_the_interval_has_passed(db):
    await _call(db, amount="50000", last_reminded_on=date(2026, 4, 1))

    [late] = await call_chasing_service.late_calls(db, as_of=TODAY)
    due, why = call_chasing_service.due_for_reminder(late, as_of=TODAY)

    assert due is True and why is None


async def test_a_call_not_yet_due_is_not_late(db):
    """The boundary: on the due date itself the investor still has the day."""
    await _call(db, amount="50000")

    assert await call_chasing_service.late_calls(db, as_of=DUE_ON) == []
