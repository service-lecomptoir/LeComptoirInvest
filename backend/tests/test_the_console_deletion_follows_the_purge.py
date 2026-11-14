"""The console's deletion of an account runs the purge of the erasure, held by its guards;
the product says its hold to Alice the morning it knows it.

The owner, 14 Nov 2026: the console's deletion follows the purge, and the product tells
Alice when it holds an erasure. `DELETE /internal/managers/{id}` removed the account row alone: the
firm's funds, investors, subscriptions, money and team stayed, with no holder. docs/THE_SPACE_IS_ERASED_AFTER_THE_EXPORT_DAYS.md. One rule per test.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.config import get_settings
from app.core import firm_scope, self_delete
from app.core.security import hash_password
from app.database import get_db
from app.main import app
from app.models.account_deletion import ENDED, AccountDeletion
from app.models.audit_log import AuditLog
from app.models.fund import Fund
from app.models.user import ADMIN, MANAGER, User

KEY = "cle-interne-de-test"
HEADERS = {"X-Internal-Key": KEY}


@pytest.fixture
async def client(db, monkeypatch):
    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "ALICE_INTERNAL_KEY", KEY)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://invest.test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


async def _account(db, *, role: str = MANAGER, firm_id=None) -> User:
    user = User(
        email=f"{uuid.uuid4().hex[:8]}@fonds-essai.fr",
        hashed_password=hash_password("Motdepasse-1234"),
        account_name="Meridian Capital",
        role=role,
        firm_id=firm_id,
    )
    db.add(user)
    await db.flush()
    return user


async def _holder_with_a_fund(db) -> User:
    """A holder with a fund, and another account able to administer (the deletion never
    takes the last one)."""
    holder = await _account(db)
    await _account(db, role=ADMIN)
    db.add(
        Fund(id=uuid.uuid4(), name="Fonds Meridian", currency="EUR", firm_id=holder.id)
    )
    await db.flush()
    return holder


async def _funds(db, firm) -> int:
    with firm_scope.all_firms():
        found = await db.execute(
            select(func.count()).select_from(Fund).where(Fund.firm_id == firm)
        )
    return int(found.scalar() or 0)


async def _alive(db, user_id) -> bool:
    return await db.get(User, user_id, populate_existing=True) is not None


def _shared(found: int = 1):
    return patch(
        "app.services.firm_purge.shared_with_another_space",
        new=AsyncMock(return_value=found),
    )


async def _journal(db, action: str, user_id) -> list[AuditLog]:
    return list(
        (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.action == action, AuditLog.entity_id == str(user_id)
                )
            )
        ).scalars()
    )


# ── The console's deletion runs the purge ───────────────────────────────────────────


async def test_the_console_deletion_leaves_no_fund_behind(client, db):
    holder = await _holder_with_a_fund(db)
    firm = holder.id

    r = await client.delete(f"/internal/managers/{firm}", headers=HEADERS)

    assert r.status_code == 204, r.text
    assert await _funds(db, firm) == 0


async def test_the_console_deletion_takes_the_team_accounts(client, db):
    holder = await _holder_with_a_fund(db)
    member = await _account(db, role=MANAGER, firm_id=holder.id)
    member_id = member.id

    await client.delete(f"/internal/managers/{holder.id}", headers=HEADERS)

    assert not await _alive(db, member_id)


async def test_a_team_account_deleted_from_the_console_goes_alone(client, db):
    holder = await _holder_with_a_fund(db)
    member = await _account(db, role=MANAGER, firm_id=holder.id)

    await client.delete(f"/internal/managers/{member.id}", headers=HEADERS)

    assert await _funds(db, holder.id) == 1


async def test_the_console_deletion_is_journaled_with_the_numbers(client, db):
    holder = await _holder_with_a_fund(db)
    firm = holder.id

    await client.delete(f"/internal/managers/{firm}", headers=HEADERS)

    [row] = await _journal(db, "account.console_deletion_executed", firm)
    assert row.details["counts"]["accounts"] == 1


# ── Held by the same guards ─────────────────────────────────────────────────────────


async def test_a_link_to_another_workspace_refuses_with_its_code(client, db):
    holder = await _holder_with_a_fund(db)

    with _shared():
        r = await client.delete(f"/internal/managers/{holder.id}", headers=HEADERS)

    assert (r.status_code, r.headers.get("X-Refusal")) == (409, self_delete.SHARED_ROWS)


async def test_a_platform_account_inside_the_firm_refuses_with_its_code(client, db):
    holder = await _holder_with_a_fund(db)
    await _account(db, role=ADMIN, firm_id=holder.id)

    r = await client.delete(f"/internal/managers/{holder.id}", headers=HEADERS)

    assert (r.status_code, r.headers.get("X-Refusal")) == (
        409,
        self_delete.PLATFORM_ACCOUNT_INSIDE,
    )


async def test_a_refused_deletion_deletes_nothing(client, db):
    holder = await _holder_with_a_fund(db)

    with _shared():
        await client.delete(f"/internal/managers/{holder.id}", headers=HEADERS)

    assert await _funds(db, holder.id) == 1


async def test_a_refused_deletion_says_the_shared_sentence(client, db):
    holder = await _holder_with_a_fund(db)

    with _shared():
        r = await client.delete(f"/internal/managers/{holder.id}", headers=HEADERS)

    assert r.json()["detail"] == self_delete.hold_phrase(self_delete.SHARED_ROWS)


async def test_the_last_administrator_refuses_with_its_code(client, db):
    alone = await _account(db)

    r = await client.delete(f"/internal/managers/{alone.id}", headers=HEADERS)

    assert (r.status_code, r.headers.get("X-Refusal")) == (
        409,
        self_delete.LAST_ADMINISTRATOR,
    )


async def test_a_refused_deletion_is_journaled_with_why(client, db):
    alone = await _account(db)

    await client.delete(f"/internal/managers/{alone.id}", headers=HEADERS)

    [row] = await _journal(db, "account.console_deletion_held", alone.id)
    assert row.details["why"] == self_delete.LAST_ADMINISTRATOR


async def test_the_console_asks_the_hold_before_anything_stops(client, db):
    holder = await _holder_with_a_fund(db)

    with _shared():
        r = await client.get(
            f"/internal/managers/{holder.id}/deletion-hold", headers=HEADERS
        )

    assert r.json()["code"] == self_delete.SHARED_ROWS


async def test_nothing_holds_a_plain_workspace(client, db):
    holder = await _holder_with_a_fund(db)

    r = await client.get(
        f"/internal/managers/{holder.id}/deletion-hold", headers=HEADERS
    )

    assert r.json() == {"code": None, "reason": None}


# ── Alice hears the hold the morning it is known ────────────────────────────────────


def _listed(*users):
    return patch(
        "app.services.alice_client.erasures_due",
        new=AsyncMock(
            return_value=[
                {
                    "manager_user_id": str(u.id),
                    "access_until": "2026-09-30T21:59:59",
                    "erase_on": self_delete.FIRST_ERASURE_DAY.isoformat(),
                    "status": "scheduled",
                }
                for u in users
            ]
        ),
    )


def _tally() -> dict:
    return {"planned": 0, "withdrawn": 0, "failed": 0}


async def _plan(db, said: AsyncMock, *users) -> None:
    from app.services.account_deletion_service import plan_ended

    with _listed(*users), patch("app.services.alice_client.say_erasure_hold", new=said):
        await plan_ended(db, _tally())


async def test_the_morning_plan_tells_alice_the_hold(db):
    holder = await _account(db)
    await _account(db, role=ADMIN)
    said = AsyncMock(return_value=True)

    with _shared():
        await _plan(db, said, holder)

    said.assert_awaited_once_with(holder.id, self_delete.SHARED_ROWS)


async def test_the_morning_plan_tells_alice_when_nothing_holds(db):
    holder = await _account(db)
    await _account(db, role=ADMIN)
    said = AsyncMock(return_value=True)

    await _plan(db, said, holder)

    said.assert_awaited_once_with(holder.id, None)


async def test_an_alice_that_does_not_answer_the_hold_plans_all_the_same(db):
    holder = await _account(db)
    await _account(db, role=ADMIN)

    with _shared():
        await _plan(db, AsyncMock(side_effect=RuntimeError("Alice down")), holder)

    rows = (
        await db.execute(
            select(AccountDeletion).where(
                AccountDeletion.user_id == holder.id, AccountDeletion.kind == ENDED
            )
        )
    ).scalars()
    assert len(list(rows)) == 1


async def test_an_alice_without_the_route_is_no_error(monkeypatch):
    import httpx

    from app.services import alice_client

    session = MagicMock()
    session.post = AsyncMock(return_value=MagicMock(status_code=404))
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(alice_client, "_target", lambda: ("http://alice.test", {}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: session)

    said = await alice_client.say_erasure_hold(uuid.uuid4(), self_delete.SHARED_ROWS)

    assert said is False
