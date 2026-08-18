"""The waterfall: lenders first, subscribers only once the debt is covered.

🔴 THE SECOND RULE IS THE ONE WITH TEETH. « Lenders are served first » only decides who gets
the money that IS distributed; a fund can honour that ordering perfectly and still default
the same afternoon by distributing cash it owed on an instalment. What actually protects the
lender is the refusal to give subscribers anything while the debt stands, and that is what
most of this file checks.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.core import instruments, kyc
from app.models.investor import Investor
from app.models.subscription import Subscription
from app.models.treasury import IN, OUT, BankMovement, Contribution
from app.services import distribution_service

AS_OF = date(2027, 1, 1)


async def _investor(db, name: str) -> Investor:
    investor = Investor(
        kind="personne", last_name=name, first_name="A", kyc_status=kyc.ACCEPTED
    )
    db.add(investor)
    await db.flush()
    return investor


async def _funded(
    db,
    investor: Investor,
    *,
    instrument: str,
    amount: str,
    currency: str = "EUR",
    signed_on: date = date(2026, 1, 1),
    ends_on: date | None = None,
    terms: dict | None = None,
    drawn: str | None = None,
) -> Subscription:
    """A subscription with money actually paid in against a real bank movement."""
    subscription = Subscription(
        investor_id=investor.id,
        instrument=instrument,
        amount=Decimal(amount),
        currency=currency,
        signed_on=signed_on,
        ends_on=ends_on,
        terms=terms,
    )
    db.add(subscription)
    await db.flush()

    movement = BankMovement(
        account_iban="FR7630006000011234567890189",
        direction=IN,
        amount=Decimal(drawn or amount),
        currency=currency,
        value_date=signed_on,
    )
    db.add(movement)
    await db.flush()
    db.add(
        Contribution(
            bank_movement_id=movement.id,
            subscription_id=subscription.id,
            amount=Decimal(drawn or amount),
            currency=currency,
        )
    )
    await db.flush()
    return subscription


_BULLET = {"rate": 0.08, "term_months": 24, "period_months": 12, "bullet": True}


class TestSubscribersAreNotPaidOutOfWhatALenderIsOwed:
    async def test_a_subscriber_gets_nothing_while_the_lender_is_short(self, db):
        """The whole point. 20 000 of interest is owed and only 5 000 is available: every
        cent goes to the lender, and the subscriber's share is not « smaller », it is none."""
        lender = await _investor(db, "Prêteur")
        member = await _investor(db, "Souscripteur")
        await _funded(
            db,
            lender,
            instrument=instruments.LOAN,
            amount="250000",
            ends_on=date(2028, 1, 1),
            terms=_BULLET,
        )
        await _funded(db, member, instrument=instruments.EQUITY, amount="400000")

        result = await distribution_service.propose(
            db, currency="EUR", amount=Decimal("5000"), as_of=AS_OF
        )
        assert [s.instrument for s in result.shares] == [instruments.LOAN]
        assert result.shares[0].income_amount == Decimal("5000.00")
        assert result.debt_remaining == Decimal("15000.00")
        assert "prêteurs" in result.blocked_reason.lower()

    async def test_once_the_debt_is_covered_the_subscriber_is_served(self, db):
        lender = await _investor(db, "Prêteur")
        member = await _investor(db, "Souscripteur")
        await _funded(
            db,
            lender,
            instrument=instruments.LOAN,
            amount="250000",
            ends_on=date(2028, 1, 1),
            terms=_BULLET,
        )
        await _funded(db, member, instrument=instruments.EQUITY, amount="400000")

        result = await distribution_service.propose(
            db, currency="EUR", amount=Decimal("50000"), as_of=AS_OF
        )
        by_instrument = {s.instrument: s for s in result.shares}
        assert by_instrument[instruments.LOAN].income_amount == Decimal("20000.00")
        assert by_instrument[instruments.EQUITY].income_amount == Decimal("30000.00")
        assert result.debt_remaining == Decimal("0")
        assert result.blocked_reason is None

    async def test_the_lender_comes_first_in_the_list_shown(self, db):
        """The order on screen is the order of service, not an arbitrary sort."""
        member = await _investor(
            db, "Aaaa"
        )  # first alphabetically, still second served
        lender = await _investor(db, "Zzzz")
        await _funded(db, member, instrument=instruments.EQUITY, amount="400000")
        await _funded(
            db,
            lender,
            instrument=instruments.LOAN,
            amount="250000",
            ends_on=date(2028, 1, 1),
            terms=_BULLET,
        )
        result = await distribution_service.propose(
            db, currency="EUR", amount=Decimal("50000"), as_of=AS_OF
        )
        assert result.shares[0].instrument == instruments.LOAN


