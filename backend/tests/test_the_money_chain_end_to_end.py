"""From an unvetted investor to an attributed transfer, against a real database.

WHAT THIS PROVES that the pure-rule tests cannot: that the verdict actually blocks at the
one place money enters, that a reference printed on a call is found again in a bank label
weeks later, and that a transfer cannot be attributed for more than it carried.

Each of those is a rule the unit tests already check in isolation. What is checked here is
that the rule is WIRED — the sister product's history is a long list of rules that were
correct and consulted by nobody.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core import instruments, kyc
from app.models.investor import Investor
from app.models.subscription import Subscription
from app.models.treasury import IN, BankMovement
from app.services import treasury_service


async def _investor(db, **kw) -> Investor:
    investor = Investor(
        kind=kw.pop("kind", "personne"),
        last_name=kw.pop("last_name", "Alphanor"),
        first_name=kw.pop("first_name", "Raymonde"),
        **kw,
    )
    db.add(investor)
    await db.flush()
    return investor


async def _subscription(db, investor, **kw) -> Subscription:
    subscription = Subscription(
        investor_id=investor.id,
        instrument=kw.pop("instrument", instruments.EQUITY),
        amount=kw.pop("amount", Decimal("200000")),
        currency=kw.pop("currency", "EUR"),
        signed_on=kw.pop("signed_on", date(2026, 1, 15)),
        **kw,
    )
    db.add(subscription)
    await db.flush()
    return subscription


async def _movement(db, **kw) -> BankMovement:
    movement = BankMovement(
        account_iban=kw.pop("account_iban", "FR7630006000011234567890189"),
        direction=IN,
        amount=kw.pop("amount", Decimal("50000")),
        currency=kw.pop("currency", "EUR"),
        value_date=kw.pop("value_date", date(2026, 3, 1)),
        **kw,
    )
    db.add(movement)
    await db.flush()
    return movement


class TestTheVerdictActuallyBlocks:
    async def test_money_is_refused_while_the_file_is_unvetted(self, db):
        """The check lives where money enters, not on the screen that offers the button.

        A screen-level check is missing from every other way in — an import, a correction,
        a script — and the whole point of a verdict is that it stops something.
        """
        investor = await _investor(db)
        assert investor.kyc_status == kyc.PENDING
        subscription = await _subscription(db, investor)
        movement = await _movement(db)

        with pytest.raises(ValueError, match="a verifier|à vérifier|accepté"):
            await treasury_service.attribute(
                db,
                movement=movement,
                subscription=subscription,
                amount=Decimal("50000"),
                capital_call=None,
                today=date.today(),
                attributed_by="tests",
            )

    async def test_and_lets_it_in_once_accepted(self, db):
        investor = await _investor(db, kyc_status=kyc.ACCEPTED)
        subscription = await _subscription(db, investor)
        movement = await _movement(db)

        contribution = await treasury_service.attribute(
            db,
            movement=movement,
            subscription=subscription,
            amount=Decimal("50000"),
            capital_call=None,
            today=date.today(),
            attributed_by="tests",
        )
        assert contribution.amount == Decimal("50000")
        assert contribution.attributed_by == "tests"


class TestTheReferenceTravels:
    async def test_a_call_reference_is_found_again_in_a_bank_label(self, db):
        """The whole mechanism, end to end: printed on a notice, retyped by a human into a
        banking app, read back out of a statement line."""
        investor = await _investor(db, kyc_status=kyc.ACCEPTED)
        subscription = await _subscription(db, investor)
        call = await treasury_service.open_call(
            db,
            subscription=subscription,
            amount=Decimal("50000"),
            called_on=date(2026, 2, 1),
            due_on=date(2026, 3, 1),
        )
        movement = await _movement(db, label=f"VIR SEPA {call.reference} SOUSCRIPTION")

        proposal = await treasury_service.propose_for(db, movement)
        assert proposal.investor_id == str(investor.id)
        assert proposal.capital_call_id == str(call.id)

    async def test_a_virtual_iban_needs_no_label_at_all(self, db):
        investor = await _investor(
            db, kyc_status=kyc.ACCEPTED, virtual_iban="FR7612345000011111111111111"
        )
        await _subscription(db, investor)
        movement = await _movement(
            db, account_iban="FR7612345000011111111111111", label="AUCUN LIBELLE UTILE"
        )

        proposal = await treasury_service.propose_for(db, movement)
        assert proposal.investor_id == str(investor.id)

    async def test_an_unreadable_line_is_left_in_the_pile_rather_than_guessed(self, db):
        investor = await _investor(db, kyc_status=kyc.ACCEPTED)
        await _subscription(db, investor)
        movement = await _movement(db, label="VIREMENT")

        proposal = await treasury_service.propose_for(db, movement)
        assert proposal.investor_id is None
        assert proposal.explanation


class TestATransferIsNeverSplitIntoMoreThanItCarried:
    async def test_over_attribution_is_refused(self, db):
        """Money the fund never received would reconcile to nothing at the bank while
        looking perfectly balanced here."""
        investor = await _investor(db, kyc_status=kyc.ACCEPTED)
        subscription = await _subscription(db, investor)
        movement = await _movement(db, amount=Decimal("50000"))

        await treasury_service.attribute(
            db,
            movement=movement,
            subscription=subscription,
            amount=Decimal("30000"),
            capital_call=None,
            today=date.today(),
            attributed_by="tests",
        )
        with pytest.raises(ValueError, match="ne porte plus que"):
            await treasury_service.attribute(
                db,
                movement=movement,
                subscription=subscription,
                amount=Decimal("25000"),
                capital_call=None,
                today=date.today(),
                attributed_by="tests",
            )

    async def test_the_remainder_can_still_be_attributed(self, db):
        """Partial is the norm on large amounts: one transfer, several subscriptions."""
        investor = await _investor(db, kyc_status=kyc.ACCEPTED)
        first = await _subscription(db, investor)
        second = await _subscription(db, investor, instrument=instruments.LOAN)
        movement = await _movement(db, amount=Decimal("50000"))

        await treasury_service.attribute(
            db,
            movement=movement,
            subscription=first,
            amount=Decimal("30000"),
            capital_call=None,
            today=date.today(),
            attributed_by="tests",
        )
        rest = await treasury_service.attribute(
            db,
            movement=movement,
            subscription=second,
            amount=Decimal("20000"),
            capital_call=None,
            today=date.today(),
            attributed_by="tests",
        )
        assert rest.amount == Decimal("20000")


class TestCurrenciesNeverMeet:
    async def test_a_transfer_cannot_settle_a_subscription_in_another_currency(
        self, db
    ):
        """A conversion is a dated event at a stated rate, not an attribution."""
        investor = await _investor(db, kyc_status=kyc.ACCEPTED)
        subscription = await _subscription(db, investor, currency="XOF")
        movement = await _movement(db, currency="EUR")

        with pytest.raises(ValueError, match="conversion"):
            await treasury_service.attribute(
                db,
                movement=movement,
                subscription=subscription,
                amount=Decimal("50000"),
                capital_call=None,
                today=date.today(),
                attributed_by="tests",
            )

    async def test_the_balance_is_one_figure_per_currency(self, db):
        await _movement(db, amount=Decimal("50000"), currency="EUR")
        await _movement(db, amount=Decimal("3000000"), currency="XOF")

        balance = await treasury_service.treasury_by_currency(db)
        assert balance["EUR"] == Decimal("50000")
        assert balance["XOF"] == Decimal("3000000")


class TestThePileOfUnnamedMoney:
    async def test_a_line_leaves_the_pile_once_attributed(self, db):
        investor = await _investor(db, kyc_status=kyc.ACCEPTED)
        subscription = await _subscription(db, investor)
        movement = await _movement(db)

        assert movement.id in {m.id for m in await treasury_service.unattributed(db)}
        await treasury_service.attribute(
            db,
            movement=movement,
            subscription=subscription,
            amount=Decimal("50000"),
            capital_call=None,
            today=date.today(),
            attributed_by="tests",
        )
        assert movement.id not in {
            m.id for m in await treasury_service.unattributed(db)
        }


class TestAThirdPartyPayerIsRecorded:
    async def test_money_from_somebody_else_is_flagged_not_blocked(self, db):
        """Often legitimate — a spouse, a company paying for its director — and exactly what
        identification rules exist to surface."""
        investor = await _investor(db, kyc_status=kyc.ACCEPTED)
        subscription = await _subscription(db, investor)
        movement = await _movement(db, counterparty_name="SCI DU PORT")

        contribution = await treasury_service.attribute(
            db,
            movement=movement,
            subscription=subscription,
            amount=Decimal("50000"),
            capital_call=None,
            today=date.today(),
            attributed_by="tests",
            third_party_reason="Paiement par la SCI du souscripteur",
        )
        assert contribution.third_party_payer is True
        assert contribution.third_party_reason

    async def test_the_investor_paying_from_their_own_account_is_not_flagged(self, db):
        investor = await _investor(db, kyc_status=kyc.ACCEPTED)
        subscription = await _subscription(db, investor)
        movement = await _movement(db, counterparty_name="ALPHANOR RAYMONDE")

        contribution = await treasury_service.attribute(
            db,
            movement=movement,
            subscription=subscription,
            amount=Decimal("50000"),
            capital_call=None,
            today=date.today(),
            attributed_by="tests",
        )
        assert contribution.third_party_payer is False


class TestACallIsNotMoney:
    async def test_opening_a_call_creates_no_contribution(self, db):
        """The second of the four amounts. A screen adding up calls and calling the total
        available cash is how a fund calls capital it has already spent."""
        investor = await _investor(db, kyc_status=kyc.ACCEPTED)
        subscription = await _subscription(db, investor)

        await treasury_service.open_call(
            db,
            subscription=subscription,
            amount=Decimal("50000"),
            called_on=date.today(),
            due_on=date.today() + timedelta(days=30),
        )
        assert await treasury_service.treasury_by_currency(db) == {}
