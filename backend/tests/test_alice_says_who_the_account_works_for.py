"""The console says who an account works for, and this product keeps it in its own words.

🔴 WHAT IS HELD STILL HERE (decided on 28 September 2026):

  * Alice sends the neutral `acts_for` -- « self » or « clients » -- and this product stores
    its OWN kind for it: `single_fund` (« Club ou fonds ») or `management_company`
    (« Société de gestion »). Written, stored, and read back on every route that returns an
    account, including the answer to the creation itself;
  * an older console still sends `role = "gestionnaire"` or `"gestionnaire_proprio"`. Those
    were refused with a 422, which blocked self-service sign-up. They are now a manager, and
    they say NOTHING about the kind: it stays NULL rather than guessed;
  * any other `acts_for` is refused, and the refusal names the two accepted values.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import get_settings
from app.core import account_kind
from app.core.security import create_access_token
from app.database import get_db
from app.main import app
from app.models.user import ADMIN, MANAGER, User

KEY = "cle-interne-de-test"
PASSWORD = "provisoire-1234"


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


def auth() -> dict:
    return {"X-Internal-Key": KEY}


async def _create(client, email: str, **extra):
    return await client.post(
        "/internal/managers",
        headers=auth(),
        json={"email": email, "full_name": "Fonds", "password": PASSWORD, **extra},
    )


async def _stored(db, email: str) -> User:
    return (await db.execute(select(User).where(User.email == email))).scalar_one()


class TestTheConsolesWordBecomesThisProductsKind:
    async def test_self_is_a_club_or_a_fund(self, client, db):
        r = await _create(client, "club@fonds.fr", acts_for="self")
        assert r.status_code == 201, r.text
        body = r.json()
        # 🔴 On the answer to the creation itself, not only on a later read: the console
        # shows what it just wrote from this very body.
        assert body["account_kind"] == "single_fund"
        assert body["account_kind_label"] == "Club ou fonds"
        assert body["acts_for"] == "self"
        assert (await _stored(db, "club@fonds.fr")).account_kind == "single_fund"

    async def test_clients_is_a_management_company(self, client, db):
        r = await _create(client, "sgp@fonds.fr", acts_for="clients")
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["account_kind"] == "management_company"
        assert body["account_kind_label"] == "Société de gestion"
        assert body["acts_for"] == "clients"
        assert (await _stored(db, "sgp@fonds.fr")).account_kind == "management_company"

    async def test_the_mapping_reads_back_the_word_it_was_given(self):
        """One table, read both ways: what Alice writes is what Alice reads back."""
        for word in account_kind.ACTS_FOR:
            assert account_kind.acts_for_of(account_kind.kind_for(word)) == word
        assert account_kind.acts_for_of(None) is None
        assert account_kind.label_of(None) is None


class TestTheOldConsoleIsNoLongerTurnedAway:
    @pytest.mark.parametrize("legacy", ["gestionnaire", "gestionnaire_proprio"])
    async def test_a_legacy_role_creates_a_manager_with_no_kind(
        self, client, db, legacy
    ):
        """🔴 IT WAS A 422, AND THAT WAS SIGN-UP BLOCKED. And the kind is NOT derived from
        the old word: « gestionnaire_proprio » never meant « works for itself »."""
        email = f"{legacy}@fonds.fr"
        r = await _create(client, email, role=legacy)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["role"] == MANAGER
        assert body["account_kind"] is None
        assert body["account_kind_label"] is None
        assert body["acts_for"] is None
        user = await _stored(db, email)
        assert user.role == MANAGER and user.account_kind is None

    async def test_a_legacy_role_with_acts_for_takes_the_kind_from_acts_for(
        self, client
    ):
        r = await _create(
            client, "les-deux@fonds.fr", role="gestionnaire", acts_for="clients"
        )
        assert r.status_code == 201, r.text
        assert r.json()["account_kind"] == "management_company"

    async def test_a_legacy_role_on_an_update_demotes_nobody(self, client, db):
        """The old word means « an account that runs the business ». Read as « make this a
        manager », the next identity push would quietly demote an administrator."""
        admin = User(email="admin@fonds.fr", hashed_password="h", role=ADMIN)
        db.add(admin)
        await db.flush()
        r = await client.patch(
            f"/internal/managers/{admin.id}",
            headers=auth(),
            json={"email": "admin@fonds.fr", "role": "gestionnaire"},
        )
        assert r.status_code == 200, r.text
        await db.refresh(admin)
        assert admin.role == ADMIN

    async def test_a_genuinely_unknown_role_is_still_refused(self, client):
        r = await _create(client, "syndic@fonds.fr", role="syndic")
        assert r.status_code == 422


class TestAWordThisProductCannotReadIsRefused:
    @pytest.mark.parametrize("word", ["tiers", "SELF", ""])
    async def test_an_unknown_acts_for_is_a_422_naming_both_values(
        self, client, db, word
    ):
        r = await _create(client, "inconnu@fonds.fr", acts_for=word)
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert "« self »" in detail and "« clients »" in detail, detail
        assert (
            await db.execute(select(User.id).where(User.email == "inconnu@fonds.fr"))
        ).scalar_one_or_none() is None

    async def test_an_unknown_acts_for_on_an_update_writes_nothing(self, client, db):
        created = await _create(client, "intact@fonds.fr", acts_for="self")
        manager_id = created.json()["id"]
        r = await client.patch(
            f"/internal/managers/{manager_id}",
            headers=auth(),
            json={"email": "intact@fonds.fr", "city": "Lyon", "acts_for": "tiers"},
        )
        assert r.status_code == 422
        user = await _stored(db, "intact@fonds.fr")
        await db.refresh(user)
        assert user.account_kind == "single_fund"


class TestTheKindChangesOnlyWhenTheConsoleSaysSo:
    async def test_an_update_changes_the_kind(self, client, db):
        created = await _create(client, "bascule@fonds.fr", acts_for="self")
        manager_id = created.json()["id"]
        r = await client.patch(
            f"/internal/managers/{manager_id}",
            headers=auth(),
            json={"email": "bascule@fonds.fr", "acts_for": "clients"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["account_kind"] == "management_company"
        assert r.json()["account_kind_label"] == "Société de gestion"
        assert r.json()["acts_for"] == "clients"
        user = await _stored(db, "bascule@fonds.fr")
        await db.refresh(user)
        assert user.account_kind == "management_company"

    async def test_an_update_without_acts_for_leaves_the_kind_alone(self, client, db):
        created = await _create(client, "stable@fonds.fr", acts_for="clients")
        manager_id = created.json()["id"]
        r = await client.patch(
            f"/internal/managers/{manager_id}",
            headers=auth(),
            json={"email": "stable@fonds.fr", "city": "Paris", "role": "gestionnaire"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["account_kind"] == "management_company"


class TestEveryRouteReadsTheKindBack:
    async def test_the_listing_and_the_record_carry_the_label(self, client):
        created = await _create(client, "liste@fonds.fr", acts_for="self")
        manager_id = created.json()["id"]

        listed = await client.get("/internal/managers", headers=auth())
        found = [m for m in listed.json() if m["email"] == "liste@fonds.fr"]
        assert found, listed.text
        assert found[0]["account_kind"] == "single_fund"
        assert found[0]["account_kind_label"] == "Club ou fonds"
        assert found[0]["acts_for"] == "self"

        one = await client.get(f"/internal/managers/{manager_id}", headers=auth())
        assert one.json()["account_kind_label"] == "Club ou fonds"

    async def test_the_account_sees_its_own_kind_in_its_own_language(self, client, db):
        """The label is the server's, so it is translated at the server."""
        user = User(
            email="moi@fonds.fr",
            hashed_password="h",
            role=MANAGER,
            account_kind=account_kind.MANAGEMENT_COMPANY,
        )
        db.add(user)
        await db.flush()
        bearer = {
            "Authorization": f"Bearer {create_access_token(str(user.id), MANAGER)}"
        }

        fr = (await client.get("/api/v1/auth/me", headers=bearer)).json()
        assert fr["account_kind"] == "management_company"
        assert fr["account_kind_label"] == "Société de gestion"

        en = (
            await client.get(
                "/api/v1/auth/me", headers={**bearer, "Accept-Language": "en"}
            )
        ).json()
        assert en["account_kind_label"] == "Management company"

    async def test_an_account_nobody_qualified_says_so(self, client, db):
        user = User(email="ancien@fonds.fr", hashed_password="h", role=MANAGER)
        db.add(user)
        await db.flush()
        bearer = {
            "Authorization": f"Bearer {create_access_token(str(user.id), MANAGER)}"
        }
        body = (await client.get("/api/v1/auth/me", headers=bearer)).json()
        assert body["account_kind"] is None and body["account_kind_label"] is None