class TestTwoLendersShareShortfallInProportion:
    async def test_pari_passu_rather_than_first_come(self, db):
        """No clause here prefers one lender to another, so a shortfall hits them equally."""
        big = await _investor(db, "Grand")
        small = await _investor(db, "Petit")
        await _funded(
            db,
            big,
            instrument=instruments.LOAN,
            amount="300000",
            signed_on=date(2026, 1, 1),
            ends_on=date(2028, 1, 1),
            terms=_BULLET,
        )
        await _funded(
            db,
            small,
            instrument=instruments.LOAN,
            amount="100000",
            signed_on=date(2026, 1, 1),
            ends_on=date(2028, 1, 1),
            terms=_BULLET,
        )
        # 24 000 + 8 000 = 32 000 owed; only 16 000 available.
        result = await distribution_service.propose(
            db, currency="EUR", amount=Decimal("16000"), as_of=AS_OF
        )
        got = {s.investor_name: s.income_amount for s in result.shares}
        assert got["A Grand"] == Decimal("12000.00")
        assert got["A Petit"] == Decimal("4000.00")
        assert sum(s.gross_amount for s in result.shares) == Decimal("16000.00")


class TestInterestIsServedBeforeCapital:
    async def test_at_maturity_the_coupon_comes_before_the_principal(self, db):
        """A lender served capital while their coupon goes unpaid is still owed."""
        lender = await _investor(db, "Prêteur")
        await _funded(
            db,
            lender,
            instrument=instruments.LOAN,
            amount="250000",
            ends_on=date(2028, 1, 1),
            terms=_BULLET,
        )
        result = await distribution_service.propose(
            db, currency="EUR", amount=Decimal("30000"), as_of=date(2028, 1, 1)
        )
        share = result.shares[0]
        assert share.income_amount == Decimal("40000.00") - Decimal("10000.00")
        assert share.capital_amount == Decimal("0")


class TestAnUnmeasurableDebtBlocksEverything:
    async def test_one_amortising_loan_refuses_the_whole_proposal(self, db):
        """« Are the lenders covered » has no answer, so subscribers cannot be shown as
        safely payable on the strength of a debt nobody measured."""
        lender = await _investor(db, "Prêteur")
        member = await _investor(db, "Souscripteur")
        await _funded(
            db,
            lender,
            instrument=instruments.LOAN,
            amount="250000",
            ends_on=date(2028, 1, 1),
            terms={**_BULLET, "bullet": False},
        )
        await _funded(db, member, instrument=instruments.EQUITY, amount="400000")

        result = await distribution_service.propose(
            db, currency="EUR", amount=Decimal("500000"), as_of=AS_OF
        )
        assert result.shares == []
        assert len(result.unknown) == 1
        assert result.blocked_reason is not None


class TestCurrenciesNeverMeet:
    async def test_a_lender_in_another_currency_does_not_block_this_one(self, db):
        """The invariant holds per currency, and so does the debt."""
        euro_member = await _investor(db, "Euro")
        cfa_lender = await _investor(db, "Franc")
        await _funded(db, euro_member, instrument=instruments.EQUITY, amount="400000")
        await _funded(
            db,
            cfa_lender,
            instrument=instruments.LOAN,
            amount="3000000",
            currency="XOF",
            ends_on=date(2028, 1, 1),
            terms=_BULLET,
        )
        result = await distribution_service.propose(
            db, currency="EUR", amount=Decimal("10000"), as_of=AS_OF
        )
        assert result.blocked_reason is None
        assert [s.instrument for s in result.shares] == [instruments.EQUITY]


