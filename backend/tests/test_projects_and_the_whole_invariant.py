"""Money out to projects, money back from them — and the treasury identity, closed.

WITH PROJECTS IN PLACE THE FOUR MOVEMENTS EXIST, and the invariant can finally be checked
end to end:

    treasury(X) = Σ contributions(X) − Σ deployments(X) + Σ returns(X) − Σ distributions(X)

Everything else this product does is presentation. If that equation holds and reconciles to
the bank, the tool tells the truth.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.core import instruments, kyc
from app.models.investor import Investor
from app.models.project import ACTIVE, Project
from app.models.subscription import Subscription
from app.models.treasury import IN, OUT, BankMovement
from app.services import project_service, treasury_service


async def _movement(db, *, direction=IN, amount=Decimal("50000"), currency="EUR", **kw):
    movement = BankMovement(
        account_iban="FR7630006000011234567890189",
        direction=direction,
        amount=amount,
        currency=currency,
        value_date=kw.pop("value_date", date(2026, 3, 1)),
        **kw,
    )
    db.add(movement)
    await db.flush()
    return movement


async def _project(db, **kw) -> Project:
    project = Project(
        name=kw.pop("name", "Résidence du Port"),
        currency=kw.pop("currency", "EUR"),
        status=kw.pop("status", ACTIVE),
        **kw,
    )
    db.add(project)
    await db.flush()
    return project


class TestMoneyOnlyLeavesOnAnOutgoingTransfer:
    async def test_a_deployment_cannot_be_imputed_on_money_that_came_in(self, db):
        """Counting the same euro twice in opposite directions balances the treasury, and
        the total looks right."""
        project = await _project(db)
        incoming = await _movement(db, direction=IN)
        with pytest.raises(ValueError, match="SORTANT|sortant"):
            await project_service.deploy(
                db,
                project=project,
                movement=incoming,
                amount=Decimal("50000"),
                decided_by="tests",
            )

    async def test_a_return_cannot_be_imputed_on_money_that_went_out(self, db):
        project = await _project(db)
        outgoing = await _movement(db, direction=OUT)
        with pytest.raises(ValueError, match="ENTRANT|entrant"):
            await project_service.record_return(
                db,
                project=project,
                movement=outgoing,
                capital_amount=Decimal("50000"),
                income_amount=Decimal("0"),
            )


class TestGettingYourOwnMoneyBackIsNotAGain:
    async def test_a_project_that_returned_what_it_took_earned_nothing(self, db):
        project = await _project(db)
        out = await _movement(db, direction=OUT, amount=Decimal("100000"))
        await project_service.deploy(
            db,
            project=project,
            movement=out,
            amount=Decimal("100000"),
            decided_by="tests",
        )
        back = await _movement(db, direction=IN, amount=Decimal("100000"))
        await project_service.record_return(
            db,
            project=project,
            movement=back,
            capital_amount=Decimal("100000"),
            income_amount=Decimal("0"),
        )

        (result,) = await project_service.results(db)
        assert result.deployed == Decimal("100000")
        assert result.capital_returned == Decimal("100000")
        assert result.gain == Decimal("0")
        assert result.outstanding == Decimal("0")
        assert result.multiple() == Decimal("1")

    async def test_the_gain_is_the_income_and_only_the_income(self, db):
        project = await _project(db)
        out = await _movement(db, direction=OUT, amount=Decimal("100000"))
        await project_service.deploy(
            db,
            project=project,
            movement=out,
            amount=Decimal("100000"),
            decided_by="tests",
        )
        back = await _movement(db, direction=IN, amount=Decimal("118000"))
        await project_service.record_return(
            db,
            project=project,
            movement=back,
            capital_amount=Decimal("100000"),
            income_amount=Decimal("18000"),
        )

        (result,) = await project_service.results(db)
        assert result.gain == Decimal("18000")
        assert result.multiple() == Decimal("1.18")

    async def test_a_project_that_has_not_started_has_no_multiple(self, db):
        """None rather than zero: « 0.00x » reads as a project that lost everything."""
        await _project(db)
        (result,) = await project_service.results(db)
        assert result.multiple() is None

    async def test_a_project_that_has_not_returned_anything_yet_has_no_multiple_either(
        self, db
    ):
        """🔴 THE HALF OF THE CASE THAT WAS MISSING, seen on screen on 18 August.

        The first rule returned `None` only when nothing had been deployed. A project funded
        the day before, perfectly healthy, simply too young to have returned anything, was
        showing « 0.00x » — exactly the « it lost everything » reading the rule claimed to
        prevent, and worse, since it landed on a project in good health.

        A ratio of what has not arrived yet is not zero, it is UNKNOWN. A real loss, by
        contrast, is already stated by the status and by the capital still outstanding.
        """
        project = await _project(db)
        out = await _movement(db, direction=OUT, amount=Decimal("120000"))
        await project_service.deploy(
            db,
            project=project,
            movement=out,
            amount=Decimal("120000"),
            decided_by="tests",
        )
        (result,) = await project_service.results(db)
        assert result.deployed == Decimal("120000")
        assert result.multiple() is None
        # What is committed, by contrast, is stated straight away.
        assert result.outstanding == Decimal("120000")


class TestTheTreasuryIdentityHolds:
    async def test_the_four_movements_reconcile_per_currency(self, db):
        """The whole product in one test.

        An investor pays 200 000. The fund deploys 150 000 into a project. The project
        returns 160 000, of which 10 000 is income. What is left in the account is what the
        bank would say: 200 000 − 150 000 + 160 000 = 210 000.
        """
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
            instrument=instruments.EQUITY,
            amount=Decimal("200000"),
            currency="EUR",
            signed_on=date(2026, 1, 15),
        )
        db.add(subscription)
        await db.flush()

        paid_in = await _movement(
            db,
            direction=IN,
            amount=Decimal("200000"),
            counterparty_name="ALPHANOR RAYMONDE",
        )
        await treasury_service.attribute(
            db,
            movement=paid_in,
            subscription=subscription,
            amount=Decimal("200000"),
            capital_call=None,
            attributed_by="tests",
        )

        project = await _project(db)
        sent_out = await _movement(db, direction=OUT, amount=Decimal("150000"))
        await project_service.deploy(
            db,
            project=project,
            movement=sent_out,
            amount=Decimal("150000"),
            decided_by="tests",
        )
        came_back = await _movement(db, direction=IN, amount=Decimal("160000"))
        await project_service.record_return(
            db,
            project=project,
            movement=came_back,
            capital_amount=Decimal("150000"),
            income_amount=Decimal("10000"),
        )

        balance = await treasury_service.treasury_by_currency(db)
        assert balance == {"EUR": Decimal("210000")}

        (result,) = await project_service.results(db)
        assert result.outstanding == Decimal("0")
        assert result.gain == Decimal("10000")

    async def test_two_currencies_never_meet_in_the_balance(self, db):
        await _movement(db, direction=IN, amount=Decimal("50000"), currency="EUR")
        await _movement(db, direction=IN, amount=Decimal("3000000"), currency="XOF")
        await _movement(db, direction=OUT, amount=Decimal("1000000"), currency="XOF")

        assert await treasury_service.treasury_by_currency(db) == {
            "EUR": Decimal("50000"),
            "XOF": Decimal("2000000"),
        }


class TestATransferIsNeverSplitIntoMoreThanItCarried:
    async def test_on_the_project_side_too(self, db):
        project = await _project(db)
        out = await _movement(db, direction=OUT, amount=Decimal("100000"))
        await project_service.deploy(
            db,
            project=project,
            movement=out,
            amount=Decimal("70000"),
            decided_by="tests",
        )
        with pytest.raises(ValueError, match="ne porte plus que"):
            await project_service.deploy(
                db,
                project=project,
                movement=out,
                amount=Decimal("40000"),
                decided_by="tests",
            )
