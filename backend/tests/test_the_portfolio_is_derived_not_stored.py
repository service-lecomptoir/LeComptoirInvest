"""An investor's position, recomputed from what happened — and the conversion that keeps history.

🔴 NOTHING ABOUT A POSITION IS STORED. A position kept in a column is a second ledger, and
two ledgers disagree silently. These tests exist to keep it that way: each one moves a fact
and checks that the position follows, which is only possible if it is derived.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core import instruments, kyc
from app.models.investor import Investor
from app.models.subscription import Subscription, SubscriptionConversion
from app.models.treasury import IN, BankMovement, Distribution
from app.services import portfolio_service, treasury_service


async def _setup(
    db, *, amount=Decimal("200000"), currency="EUR", instrument=instruments.EQUITY
):
    investor = Investor(
        kind="personne",
        last_name="Alphanor",
        first_name="Raymonde",
        kyc_status=kyc.ACCEPTED,
    )
    db.add(investor)
    await db.flush()
    subscription = Subscription(
        investor_id=investor.id,
        instrument=instrument,
        amount=amount,
        currency=currency,
        signed_on=date(2026, 1, 15),
    )
    db.add(subscription)
    await db.flush()
    return investor, subscription


async def _pay(db, subscription, amount, currency="EUR"):
    movement = BankMovement(
        account_iban="FR7630006000011234567890189",
        direction=IN,
        amount=amount,
        currency=currency,
        value_date=date(2026, 3, 1),
        counterparty_name="ALPHANOR RAYMONDE",
    )
    db.add(movement)
    await db.flush()
    return await treasury_service.attribute(
        db,
        movement=movement,
        subscription=subscription,
        amount=amount,
        capital_call=None,
        attributed_by="tests",
    )


class TestThePositionFollowsTheFacts:
    async def test_an_engagement_alone_is_not_money(self, db):
        """The first of the four confusions, and the one that has funds calling capital
        they have already spent."""
        investor, _ = await _setup(db)
        (position,) = await portfolio_service.positions_of(db, investor.id)
        assert position.committed == Decimal("200000")
        assert position.contributed == Decimal("0")
        assert position.capital_at_work == Decimal("0")
        assert position.outstanding_commitment == Decimal("200000")

    async def test_a_call_asks_but_does_not_bring(self, db):
        investor, subscription = await _setup(db)
        await treasury_service.open_call(
            db,
            subscription=subscription,
            amount=Decimal("50000"),
            called_on=date(2026, 2, 1),
            due_on=date(2026, 3, 1),
        )
        (position,) = await portfolio_service.positions_of(db, investor.id)
        assert position.called == Decimal("50000")
        assert position.contributed == Decimal("0")

    async def test_a_contribution_puts_capital_to_work(self, db):
        investor, subscription = await _setup(db)
        await _pay(db, subscription, Decimal("50000"))
        (position,) = await portfolio_service.positions_of(db, investor.id)
        assert position.contributed == Decimal("50000")
        assert position.capital_at_work == Decimal("50000")
        assert position.outstanding_commitment == Decimal("150000")


class TestCapitalComingBackIsNotAReturn:
    async def test_repaid_capital_leaves_the_capital_at_work_and_is_not_income(
        self, db
    ):
        """The split is the point. A distribution stored as one figure makes this
        subtraction impossible, and no presentation afterwards recovers it."""
        investor, subscription = await _setup(db)
        await _pay(db, subscription, Decimal("50000"))
        db.add(
            Distribution(
                subscription_id=subscription.id,
                capital_amount=Decimal("20000"),
                income_amount=Decimal("4000"),
                withholding_amount=Decimal("1200"),
                currency="EUR",
                decided_on=date(2026, 6, 1),
                paid_on=date(2026, 6, 5),
            )
        )
        await db.flush()

        (position,) = await portfolio_service.positions_of(db, investor.id)
        assert position.capital_repaid == Decimal("20000")
        assert position.income_received == Decimal("4000")
        assert position.capital_at_work == Decimal("30000")
        # What actually reached their account: capital + income, less withholding.
        assert position.net_received == Decimal("22800")

    async def test_a_distribution_decided_but_not_paid_counts_for_nothing(self, db):
        """A real state, and counting it would tell an investor they have received money
        that is still in the fund's account."""
        investor, subscription = await _setup(db)
        await _pay(db, subscription, Decimal("50000"))
        db.add(
            Distribution(
                subscription_id=subscription.id,
                capital_amount=Decimal("20000"),
                income_amount=Decimal("4000"),
                currency="EUR",
                decided_on=date(2026, 6, 1),
                paid_on=None,
            )
        )
        await db.flush()

        (position,) = await portfolio_service.positions_of(db, investor.id)
        assert position.capital_repaid == Decimal("0")
        assert position.capital_at_work == Decimal("50000")


class TestTwoCurrenciesAreTwoPortfolios:
    async def test_totals_are_kept_apart(self, db):
        investor, first = await _setup(db)
        second = Subscription(
            investor_id=investor.id,
            instrument=instruments.LOAN,
            amount=Decimal("3000000"),
            currency="XOF",
            signed_on=date(2026, 2, 1),
        )
        db.add(second)
        await db.flush()
        await _pay(db, first, Decimal("50000"))
        await _pay(db, second, Decimal("1000000"), currency="XOF")

        totals = portfolio_service.summarise(
            await portfolio_service.positions_of(db, investor.id)
        )
        assert totals["EUR"]["contributed"] == Decimal("50000")
        assert totals["XOF"]["contributed"] == Decimal("1000000")
        assert set(totals) == {"EUR", "XOF"}


class TestAConversionKeepsTheHistory:
    async def test_the_loan_closes_and_a_subscription_opens(self, db):
        """Both rows survive. A converted loan that vanished would make every past
        statement unexplainable."""
        investor, loan = await _setup(
            db, instrument=instruments.LOAN, amount=Decimal("100000")
        )
        await _pay(db, loan, Decimal("100000"))

        equity = Subscription(
            investor_id=investor.id,
            instrument=instruments.EQUITY,
            amount=Decimal("108000"),
            currency="EUR",
            signed_on=date(2026, 9, 1),
        )
        db.add(equity)
        await db.flush()
        db.add(
            SubscriptionConversion(
                from_subscription_id=loan.id,
                to_subscription_id=equity.id,
                converted_on=date(2026, 9, 1),
                principal_converted=Decimal("100000"),
                interest_converted=Decimal("8000"),
                currency="EUR",
            )
        )
        loan.converted_on = date(2026, 9, 1)
        await db.flush()

        positions = {
            p.subscription_id: p
            for p in await portfolio_service.positions_of(db, investor.id)
        }
        assert loan.id in positions, (
            "Le prêt converti doit rester lisible dans l'historique."
        )
        assert equity.id in positions
        # The money paid stays attached to the loan it was paid into: what converted is the
        # instrument governing the future, not the cash already received.
        assert positions[loan.id].contributed == Decimal("100000")
        assert positions[equity.id].contributed == Decimal("0")
        assert loan.is_open is False
