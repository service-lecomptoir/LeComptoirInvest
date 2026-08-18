"""Net asset value: the composition, the debt, and the project nobody valued.

🔴 THIS IS THE PIECE THE PERFORMANCE MODULE WAS WAITING FOR, and the reason it is worth
guarding this hard: TVPI, RVPI and the full rate of return all rest on it. An error here
does not show up as a wrong net asset value on one screen — it shows up as a wrong
performance figure on every report the fund sends out.

Two mistakes are guarded above all, and both flatter somebody:

  * forgetting to deduct the debt tells an equity holder they own a share of money that is
    already spoken for, and the error grows with exactly the leverage that made the fund
    worth reporting;
  * treating an unvalued project as worth nothing UNDER-states the fund, which is the error
    nobody ever disputes.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.core import instruments, kyc
from app.core.landlord_kind_values import PERSON
from app.models.investor import Investor
from app.models.project import ACTIVE, CLOSED, Project, ProjectValuation
from app.models.subscription import Subscription
from app.models.treasury import IN, OUT, BankMovement, Contribution
from app.services import valuation_service

CURRENCY = "EUR"
AS_OF = date(2026, 6, 30)


async def _project(db, name: str, *, status: str = ACTIVE) -> Project:
    project = Project(id=uuid.uuid4(), name=name, status=status, currency=CURRENCY)
    db.add(project)
    await db.flush()
    return project


async def _value(
    db, project: Project, amount: str, on: date = date(2026, 6, 30)
) -> None:
    db.add(
        ProjectValuation(
            id=uuid.uuid4(),
            project_id=project.id,
            valued_on=on,
            amount=Decimal(amount),
            currency=CURRENCY,
            valued_by="gestion@fonds.test",
        )
    )
    await db.flush()


async def _cash(
    db, amount: str, *, direction: str = IN, on: date = date(2026, 1, 5)
) -> BankMovement:
    movement = BankMovement(
        id=uuid.uuid4(),
        account_iban="FR7630006000011234567890189",
        direction=direction,
        amount=Decimal(amount),
        currency=CURRENCY,
        value_date=on,
    )
    db.add(movement)
    await db.flush()
    return movement


async def _subscriber(
    db,
    name: str,
    amount: str,
    *,
    instrument: str = instruments.EQUITY,
    terms: dict | None = None,
    ends_on: date | None = None,
) -> Subscription:
    investor = Investor(
        id=uuid.uuid4(), kind=PERSON, last_name=name, kyc_status=kyc.ACCEPTED
    )
    db.add(investor)
    await db.flush()
    subscription = Subscription(
        id=uuid.uuid4(),
        investor_id=investor.id,
        instrument=instrument,
        amount=Decimal(amount),
        currency=CURRENCY,
        signed_on=date(2026, 1, 1),
        ends_on=ends_on,
        terms=terms,
    )
    db.add(subscription)
    await db.flush()
    movement = await _cash(db, amount)
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


async def test_the_value_is_projects_plus_cash_minus_debt(db):
    """The composition, checkable by hand."""
    await _subscriber(db, "Bernard", "100000")
    project = await _project(db, "Rue de la Paix")
    await _value(db, project, "130000")
    await _cash(db, "100000", direction=OUT, on=date(2026, 2, 1))  # deployed

    nav = await valuation_service.net_asset_value(db, currency=CURRENCY, as_of=AS_OF)

    assert nav.is_known
    assert nav.projects == Decimal("130000")
    assert nav.cash == Decimal("0")
    assert nav.debt == Decimal("0")
    assert nav.total == Decimal("130000")


async def test_an_unvalued_open_project_makes_the_whole_total_unknown(db):
    """🔴 NOT « SHORT BY ONE PROJECT ». A fund holding two projects of which one was never
    valued has an UNKNOWN net asset value. Filling the gap with a nil under-states it, and
    an under-stated value is the error nobody disputes."""
    valued = await _project(db, "Rue de la Paix")
    await _value(db, valued, "130000")
    await _project(db, "Quai de Valmy")  # never valued

    nav = await valuation_service.net_asset_value(db, currency=CURRENCY, as_of=AS_OF)

    assert nav.is_known is False
    assert nav.total is None
    assert nav.unvalued == ["Quai de Valmy"]
    assert "ne vaut pas zéro" in nav.unavailable_reason


async def test_a_closed_project_needs_no_valuation(db):
    """What came back is already in the treasury; what was lost is already a loss."""
    open_one = await _project(db, "Rue de la Paix")
    await _value(db, open_one, "130000")
    await _project(db, "Ancien projet", status=CLOSED)

    nav = await valuation_service.net_asset_value(db, currency=CURRENCY, as_of=AS_OF)

    assert nav.is_known
    assert nav.unvalued == []


async def test_a_later_valuation_is_not_used_for_an_earlier_date(db):
    """⚠️ A JUNE OPINION MUST NOT APPEAR IN A MARCH REPORT. An as-of date that reached
    forward would let a fund publish a quarter using knowledge it did not have."""
    project = await _project(db, "Rue de la Paix")
    await _value(db, project, "100000", on=date(2026, 3, 31))
    await _value(db, project, "130000", on=date(2026, 6, 30))

    march = await valuation_service.net_asset_value(
        db, currency=CURRENCY, as_of=date(2026, 3, 31)
    )
    june = await valuation_service.net_asset_value(db, currency=CURRENCY, as_of=AS_OF)

    assert march.projects == Decimal("100000")
    assert june.projects == Decimal("130000")


async def test_the_debt_to_lenders_is_deducted(db):
    """🔴 THE MISTAKE THAT FLATTERS EVERY LEVERAGED FUND. A lender's capital and accrued
    interest leave before any subscriber sees a euro."""
    await _subscriber(
        db,
        "Prêteur",
        "50000",
        instrument=instruments.LOAN,
        terms={"rate": 0.08, "term_months": 60, "bullet": True},
        ends_on=date(2031, 1, 1),
    )
    project = await _project(db, "Rue de la Paix")
    await _value(db, project, "60000")
    await _cash(db, "50000", direction=OUT, on=date(2026, 2, 1))

    nav = await valuation_service.net_asset_value(db, currency=CURRENCY, as_of=AS_OF)

    # Interest run up on 50 000 at 8 % since the drawdown: the debt is real and deducted.
    assert nav.debt > 0
    assert nav.total == nav.projects + nav.cash - nav.debt
    assert nav.total < nav.projects


async def test_an_investors_residual_is_pro_rata_to_capital_at_work(db):
    """The same basis the waterfall distributes on. Any other key would make the reported
    share disagree with what they would actually be paid, on the same screen."""
    big = await _subscriber(db, "Bernard", "75000")
    await _subscriber(db, "Claire", "25000")
    project = await _project(db, "Rue de la Paix")
    await _value(db, project, "120000")
    await _cash(db, "100000", direction=OUT, on=date(2026, 2, 1))

    whole = await valuation_service.residual_value_of(
        db, currency=CURRENCY, as_of=AS_OF
    )
    theirs = await valuation_service.residual_value_of(
        db, currency=CURRENCY, as_of=AS_OF, investor_id=big.investor_id
    )

    assert whole == Decimal("120000")
    assert theirs == Decimal("90000")  # 75 % of 120 000


async def test_an_unknown_value_yields_none_never_zero(db):
    """The caller must carry « unknown » through to the screen: a zero residual would make
    TVPI equal DPI, which is a statement and a false one."""
    await _subscriber(db, "Bernard", "100000")
    await _project(db, "Quai de Valmy")  # never valued

    assert (
        await valuation_service.residual_value_of(db, currency=CURRENCY, as_of=AS_OF)
        is None
    )


async def test_the_performance_module_now_uses_it(db):
    """🔴 THE POINT OF THE WHOLE PIECE. A module that CAN answer and is never called is the
    same object as a rule nobody applies — which is the defect this product carried four
    times over. TVPI must stop saying « unknown » the moment a valuation exists."""
    from app.services import performance_service

    await _subscriber(db, "Bernard", "100000")
    project = await _project(db, "Rue de la Paix")
    await _value(db, project, "130000")
    await _cash(db, "100000", direction=OUT, on=date(2026, 2, 1))

    [block] = await performance_service.performance(db, as_of=AS_OF)

    assert block.residual_value == Decimal("130000")
    assert block.tvpi == Decimal("1.3")
    assert block.irr_is_realised_only is False
