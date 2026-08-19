"""Two vehicles, and everything that used to be scoped by currency alone.

🔴 SCOPING BY CURRENCY WAS RIGHT WITH ONE FUND AND CATASTROPHIC WITH TWO. The waterfall, the
net asset value and the performance all selected « every open subscription in EUR ». The day
a second vehicle exists, fund A's cash goes to fund B's subscribers — and every total
reconciles, because nothing was lost. It merely went to the wrong people.

⚠️ AND THE CASH IS THE ONE THING THAT CANNOT BE SPLIT BY A RULE. Projects and commitments
carry a `fund_id`; a bank statement line does not, and cannot: it says nothing about which
vehicle the euro was for. Two funds on one account therefore have NO computable net asset
value, and this is guarded as a refusal rather than a division.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.core import instruments, kyc
from app.core.landlord_kind_values import PERSON
from app.models.fund import Fund
from app.models.investor import Investor
from app.models.project import ACTIVE, Project, ProjectValuation
from app.models.subscription import Subscription
from app.models.treasury import IN, BankMovement, Contribution
from app.services import distribution_service, valuation_service

CURRENCY = "EUR"
AS_OF = date(2026, 6, 30)
IBAN_A = "FR7630006000011111111111111"
IBAN_B = "FR7630006000012222222222222"


async def _fund(
    db, name: str, *, iban: str | None = None, terms: dict | None = None
) -> Fund:
    fund = Fund(id=uuid.uuid4(), name=name, currency=CURRENCY, iban=iban, terms=terms)
    db.add(fund)
    await db.flush()
    return fund


async def _subscriber(
    db, name: str, amount: str, *, fund: Fund | None = None, iban: str = IBAN_A
) -> Subscription:
    investor = Investor(
        id=uuid.uuid4(), kind=PERSON, last_name=name, kyc_status=kyc.ACCEPTED
    )
    db.add(investor)
    await db.flush()
    subscription = Subscription(
        id=uuid.uuid4(),
        fund_id=fund.id if fund else None,
        investor_id=investor.id,
        instrument=instruments.EQUITY,
        amount=Decimal(amount),
        currency=CURRENCY,
        signed_on=date(2026, 1, 1),
    )
    db.add(subscription)
    await db.flush()
    movement = BankMovement(
        id=uuid.uuid4(),
        account_iban=iban,
        direction=IN,
        amount=Decimal(amount),
        currency=CURRENCY,
        value_date=date(2026, 1, 5),
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


async def _valued_project(
    db, name: str, worth: str, *, fund: Fund | None = None
) -> Project:
    project = Project(
        id=uuid.uuid4(),
        fund_id=fund.id if fund else None,
        name=name,
        status=ACTIVE,
        currency=CURRENCY,
    )
    db.add(project)
    await db.flush()
    db.add(
        ProjectValuation(
            id=uuid.uuid4(),
            project_id=project.id,
            valued_on=AS_OF,
            amount=Decimal(worth),
            currency=CURRENCY,
            valued_by="gestion@fonds.test",
        )
    )
    await db.flush()
    return project


async def test_a_distribution_serves_only_its_own_subscribers(db):
    """🔴 THE DEFECT THE VEHICLE EXISTS TO PREVENT. Without the scope, distributing 10 000 in
    EUR would split it between both funds' subscribers — and reconcile."""
    fund_a = await _fund(db, "Fonds A", iban=IBAN_A)
    fund_b = await _fund(db, "Fonds B", iban=IBAN_B)
    mine = await _subscriber(db, "Bernard", "100000", fund=fund_a)
    await _subscriber(db, "Claire", "100000", fund=fund_b, iban=IBAN_B)

    waterfall = await distribution_service.propose(
        db, currency=CURRENCY, amount=Decimal("10000"), as_of=AS_OF, fund_id=fund_a.id
    )

    assert [s.subscription_id for s in waterfall.shares] == [mine.id]
    assert waterfall.shares[0].income_amount == Decimal("10000")