class TestCapitalAndIncomeAreNeverConflated:
    async def test_a_profit_distribution_returns_no_capital(self, db):
        member = await _investor(db, "Souscripteur")
        await _funded(db, member, instrument=instruments.EQUITY, amount="400000")
        result = await distribution_service.propose(
            db,
            currency="EUR",
            amount=Decimal("10000"),
            as_of=AS_OF,
            repay_capital=False,
        )
        assert result.shares[0].capital_amount == Decimal("0")
        assert result.shares[0].income_amount == Decimal("10000.00")

    async def test_a_wind_down_returns_capital_first_then_the_gain(self, db):
        """Reporting a return of capital as performance is the oldest flattering mistake."""
        member = await _investor(db, "Souscripteur")
        await _funded(db, member, instrument=instruments.EQUITY, amount="400000")
        result = await distribution_service.propose(
            db,
            currency="EUR",
            amount=Decimal("450000"),
            as_of=AS_OF,
            repay_capital=True,
        )
        assert result.shares[0].capital_amount == Decimal("400000.00")
        assert result.shares[0].income_amount == Decimal("50000.00")


class TestDecidingIsNotPaying:
    async def test_a_recorded_distribution_is_not_paid_yet(self, db):
        member = await _investor(db, "Souscripteur")
        await _funded(db, member, instrument=instruments.EQUITY, amount="400000")
        result = await distribution_service.propose(
            db, currency="EUR", amount=Decimal("10000"), as_of=AS_OF
        )
        (created,) = await distribution_service.record(
            db, result, decided_on=date(2027, 1, 5)
        )
        assert created.paid_on is None
        assert created.bank_movement_id is None

    async def test_paying_it_needs_an_outgoing_transfer(self, db):
        member = await _investor(db, "Souscripteur")
        await _funded(db, member, instrument=instruments.EQUITY, amount="400000")
        result = await distribution_service.propose(
            db, currency="EUR", amount=Decimal("10000"), as_of=AS_OF
        )
        (created,) = await distribution_service.record(
            db, result, decided_on=date(2027, 1, 5)
        )
        incoming = BankMovement(
            account_iban="FR7630006000011234567890189",
            direction=IN,
            amount=Decimal("10000"),
            currency="EUR",
            value_date=date(2027, 1, 8),
        )
        db.add(incoming)
        await db.flush()
        with pytest.raises(ValueError, match="SORTANT|sortant"):
            await distribution_service.pay(db, distribution=created, movement=incoming)

    async def test_once_paid_it_cannot_be_paid_again(self, db):
        member = await _investor(db, "Souscripteur")
        await _funded(db, member, instrument=instruments.EQUITY, amount="400000")
        result = await distribution_service.propose(
            db, currency="EUR", amount=Decimal("10000"), as_of=AS_OF
        )
        (created,) = await distribution_service.record(
            db, result, decided_on=date(2027, 1, 5)
        )
        outgoing = BankMovement(
            account_iban="FR7630006000011234567890189",
            direction=OUT,
            amount=Decimal("10000"),
            currency="EUR",
            value_date=date(2027, 1, 8),
        )
        db.add(outgoing)
        await db.flush()
        await distribution_service.pay(db, distribution=created, movement=outgoing)
        assert created.paid_on == date(2027, 1, 8)
        with pytest.raises(ValueError, match="déjà payée"):
            await distribution_service.pay(db, distribution=created, movement=outgoing)


class TestADecidedDistributionIsNotProposedTwice:
    async def test_the_second_proposal_knows_the_first_was_already_allocated(self, db):
        """`portfolio_service` counts what was PAID; a proposal counts what was DECIDED.
        Using the paid figure here would re-offer the same coupon for as long as the first
        one sat unpaid, and the second proposal would look perfectly sound."""
        lender = await _investor(db, "Prêteur")
        await _funded(
            db,
            lender,
            instrument=instruments.LOAN,
            amount="250000",
            ends_on=date(2028, 1, 1),
            terms=_BULLET,
        )
        first = await distribution_service.propose(
            db, currency="EUR", amount=Decimal("20000"), as_of=AS_OF
        )
        await distribution_service.record(db, first, decided_on=date(2027, 1, 2))

        second = await distribution_service.propose(
            db, currency="EUR", amount=Decimal("20000"), as_of=AS_OF
        )
        assert second.shares == []
        assert second.debt_remaining == Decimal("0")
