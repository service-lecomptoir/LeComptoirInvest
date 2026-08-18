"""The bootstrap creates the first manager, and then never touches anything again.

🔴 THE DEFECT THIS GUARDS AGAINST IS NOT HYPOTHETICAL. The sister products shipped seeds
that asked « does this e-mail exist? »: an account deleted on purpose came back at every
deployment, and the password was rewritten on every boot. The user reported it as « je le
supprime et il revient a chaque fois ». The condition below is the only one that is true.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.security import verify_password
from app.models.user import INVESTOR, MANAGER, User
from app.startup.bootstrap import bootstrap_is_needed, ensure_first_manager


class TestTheRuleItself:
    def test_the_question_is_whether_anybody_can_administer(self):
        assert bootstrap_is_needed(somebody_can_administer=False) is True
        assert bootstrap_is_needed(somebody_can_administer=True) is False


class TestItCreatesTheFirstAccount:
    async def test_on_an_empty_fund_a_manager_appears(self, db):
        created = await ensure_first_manager(
            db, email="Gestion@Fonds.FR", password="s3cret!"
        )
        assert created is True
        user = (await db.execute(select(User).where(User.role == MANAGER))).scalar_one()
        assert user.email == "gestion@fonds.fr"  # normalised, not stored as typed
        assert user.must_change_password is True

    async def test_the_password_given_is_the_password_stored(self, db):
        await ensure_first_manager(db, email="gestion@fonds.fr", password="s3cret!")
        user = (await db.execute(select(User).where(User.role == MANAGER))).scalar_one()
        assert verify_password("s3cret!", user.hashed_password)


class TestItNeverMaintains:
    async def test_it_does_nothing_when_somebody_can_already_administer(self, db):
        db.add(
            User(
                email="patron@fonds.fr",
                hashed_password="already-hashed",
                role=MANAGER,
            )
        )
        await db.flush()
        assert (
            await ensure_first_manager(db, email="autre@fonds.fr", password="x")
            is False
        )
        assert (
            await db.execute(select(User).where(User.email == "autre@fonds.fr"))
        ).scalar_one_or_none() is None

    async def test_a_deleted_account_does_not_come_back_while_another_manager_exists(
        self, db
    ):
        """« Je le supprime et il revient » : the exact report, held still."""
        db.add(User(email="autre@fonds.fr", hashed_password="h", role=MANAGER))
        db.add(User(email="amorce@fonds.fr", hashed_password="h", role=MANAGER))
        await db.flush()
        deleted = (
            await db.execute(select(User).where(User.email == "amorce@fonds.fr"))
        ).scalar_one()
        await db.delete(deleted)
        await db.flush()

        assert (
            await ensure_first_manager(db, email="amorce@fonds.fr", password="x")
            is False
        )
        assert (
            await db.execute(select(User).where(User.email == "amorce@fonds.fr"))
        ).scalar_one_or_none() is None

    async def test_the_password_of_an_existing_account_is_never_rewritten(self, db):
        await ensure_first_manager(db, email="gestion@fonds.fr", password="first")
        user = (await db.execute(select(User).where(User.role == MANAGER))).scalar_one()
        chosen = user.hashed_password

        await ensure_first_manager(db, email="gestion@fonds.fr", password="second")
        again = (
            await db.execute(select(User).where(User.role == MANAGER))
        ).scalar_one()
        assert again.hashed_password == chosen

    async def test_an_investor_account_alone_does_not_count_as_administration(self, db):
        """An investor sees their own portfolio and nothing else. A fund holding only
        investor logins is a fund nobody can run, and the bootstrap is exactly for that."""
        db.add(User(email="souscripteur@fonds.fr", hashed_password="h", role=INVESTOR))
        await db.flush()
        assert (
            await ensure_first_manager(db, email="gestion@fonds.fr", password="x")
            is True
        )


@pytest.mark.parametrize("email", ["  GESTION@fonds.FR  ", "gestion@fonds.fr"])
async def test_the_e_mail_is_normalised_whatever_was_typed(db, email):
    await ensure_first_manager(db, email=email, password="x")
    user = (await db.execute(select(User).where(User.role == MANAGER))).scalar_one()
    assert user.email == "gestion@fonds.fr"


class TestTwoWorkersRacingDoNotProduceAnError:
    async def test_a_duplicate_e_mail_is_an_answer_not_a_failure(self, db):
        """🔴 SEEN IN PRODUCTION ON THE FIRST DEPLOYMENT. `uvicorn --workers 2` runs the
        lifespan twice; both processes read « nobody can administer » before either had
        committed, and both inserted. One won, the other raised a duplicate-key error and
        logged a stack trace under a fund that was in fact correctly set up.

        Here the row is inserted BEHIND the function's back — an investor account, so the
        « can anybody administer » read still says no — and the unique index is what stops
        the second write. It must come back as False, not as an exception.
        """
        db.add(
            User(
                email="gestion@fonds.fr",
                hashed_password="posee-par-un-autre-processus",
                role=INVESTOR,
            )
        )
        await db.flush()

        assert (
            await ensure_first_manager(db, email="gestion@fonds.fr", password="x")
            is False
        )

        rows = (
            (await db.execute(select(User).where(User.email == "gestion@fonds.fr")))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].hashed_password == "posee-par-un-autre-processus"
