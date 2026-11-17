"""Two writes clicked at the same moment, in two real sessions, never spend the same room.

🔴 WHY REAL SESSIONS. Every other test of this suite runs in ONE session rolled back at the
end, where two writes are always one after the other and a missing lock cannot show. Here
two sessions commit for real, each holding its transaction open until the other has done
its own work (or two seconds have passed): without a lock both measure the room before the
other writes, and both pass.

⚠️ THE ROWS ARE COMMITTED, SO THEY ARE ERASED AFTERWARDS, by id, with their journal lines.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import instruments, kyc
from app.models.investor import Investor
from app.models.subscription import Subscription
from app.models.treasury import IN, BankMovement
from app.services import treasury_service
from tests.conftest import _ASYNC_URL

TODAY = date(2026, 3, 2)


@pytest.fixture
async def maker(migrated_schema):
    engine = create_async_engine(
        _ASYNC_URL, connect_args={"server_settings": {"search_path": migrated_schema}}
    )
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def committed(maker):
    """An accepted investor, a subscription of 1 000 EUR and a transfer of 1 000 EUR."""
    ids = {
        "investor": uuid.uuid4(),
        "subscription": uuid.uuid4(),
        "movement": uuid.uuid4(),
    }
    async with maker() as session:
        session.add(
            Investor(
                id=ids["investor"],
                kind="personne",
                last_name="Concurrent",
                first_name="Clic",
                kyc_status=kyc.ACCEPTED,
            )
        )
        await session.flush()
        session.add_all(
            [
                Subscription(
                    id=ids["subscription"],
                    investor_id=ids["investor"],
                    instrument=instruments.EQUITY,
                    amount=Decimal("1000"),
                    currency="EUR",
                    signed_on=date(2026, 1, 15),
                ),
                BankMovement(
                    id=ids["movement"],
                    account_iban="FR7630006000011234567890189",
                    direction=IN,
                    amount=Decimal("1000"),
                    currency="EUR",
                    value_date=date(2026, 3, 1),
                    counterparty_name="Clic Concurrent",
                ),
            ]
        )
        await session.commit()
    yield ids
    async with maker() as session:
        for statement in (
            "DELETE FROM contributions WHERE subscription_id = :subscription",
            "DELETE FROM capital_calls WHERE subscription_id = :subscription",
            "DELETE FROM subscriptions WHERE id = :subscription",
            "DELETE FROM bank_movements WHERE id = :movement",
            "DELETE FROM investors WHERE id = :investor",
        ):
            await session.execute(text(statement), ids)
        await session.execute(
            text(
                "DELETE FROM audit_logs WHERE entity_id IN "
                "(:investor, :subscription, :movement)"
            ),
            {k: str(v) for k, v in ids.items()},
        )
        await session.commit()


async def _race(maker, work):
    """Run `work` in two sessions at once; return what each one raised, or None."""
    finished = [asyncio.Event(), asyncio.Event()]

    async def one(me: int):
        async with maker() as session:
            try:
                await work(session)
            except ValueError as exc:
                finished[me].set()
                await session.rollback()
                return exc
            finished[me].set()
            try:
                # Hold the transaction open until the other has done its work: without a
                # lock it has, by then, measured the same room.
                await asyncio.wait_for(finished[1 - me].wait(), timeout=2)
            except asyncio.TimeoutError:
                pass
            await session.commit()
            return None

    return await asyncio.gather(one(0), one(1))


async def test_one_transfer_is_never_attributed_twice_over(maker, committed):
    """1 000 EUR received, two attributions of 700 EUR clicked at once: one passes."""

    async def attribute(session):
        await treasury_service.attribute(
            session,
            movement=await session.get(BankMovement, committed["movement"]),
            subscription=await session.get(Subscription, committed["subscription"]),
            amount=Decimal("700"),
            capital_call=None,
            attributed_by="test",
            today=TODAY,
        )

    outcomes = await _race(maker, attribute)
    assert sum(o is None for o in outcomes) == 1, outcomes

    async with maker() as session:
        attributed = (
            await session.execute(
                text(
                    "SELECT COALESCE(SUM(amount), 0) FROM contributions "
                    "WHERE bank_movement_id = :m"
                ),
                {"m": committed["movement"]},
            )
        ).scalar_one()
    assert attributed == Decimal("700")


async def test_two_calls_never_ask_for_more_than_was_committed(maker, committed):
    """1 000 EUR committed, two calls of 700 EUR opened at once: one passes."""

    async def call(session):
        await treasury_service.open_call(
            session,
            subscription=await session.get(Subscription, committed["subscription"]),
            amount=Decimal("700"),
            called_on=TODAY,
            due_on=date(2026, 4, 1),
        )

    outcomes = await _race(maker, call)
    assert sum(o is None for o in outcomes) == 1, outcomes
