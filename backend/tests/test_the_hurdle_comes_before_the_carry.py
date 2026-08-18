"""The three tiers that stood between a promise and the manager's pocket.

🔴 WHAT THIS GUARDS, AND WHY IT WAS NOT GUARDED BEFORE. `EquityTerms` declared
`preferred_return` and `carried_interest` from the first day. Neither was ever read: the
waterfall rebuilt `LoanTerms` from stored JSON and had no `_equity_terms` at all. So the
class documented a hurdle, the screen let a manager record one, and every surplus went to
the subscribers pro rata as if no clause existed.

That failure has two faces and only one of them is visible:

  * the manager was paid NOTHING on performance, on a fund whose whole compensation is the
    carry — noticeable, eventually, by the person not being paid;
  * and had the carry merely been applied without the hurdle, subscribers would have paid a
    performance fee on the first euro back, including on a wind-down that returned their own
    capital. NOBODY detects that from the figure they receive.

It is the same shape as `DISTRIBUTION_ORDER` before the waterfall existed: a rule written
down, tested for its own identity, and applied nowhere.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core import instruments, kyc
from app.core.landlord_kind_values import PERSON
from app.models.investor import Investor
from app.models.subscription import Subscription
from app.models.treasury import IN, BankMovement, Contribution
from app.services import distribution_service

CURRENCY = "EUR"
DRAWN_ON = date(2025, 1, 1)
ONE_YEAR_LATER = date(2026, 1, 1)


async def _subscriber(
    db,
    *,
    name: str,
    amount: str,
    preferred_return: float = 0.0,
    carried_interest: float = 0.0,
    management_fee: float = 0.0,
) -> Subscription:
    """One subscriber who signed, paid in full on `DRAWN_ON`, and holds the fund's terms."""
    investor = Investor(
        id=uuid.uuid4(), kind=PERSON, last_name=name, kyc_status=kyc.ACCEPTED
    )
    db.add(investor)
    await db.flush()

    subscription = Subscription(
        id=uuid.uuid4(),
        investor_id=investor.id,
        instrument=instruments.EQUITY,
        amount=Decimal(amount),
        currency=CURRENCY,
        signed_on=DRAWN_ON,
        terms={
            "preferred_return": preferred_return,
            "carried_interest": carried_interest,
            "management_fee": management_fee,
        },
    )
    db.add(subscription)
    await db.flush()

    movement = BankMovement(
        id=uuid.uuid4(),
        account_iban="FR7630006000011234567890189",
        direction=IN,
        amount=Decimal(amount),
        currency=CURRENCY,
        value_date=DRAWN_ON,
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
    return subscription


async def _propose(db, amount: str, *, repay_capital: bool = False):
    return await distribution_service.propose(
        db,
        currency=CURRENCY,
        amount=Decimal(amount),
        as_of=ONE_YEAR_LATER,
        repay_capital=repay_capital,
    )


async def test_the_manager_takes_nothing_below_the_hurdle(db):
    """🔴 THE CASE THE MISSING TIER GOT WRONG IN THE SUBSCRIBERS' FAVOUR IS NOT THIS ONE.

    100 000 at work, an 8 % preference, one year gone: the first 8 000 belong to the
    subscriber whatever the carry says. A waterfall that applied the carry without the
    hurdle would hand 20 % of this away.
    """
    await _subscriber(
        db,
        name="Bernard",
        amount="100000",
        preferred_return=0.08,
        carried_interest=0.20,
    )

    waterfall = await _propose(db, "5000")

    assert waterfall.carried_interest == Decimal("0")
    assert waterfall.distributed == Decimal("5000")
    assert waterfall.shares[0].income_amount == Decimal("5000")
    # Still 3 000 short of the threshold, and the screen says so rather than implying it.
    assert waterfall.preferred_remaining == Decimal("3000")


async def test_the_carry_applies_only_to_what_exceeds_the_hurdle(db):
    """20 % of the EXCESS, never of the whole.

    12 000 available, 8 000 of preference: the carry bites on 4 000, so 800 to the manager
    and 3 200 to the subscriber. A carry on the whole would have taken 2 400 — three times
    too much, out of money that was promised first.
    """
    await _subscriber(
        db,
        name="Bernard",
        amount="100000",
        preferred_return=0.08,
        carried_interest=0.20,
    )

    waterfall = await _propose(db, "12000")

    assert waterfall.preferred_remaining == Decimal("0")
    assert waterfall.carried_interest == Decimal("800")
    assert waterfall.shares[0].income_amount == Decimal("11200")
    # Nothing is lost between the tiers: what the fund keeps is a decision, not a rounding.
    assert waterfall.distributed == Decimal("12000")
    assert waterfall.undistributed == Decimal("0")


async def test_a_wind_down_pays_no_carry_on_returned_capital(db):
    """🔴 THE ONE NOBODY WOULD HAVE CAUGHT. Giving a subscriber their own money back is not
    a performance, and a carry taken on it is a fee on nothing.

    100 000 back plus 8 000 of preference, on a distribution flagged as a repayment: the
    manager takes zero, because nothing exceeded the hurdle.
    """
    await _subscriber(
        db,
        name="Bernard",
        amount="100000",
        preferred_return=0.08,
        carried_interest=0.20,
    )

    waterfall = await _propose(db, "108000", repay_capital=True)

    assert waterfall.carried_interest == Decimal("0")
    assert waterfall.shares[0].capital_amount == Decimal("100000")
    assert waterfall.shares[0].income_amount == Decimal("8000")


async def test_the_preference_is_net_of_what_was_already_served(db):
    """A second distribution must not re-owe the preference from inception.

    The subscriber already received 8 000 of income; a year has not passed twice. What is
    left of the hurdle is nothing, so the carry starts on the first euro of this proposal.
    """
    subscription = await _subscriber(
        db,
        name="Bernard",
        amount="100000",
        preferred_return=0.08,
        carried_interest=0.20,
    )
    from app.models.treasury import Distribution

    db.add(
        Distribution(
            id=uuid.uuid4(),
            subscription_id=subscription.id,
            capital_amount=Decimal("0"),
            income_amount=Decimal("8000"),
            currency=CURRENCY,
            decided_on=ONE_YEAR_LATER,
        )
    )
    await db.flush()

    waterfall = await _propose(db, "10000")

    assert waterfall.preferred_remaining == Decimal("0")
    assert waterfall.carried_interest == Decimal("2000")
    assert waterfall.shares[0].income_amount == Decimal("8000")


async def test_a_fund_with_no_terms_behaves_exactly_as_before(db):
    """⚠️ NO TERMS MEANS NO HURDLE AND NO CARRY, and that is the crowdfunding case.

    A vehicle that never agreed a manager's fee must not be given one by this module. The
    whole surplus goes to the subscribers, which is the waterfall as it stood before the
    three tiers existed.
    """
    await _subscriber(db, name="Bernard", amount="100000")

    waterfall = await _propose(db, "9000")

    assert waterfall.carried_interest == Decimal("0")
    assert waterfall.preferred_remaining == Decimal("0")
    assert waterfall.shares[0].income_amount == Decimal("9000")


async def test_subscribers_on_different_terms_are_refused_not_averaged(db):
    """🔴 REFUSE RATHER THAN PRODUCE A PLAUSIBLE WRONG NUMBER.

    A hurdle and a carry describe the VEHICLE. Two subscribers carrying different rates
    describe a per-class waterfall this module does not compute. Averaging, or taking the
    first, would answer with a figure whose error comes out of somebody's share and shows
    nowhere.
    """
    await _subscriber(
        db,
        name="Bernard",
        amount="100000",
        preferred_return=0.08,
        carried_interest=0.20,
    )
    await _subscriber(
        db, name="Claire", amount="100000", preferred_return=0.06, carried_interest=0.20
    )

    waterfall = await _propose(db, "50000")

    assert waterfall.shares == []
    assert waterfall.carried_interest == Decimal("0")
    assert waterfall.blocked_reason is not None
    assert "conditions" in waterfall.blocked_reason


async def test_the_carry_never_outranks_a_lender(db):
    """The new tiers sit UNDER the existing guard, they do not go around it.

    A lender still owed money blocks the subscribers, and therefore the manager too: a
    carry paid while a creditor is short is the default the whole module exists to prevent.
    """
    await _subscriber(
        db,
        name="Bernard",
        amount="100000",
        preferred_return=0.08,
        carried_interest=0.20,
    )
    lender = Investor(
        id=uuid.uuid4(), kind=PERSON, last_name="Prêteur", kyc_status=kyc.ACCEPTED
    )
    db.add(lender)
    await db.flush()
    loan = Subscription(
        id=uuid.uuid4(),
        investor_id=lender.id,
        instrument=instruments.LOAN,
        amount=Decimal("50000"),
        currency=CURRENCY,
        signed_on=DRAWN_ON,
        ends_on=date(2030, 1, 1),
        terms={"rate": 0.05, "term_months": 60, "bullet": True},
    )
    db.add(loan)
    await db.flush()
    movement = BankMovement(
        id=uuid.uuid4(),
        account_iban="FR7630006000011234567890189",
        direction=IN,
        amount=Decimal("50000"),
        currency=CURRENCY,
        value_date=DRAWN_ON,
    )
    db.add(movement)
    await db.flush()
    db.add(
        Contribution(
            id=uuid.uuid4(),
            bank_movement_id=movement.id,
            subscription_id=loan.id,
            amount=Decimal("50000"),
            currency=CURRENCY,
        )
    )
    await db.flush()

    # 1 000 available against 2 500 of interest owed: the lender is not covered.
    waterfall = await _propose(db, "1000")

    assert waterfall.carried_interest == Decimal("0")
    assert waterfall.debt_remaining > 0
    assert waterfall.blocked_reason is not None
    assert all(s.instrument == instruments.LOAN for s in waterfall.shares)


@pytest.mark.parametrize("carry", [0.20, 0.10])
async def test_nothing_is_lost_between_the_tiers(db, carry: float):
    """Every euro available is either shared, carried, or visibly kept. Never absorbed."""
    await _subscriber(
        db,
        name="Bernard",
        amount="100000",
        preferred_return=0.08,
        carried_interest=carry,
    )
    await _subscriber(
        db, name="Claire", amount="60000", preferred_return=0.08, carried_interest=carry
    )

    waterfall = await _propose(db, "33333.33")

    shared = sum((s.gross_amount for s in waterfall.shares), Decimal("0"))
    assert shared + waterfall.carried_interest + waterfall.undistributed == Decimal(
        "33333.33"
    )


async def test_a_management_fee_is_owed_even_when_nothing_exceeds_the_hurdle(db):
    """🔴 THE DIFFERENCE BETWEEN A FEE AND A CARRY, IN ONE CASE.

    100 000 at work for a year, a 2 % fee and an 8 % hurdle. Only 5 000 is available: the
    hurdle is nowhere near met, so the carry is zero — and the fee is still owed, because
    running the vehicle cost what it cost. A fund reporting one combined figure would tell
    its subscribers the manager earned nothing this year.
    """
    await _subscriber(
        db,
        name="Bernard",
        amount="100000",
        preferred_return=0.08,
        carried_interest=0.20,
        management_fee=0.02,
    )

    waterfall = await _propose(db, "5000")

    assert waterfall.management_fee == Decimal("2000")
    assert waterfall.carried_interest == Decimal("0")
    # What is left after the fee goes to the subscriber, against their preference.
    assert waterfall.shares[0].income_amount == Decimal("3000")
    assert waterfall.distributed == Decimal("5000")


async def test_the_fee_comes_before_the_hurdle_not_after(db):
    """⚠️ THE ORDER DECIDES WHO PAYS FOR A GOOD YEAR.

    12 000 available: 2 000 of fee first, then the 8 000 preference on what remains, leaving
    2 000 above the hurdle of which the manager carries 20 %. Taking the fee AFTER would let
    the subscriber absorb it out of their preference, and the carry would be computed on a
    base that was never theirs.
    """
    await _subscriber(
        db,
        name="Bernard",
        amount="100000",
        preferred_return=0.08,
        carried_interest=0.20,
        management_fee=0.02,
    )

    waterfall = await _propose(db, "12000")

    assert waterfall.management_fee == Decimal("2000")
    assert waterfall.preferred_remaining == Decimal("0")
    assert waterfall.carried_interest == Decimal("400")
    assert waterfall.shares[0].income_amount == Decimal("9600")
    assert waterfall.distributed == Decimal("12000")


async def test_no_fee_agreed_means_no_fee_taken(db):
    """A crowdfunding vehicle that never agreed a management fee must not be given one."""
    await _subscriber(
        db,
        name="Bernard",
        amount="100000",
        preferred_return=0.08,
        carried_interest=0.20,
    )

    waterfall = await _propose(db, "12000")

    assert waterfall.management_fee == Decimal("0")