async def test_the_unattached_pool_is_a_scope_of_its_own(db):
    """⚠️ NULL IS NOT A MISSING VALUE. A crowdfunding project stands alone, and a
    distribution with no fund must serve exactly those — never a fund's subscribers."""
    fund = await _fund(db, "Fonds A", iban=IBAN_A)
    await _subscriber(db, "Dans le fonds", "100000", fund=fund)
    alone = await _subscriber(db, "Hors fonds", "50000")

    waterfall = await distribution_service.propose(
        db, currency=CURRENCY, amount=Decimal("5000"), as_of=AS_OF
    )

    assert [s.subscription_id for s in waterfall.shares] == [alone.id]


async def test_the_vehicles_terms_govern_and_resolve_the_old_dead_end(db):
    """🔴 THE REFUSAL THAT NOBODY COULD RESOLVE. Two subscribers on different terms used to
    block the waterfall with no way out, because no object held the fund's own agreement.
    The vehicle answers now."""
    fund = await _fund(
        db,
        "Fonds A",
        iban=IBAN_A,
        terms={
            "preferred_return": 0.08,
            "carried_interest": 0.20,
            "management_fee": 0.0,
        },
    )
    await _subscriber(db, "Bernard", "100000", fund=fund)

    waterfall = await distribution_service.propose(
        db, currency=CURRENCY, amount=Decimal("12000"), as_of=AS_OF, fund_id=fund.id
    )

    assert waterfall.blocked_reason is None
    assert waterfall.preferred_remaining == Decimal("0")
    # ⚠️ THE PREFERENCE IS PRORATED BY ACTUAL DAYS, not by « a year ». The money arrived on
    # 5 January and this is 30 June: 176 days, so 3 857.53 of preference and a carry on the
    # 8 142.47 above it. Writing this test against a round year would have asserted a figure
    # the fund never owes, and it is the kind of expectation that gets the CODE changed.
    assert waterfall.carried_interest == Decimal("1628.49")


async def test_the_net_asset_value_counts_only_this_vehicles_projects(db):
    fund_a = await _fund(db, "Fonds A", iban=IBAN_A)
    fund_b = await _fund(db, "Fonds B", iban=IBAN_B)
    await _valued_project(db, "Rue de la Paix", "130000", fund=fund_a)
    await _valued_project(db, "Quai de Valmy", "999999", fund=fund_b)

    nav = await valuation_service.net_asset_value(
        db, currency=CURRENCY, as_of=AS_OF, fund_id=fund_a.id
    )

    assert nav.projects == Decimal("130000")


async def test_a_fund_with_no_account_of_its_own_is_refused_not_guessed(db):
    """🔴 THE CASH CANNOT BE SPLIT BY ANY RULE. A statement line says nothing about which
    vehicle the euro was for; dividing shared cash would produce a total that reconciles and
    is wrong. The refusal is what gets the second account opened."""
    fund_a = await _fund(db, "Fonds A")  # no IBAN
    await _fund(db, "Fonds B", iban=IBAN_B)
    await _valued_project(db, "Rue de la Paix", "130000", fund=fund_a)

    nav = await valuation_service.net_asset_value(
        db, currency=CURRENCY, as_of=AS_OF, fund_id=fund_a.id
    )

    assert nav.is_known is False
    assert nav.total is None
    assert "pas de compte propre" in nav.unavailable_reason


async def test_a_lone_fund_with_no_account_still_works(db):
    """⚠️ THE REFUSAL IS ABOUT AMBIGUITY, NOT ABOUT TIDINESS. One vehicle on one account has
    no ambiguity at all, and refusing there would block the ordinary case to enforce a rule
    that protects nothing."""
    fund = await _fund(db, "Fonds unique")
    await _subscriber(db, "Bernard", "100000", fund=fund)
    await _valued_project(db, "Rue de la Paix", "130000", fund=fund)

    nav = await valuation_service.net_asset_value(
        db, currency=CURRENCY, as_of=AS_OF, fund_id=fund.id
    )

    assert nav.is_known is True
    assert nav.projects == Decimal("130000")


async def test_cash_is_filtered_by_the_vehicles_own_account(db):
    fund_a = await _fund(db, "Fonds A", iban=IBAN_A)
    fund_b = await _fund(db, "Fonds B", iban=IBAN_B)
    await _subscriber(db, "Bernard", "100000", fund=fund_a, iban=IBAN_A)
    await _subscriber(db, "Claire", "70000", fund=fund_b, iban=IBAN_B)

    nav_a = await valuation_service.net_asset_value(
        db, currency=CURRENCY, as_of=AS_OF, fund_id=fund_a.id
    )
    nav_b = await valuation_service.net_asset_value(
        db, currency=CURRENCY, as_of=AS_OF, fund_id=fund_b.id
    )

    assert nav_a.cash == Decimal("100000")
    assert nav_b.cash == Decimal("70000")


