"""The capital account: what moved between two dates, and what was held on either side.

🔴 THE OPENING BALANCE IS THE WHOLE DIFFICULTY. It is not a stored carry-forward — this
product stores no balance anywhere — it is recomputed from the movements dated before the
period. That recomputation is what these tests guard: get it wrong by one day and every
quarterly statement disagrees with the investor's bank by exactly one transfer, on the
boundary, where it is hardest to notice and easiest to dispute.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.core import instruments, kyc
from app.core.landlord_kind_values import PERSON
from app.models.investor import Investor
from app.models.subscription import Subscription
from app.models.treasury import IN, BankMovement, Contribution, Distribution
from app.services import portfolio_service

CURRENCY = "EUR"
Q1_START = date(2026, 1, 1)
Q1_END = date(2026, 3, 31)


async def _investor(db, name: str = "Bernard") -> Investor:
    investor = Investor(
        id=uuid.uuid4(), kind=PERSON, last_name=name, kyc_status=kyc.ACCEPTED
    )
    db.add(investor)
    await db.flush()
    return investor


async def _subscription(db, investor: Investor, committed: str) -> Subscription:
    subscription = Subscription(
        id=uuid.uuid4(),
        investor_id=investor.id,
        instrument=instruments.EQUITY,
        amount=Decimal(committed),
        currency=CURRENCY,
        signed_on=date(2025, 6, 1),
    )
    db.add(subscription)
    await db.flush()
    return subscription


async def _contribute(db, subscription: Subscription, amount: str, on: date) -> None:
    movement = BankMovement(
        id=uuid.uuid4(),
        account_iban="FR7630006000011234567890189",
        direction=IN,
        amount=Decimal(amount),
        currency=CURRENCY,
        value_date=on,
    )
    db.add(movement)
    await db.flush()
    db.add(
        Contribution(
            id=uuid.uuid4(),
            bank_movement_id=movement.id,
            subscription_id=subscription.id,
            amount=Decimal(amount),
            currency=CURRENCY,
        )
    )
    await db.flush()


async def _distribute(
    db,
    subscription: Subscription,
    *,
    capital: str = "0",
    income: str = "0",
    withheld: str = "0",
    paid_on: date | None,
    decided_on: date | None = None,
) -> None:
    db.add(
        Distribution(
            id=uuid.uuid4(),
            subscription_id=subscription.id,
            capital_amount=Decimal(capital),
            income_amount=Decimal(income),
            withholding_amount=Decimal(withheld),
            currency=CURRENCY,
            decided_on=decided_on or paid_on or Q1_START,
            paid_on=paid_on,
        )
    )
    await db.flush()


async def test_the_opening_balance_is_rebuilt_from_before_the_period(db):
    """80 000 paid in last year, 20 000 returned last year: the quarter opens on 60 000."""
    investor = await _investor(db)
    subscription = await _subscription(db, investor, "100000")
    await _contribute(db, subscription, "80000", date(2025, 7, 1))
    await _distribute(db, subscription, capital="20000", paid_on=date(2025, 11, 30))

    [line] = await portfolio_service.capital_account(
        db, investor.id, since=Q1_START, until=Q1_END
    )

    assert line.opening_balance == Decimal("60000")
    assert line.contributions == Decimal("0")
    assert line.closing_balance == Decimal("60000")


async def test_a_movement_on_the_first_day_is_inside_the_period(db):
    """🔴 THE BOUNDARY, AND IT IS INCLUSIVE AT BOTH ENDS.

    A transfer dated on the opening day belongs to the period, not to the balance brought
    forward. Off by one here and the same 30 000 appears in two consecutive statements, or
    in neither.
    """
    investor = await _investor(db)
    subscription = await _subscription(db, investor, "100000")
    await _contribute(db, subscription, "30000", Q1_START)
    await _contribute(db, subscription, "10000", Q1_END)

    [line] = await portfolio_service.capital_account(
        db, investor.id, since=Q1_START, until=Q1_END
    )

    assert line.opening_balance == Decimal("0")
    assert line.contributions == Decimal("40000")


async def test_income_does_not_reduce_the_capital_at_work(db):
    """⚠️ THE SUBTRACTION THAT WOULD UNDERSTATE EVERY FUTURE RETURN.

    A profit distribution is not the investor's capital coming back. Folding the two would
    shrink the base each later return is computed on, quietly and for good.
    """
    investor = await _investor(db)
    subscription = await _subscription(db, investor, "100000")
    await _contribute(db, subscription, "100000", date(2025, 7, 1))
    await _distribute(
        db, subscription, income="9000", withheld="1080", paid_on=date(2026, 2, 15)
    )

    [line] = await portfolio_service.capital_account(
        db, investor.id, since=Q1_START, until=Q1_END
    )

    assert line.income == Decimal("9000")
    assert line.capital_returned == Decimal("0")
    assert line.closing_balance == Decimal("100000")
    # What actually reached their bank, withholding deducted.
    assert line.net_paid == Decimal("7920")


async def test_a_decided_but_unpaid_distribution_is_not_on_the_statement(db):
    """It is a promise, and a statement records movements. Counting it would tell an
    investor money reached them while it is still in the fund's account."""
    investor = await _investor(db)
    subscription = await _subscription(db, investor, "100000")
    await _contribute(db, subscription, "100000", date(2025, 7, 1))
    await _distribute(
        db, subscription, income="5000", paid_on=None, decided_on=date(2026, 3, 20)
    )

    [line] = await portfolio_service.capital_account(
        db, investor.id, since=Q1_START, until=Q1_END
    )

    assert line.income == Decimal("0")
    assert line.net_paid == Decimal("0")


async def test_returned_capital_does_not_become_callable_again(db):
    """⚠️ THE REMAINING COMMITMENT IS MEASURED ON WHAT WAS CONTRIBUTED, not on what is still
    at work. Otherwise a fund that returned capital could call it a second time, and the
    figure on screen would invite it."""
    investor = await _investor(db)
    subscription = await _subscription(db, investor, "100000")
    await _contribute(db, subscription, "100000", date(2025, 7, 1))
    await _distribute(db, subscription, capital="40000", paid_on=date(2026, 2, 1))

    [line] = await portfolio_service.capital_account(
        db, investor.id, since=Q1_START, until=Q1_END
    )

    assert line.closing_balance == Decimal("60000")
    assert line.outstanding_commitment == Decimal("0")


async def test_a_period_that_ends_before_it_begins_is_refused(db):
    investor = await _investor(db)
    await _subscription(db, investor, "100000")
    try:
        await portfolio_service.capital_account(
            db, investor.id, since=Q1_END, until=Q1_START
        )
    except ValueError as exc:
        assert "avant de commencer" in str(exc)
    else:  # pragma: no cover - the refusal is the point
        raise AssertionError("Une période inversée doit être refusée, pas calculée.")
