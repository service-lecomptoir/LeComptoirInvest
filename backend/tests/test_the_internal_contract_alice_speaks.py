"""The `/internal` contract, held still.

🔴 WHAT IS GUARDED HERE IS NOT « IT ANSWERS 200 ». It is the three decisions that, taken
the wrong way round, are invisible:

  * the protection is on the OUTCOME (« would this fund still be administrable? »), never on
    the role — a guard on the role forbids renaming an admin, which locks nobody out, and
    allows deleting the last manager, which locks everybody out;
  * a partial update must NOT blank the fields absent from the payload;
  * the fields Alice sends and this product does not keep are NAMED, because a schema that
    does not name a field drops it silently — that is how the sister product shipped a NaN
    to production.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.v1.internal_admin import IGNORED_BY_DESIGN
from app.config import get_settings
from app.core.security import verify_password
from app.database import get_db
from app.main import app
from app.models.user import ADMIN, INVESTOR, MANAGER, User

KEY = "cle-interne-de-test"


@pytest.fixture
async def client(db):
    """An ASGI client bound to the test session, with the shared key configured."""
    get_settings.cache_clear()
    settings = get_settings()
    previous = settings.ALICE_INTERNAL_KEY
    settings.ALICE_INTERNAL_KEY = KEY

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://invest.test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    settings.ALICE_INTERNAL_KEY = previous


def auth(**extra) -> dict:
    return {"X-Internal-Key": KEY, **extra}


async def _manager(db, email: str, *, role: str = MANAGER, active: bool = True) -> User:
    user = User(
        email=email,
        hashed_password="h",
        account_name="Gestion",
        role=role,
        is_active=active,
    )
    db.add(user)
    await db.flush()
    return user


class TestTheDoorIsClosed:
    async def test_no_key_is_refused(self, client):
        assert (await client.get("/internal/managers")).status_code == 401

    async def test_a_wrong_key_is_refused(self, client):
        r = await client.get("/internal/managers", headers={"X-Internal-Key": "faux"})
        assert r.status_code == 401

    async def test_the_right_key_opens(self, client):
        assert (
            await client.get("/internal/managers", headers=auth())
        ).status_code == 200


class TestNothingIsSwallowedInSilence:
    async def test_the_postal_identity_alice_pushes_down_is_stored(self, client, db):
        r = await client.post(
            "/internal/managers",
            headers=auth(),
            json={
                "email": "Gestion@Fonds.FR",
                "full_name": "Gestion du fonds",
                "password": "provisoire-1234",
                "phone": "+33600000000",
                "address": "12 rue de la Bourse",
                "zip_code": "75002",
                "city": "Paris",
                "country": "France",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["email"] == "gestion@fonds.fr"  # normalisé, pas stocké tel quel
        assert body["full_name"] == "Gestion du fonds"
        assert body["city"] == "Paris" and body["zip_code"] == "75002"

        user = (
            await db.execute(select(User).where(User.email == "gestion@fonds.fr"))
        ).scalar_one()
        assert user.address == "12 rue de la Bourse"
        assert user.must_change_password is True
        assert verify_password("provisoire-1234", user.hashed_password)

    async def test_the_management_companys_number_survives_the_round_trip(
        self, client, db
    ):
        """🔴 WRITTEN, STORED, AND READ BACK. A field the console sends and never sees again
        looks LOST: the form would come back empty every time somebody opens the record, and
        an operator would eventually retype it. Pydantic drops an undeclared key without a
        word, and this repository has already shipped a schema that swallowed one and
        produced NaN in production.

        ⚠️ AND IT IS NOT THE LANDLORD'S NUMBER. `owner_national_id` travels in the same
        payload and is deliberately thrown away, because a fund has no landlord. Putting one
        in the other's column would file a private individual's number as a management
        company's registration.
        """
        r = await client.post(
            "/internal/managers",
            headers=auth(),
            json={
                "email": "immat@fonds.fr",
                "full_name": "Meridian Capital Partners",
                "password": "provisoire-1234",
                "company_number": "90112345600017",
                "owner_company_number": "77712345600011",
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["company_number"] == "90112345600017"

        user = (
            await db.execute(select(User).where(User.email == "immat@fonds.fr"))
        ).scalar_one()
        assert user.company_number == "90112345600017"
        assert not hasattr(user, "owner_company_number")

        listed = await client.get("/internal/managers", headers=auth())
        found = [m for m in listed.json() if m["email"] == "immat@fonds.fr"]
        assert found and found[0]["company_number"] == "90112345600017", (
            "the number is not read back in the list: the console will believe it lost"
        )

    async def test_the_old_name_is_still_accepted_while_the_console_catches_up(
        self, client, db
    ):
        """⚠️ THE READER MOVES FIRST, ALWAYS.

        The console still sends `national_id` until its own deploy lands. A receiver that
        stopped recognising it would not raise: Pydantic drops what it does not declare,
        the field would arrive empty, and BOTH suites would stay green while the number
        silently vanished from every record created in between.
        """
        r = await client.post(
            "/internal/managers",
            headers=auth(),
            json={
                "email": "ancien-nom@fonds.fr",
                "full_name": "Legacy Capital",
                "password": "provisoire-1234",
                "national_id": "90112345600017",
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["company_number"] == "90112345600017", (
            "the old name is no longer heard: the number sent by the console is dropped "
            "in silence, and nothing anywhere turns red."
        )

    async def test_the_landlord_identity_is_accepted_and_deliberately_not_stored(
        self, client, db
    ):
        """A fund has no landlord. Refusing it would break Alice; swallowing it without
        saying so is the defect. So it is accepted, ignored, and the decision is NAMED."""
        payload = {
            "email": "avec-bailleur@fonds.fr",
            "full_name": "X",
            "password": "provisoire-1234",
            **{f: "quelque chose" for f in IGNORED_BY_DESIGN},
        }
        r = await client.post("/internal/managers", headers=auth(), json=payload)
        assert r.status_code == 201
        user = (
            await db.execute(select(User).where(User.email == "avec-bailleur@fonds.fr"))
        ).scalar_one()
        for field in IGNORED_BY_DESIGN:
            assert not hasattr(user, field), (
                f"{field} est stocké : la décision a changé"
            )

    async def test_a_partial_update_does_not_blank_what_it_did_not_send(
        self, client, db
    ):
        user = await _manager(db, "patch@fonds.fr")
        user.city = "Abidjan"
        user.phone = "+2250700000000"
        await db.flush()

        r = await client.patch(
            f"/internal/managers/{user.id}",
            headers=auth(),
            json={"email": "patch@fonds.fr", "city": "Paris"},
        )
        assert r.status_code == 200
        await db.refresh(user)
        assert user.city == "Paris"
        # The field missing from the payload has not moved.
        assert user.phone == "+2250700000000"
        assert user.account_name == "Gestion"


class TestTheGuardProtectsTheOutcomeNotTheRole:
    async def test_the_last_active_administrator_cannot_be_deleted(self, client, db):
        user = await _manager(db, "seul@fonds.fr")
        r = await client.delete(f"/internal/managers/{user.id}", headers=auth())
        assert r.status_code == 409
        assert "dernier" in r.json()["detail"]

    async def test_the_last_active_administrator_cannot_be_blocked(self, client, db):
        user = await _manager(db, "seul@fonds.fr")
        r = await client.post(f"/internal/managers/{user.id}/block", headers=auth())
        assert r.status_code == 409

    async def test_but_they_can_be_renamed_and_have_their_password_reset(
        self, client, db
    ):
        """What a guard on the ROLE wrongly forbade: renaming locks nobody out."""
        user = await _manager(db, "seul@fonds.fr")
        assert (
            await client.patch(
                f"/internal/managers/{user.id}",
                headers=auth(),
                json={"email": "seul@fonds.fr", "full_name": "Nouveau nom"},
            )
        ).status_code == 200
        assert (
            await client.post(
                f"/internal/managers/{user.id}/reset-password",
                headers=auth(),
                json={"new_password": "un-autre-mot-de-passe"},
            )
        ).status_code == 204

    async def test_with_a_second_administrator_the_first_may_go(self, client, db):
        first = await _manager(db, "premier@fonds.fr")
        await _manager(db, "second@fonds.fr", role=ADMIN)
        assert (
            await client.delete(f"/internal/managers/{first.id}", headers=auth())
        ).status_code == 204

    async def test_an_inactive_second_account_does_not_count_as_a_way_back_in(
        self, client, db
    ):
        """Un compte bloqué ne peut pas administrer : il ne remplace pas le dernier actif."""
        user = await _manager(db, "actif@fonds.fr")
        await _manager(db, "bloque@fonds.fr", active=False)
        r = await client.delete(f"/internal/managers/{user.id}", headers=auth())
        assert r.status_code == 409

    async def test_an_investor_account_is_not_an_administrator(self, client, db):
        user = await _manager(db, "gestion@fonds.fr")
        db.add(User(email="souscripteur@fonds.fr", hashed_password="h", role=INVESTOR))
        await db.flush()
        r = await client.delete(f"/internal/managers/{user.id}", headers=auth())
        assert r.status_code == 409


class TestBlockAndUnblockAreSymmetrical:
    async def test_block_returns_exactly_what_it_deactivated(self, client, db):
        await _manager(db, "autre@fonds.fr")
        user = await _manager(db, "cible@fonds.fr")
        r = await client.post(f"/internal/managers/{user.id}/block", headers=auth())
        assert r.status_code == 200
        assert r.json()["user_ids"] == [str(user.id)]
        await db.refresh(user)
        assert user.is_active is False

    async def test_unblock_restores_only_the_listed_accounts(self, client, db):
        await _manager(db, "autre@fonds.fr")
        user = await _manager(db, "cible@fonds.fr")
        collateral = await _manager(
            db, "desactive-pour-autre-chose@fonds.fr", active=False
        )

        await client.post(f"/internal/managers/{user.id}/block", headers=auth())
        r = await client.post(
            f"/internal/managers/{user.id}/unblock",
            headers=auth(),
            json={"user_ids": [str(user.id)]},
        )
        assert r.status_code == 204
        await db.refresh(user)
        await db.refresh(collateral)
        assert user.is_active is True
        # 🔴 The account deactivated for another reason has NOT been resurrected.
        assert collateral.is_active is False


class TestALoginLinkNeverBypassesABlock:
    async def test_a_blocked_account_gets_no_link(self, client, db):
        await _manager(db, "autre@fonds.fr")
        user = await _manager(db, "bloque@fonds.fr", active=False)
        r = await client.post(
            f"/internal/managers/{user.id}/login-link", headers=auth()
        )
        assert r.status_code == 409

    async def test_an_active_account_gets_one(self, client, db):
        user = await _manager(db, "actif@fonds.fr")
        r = await client.post(
            f"/internal/managers/{user.id}/login-link", headers=auth()
        )
        assert r.status_code == 200 and r.json()["token"]


class TestBillingIdentityAnswersForFormerCustomersToo:
    async def test_it_answers_for_an_account_that_is_not_a_manager(self, client, db):
        db.add(
            User(
                email="ancien@fonds.fr",
                hashed_password="h",
                account_name="Ancien client",
                role=INVESTOR,
            )
        )
        await db.flush()
        found = (
            await db.execute(select(User).where(User.email == "ancien@fonds.fr"))
        ).scalar_one()

        r = await client.get(f"/internal/billing-identity/{found.id}", headers=auth())
        assert r.status_code == 200
        assert r.json()["full_name"] == "Ancien client"

        # Whereas the « manager » contract does not see them, and that is correct.
        assert (
            await client.get(f"/internal/managers/{found.id}", headers=auth())
        ).status_code == 404

    async def test_an_unknown_account_is_a_404_not_an_empty_answer(self, client):
        r = await client.get(
            f"/internal/billing-identity/{uuid.uuid4()}", headers=auth()
        )
        assert r.status_code == 404


class TestStatsSayWhatTheProductActuallyDoes:
    async def test_the_figures_cover_the_customers_and_the_fund(self, client, db):
        await _manager(db, "gestion@fonds.fr")
        await _manager(db, "bloque@fonds.fr", active=False)
        db.add(User(email="souscripteur@fonds.fr", hashed_password="h", role=INVESTOR))
        await db.flush()

        body = (await client.get("/internal/stats", headers=auth())).json()
        assert body["managers"] == 2
        assert body["active_managers"] == 1
        assert body["users"] == 3
        # Un tableau de bord qui n'affiche qu'un nombre de clients ne dit rien de l'usage.
        assert "investors" in body and "subscriptions" in body


class TestTheProductRefusesWhatItCannotHonour:
    async def test_an_unknown_role_is_refused_rather_than_stored(self, client):
        r = await client.post(
            "/internal/managers",
            headers=auth(),
            json={
                "email": "x@fonds.fr",
                "password": "provisoire-1234",
                "role": "syndic",
            },
        )
        assert r.status_code == 422

    async def test_an_account_without_a_credential_is_refused(self, client):
        r = await client.post(
            "/internal/managers", headers=auth(), json={"email": "x@fonds.fr"}
        )
        assert r.status_code == 422

    async def test_a_duplicate_e_mail_is_a_conflict(self, client, db):
        await _manager(db, "deja@fonds.fr")
        r = await client.post(
            "/internal/managers",
            headers=auth(),
            json={"email": "deja@fonds.fr", "password": "provisoire-1234"},
        )
        assert r.status_code == 409