async def test_a_performance_measures_one_vehicle_and_not_the_pair(db):
    """🔴 THE LAST PLACE THAT STILL ANSWERED « EVERY FUND AT ONCE ».

    `performance_service` selected every subscription in a currency. An investor holding a
    unit of fund A and a unit of fund B got ONE rate covering both - a return on a holding
    that exists nowhere, on two vehicles with different terms, projects and lives. It looks
    entirely reasonable, and nobody can tell from the number that it is wrong.
    """
    from app.services import performance_service

    first = await _fund(db, "Premier", iban=IBAN_A)
    second = await _fund(db, "Second", iban=IBAN_B)
    await _subscriber(db, "Alix", "10000", fund=first, iban=IBAN_A)
    await _subscriber(db, "Bruno", "40000", fund=second, iban=IBAN_B)

    only_first = await performance_service.flows_by_currency(db, fund_id=first.id)
    only_second = await performance_service.flows_by_currency(db, fund_id=second.id)

    assert [f.amount for f in only_first[CURRENCY]] == [Decimal("-10000")]
    assert [f.amount for f in only_second[CURRENCY]] == [Decimal("-40000")]


async def test_the_absent_vehicle_means_the_unattached_pool_here_too(db):
    """⚠️ ONE CONVENTION, OR THE RATIO IS BUILT FROM TWO DIFFERENT POPULATIONS.

    `None` means « the subscriptions attached to no fund » in the waterfall and in the net
    asset value. If it had meant « all of them » here, a TVPI would divide flows covering
    every vehicle by a residual value covering one - and the quotient is a plausible figure
    that reconciles with nothing.
    """
    from app.services import performance_service

    attached = await _fund(db, "Rattache", iban=IBAN_A)
    await _subscriber(db, "Alix", "10000", fund=attached, iban=IBAN_A)
    await _subscriber(db, "Camille", "7000", fund=None, iban=IBAN_B)

    unattached = await performance_service.flows_by_currency(db, fund_id=None)

    assert [f.amount for f in unattached[CURRENCY]] == [Decimal("-7000")]


async def test_the_net_asset_value_is_reachable_and_not_only_computable(db):
    """🔴 IT HAD NO ROUTE AT ALL. The figure a fund is judged on was computed inside its own
    module and exposed nowhere: the only way to see any of it was sideways, through the
    residual value buried in a performance. This holds the endpoint's shape, so it cannot
    quietly go back to being unreachable."""
    from app.api.v1.funds import fund_net_asset_value

    fund = await _fund(db, "Le seul", iban=IBAN_A)
    await _valued_project(db, "Halle", "250000", fund=fund)

    out = await fund_net_asset_value(
        as_of=AS_OF, currency=CURRENCY, fund_id=fund.id, _=None, db=db
    )

    assert len(out) == 1
    assert out[0].projects == Decimal("250000")
    assert out[0].total == Decimal("250000")
    assert out[0].unavailable_reason is None


async def test_a_call_is_paid_into_its_own_vehicles_account(db):
    """🔴 THE QR POINTED AT THE PLATFORM'S FIRST IBAN, WHICH IS ONE ACCOUNT FOR EVERYBODY.

    An investor scanning fund B's call would send fund B's money to fund A's bank. Nothing
    reports an error: the transfer succeeds, it reconciles against fund A's statement, and
    the only trace is a call that stays unpaid beside a payment nobody expected.
    """
    from app.api.v1.treasury import _iban_for
    from app.models.treasury import CapitalCall

    fund = await _fund(db, "Second", iban=IBAN_B)
    subscription = await _subscriber(db, "Bruno", "40000", fund=fund, iban=IBAN_B)
    call = CapitalCall(
        id=uuid.uuid4(),
        subscription_id=subscription.id,
        reference="LCI-TEST-0001",
        amount=Decimal("1000"),
        currency=CURRENCY,
        called_on=date(2026, 2, 1),
        due_on=date(2026, 3, 1),
    )
    db.add(call)
    await db.flush()

    assert await _iban_for(db, call) == IBAN_B
