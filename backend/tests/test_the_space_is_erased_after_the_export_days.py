"""The space of an ended subscription is erased once its thirty days to export have run out.

The owner, 13 Nov 2026, yes to the erasure after the thirty days (terms of sale 7.4, data
processing agreement 11). Alice decides the day, Invest checks it on her FRESH answer and
its own reading; the purge erases the firm and nothing of its neighbour's.
docs/THE_SPACE_IS_ERASED_AFTER_THE_EXPORT_DAYS.md. One rule per test.
"""

from __future__ import annotations

import uuid
from contextlib import ExitStack
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.core import firm_scope, instruments, kyc, self_delete
from app.core.landlord_kind_values import PERSON
from app.core.security import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.models.account_deletion import ENDED, AccountDeletion
from app.models.audit_log import AuditLog
from app.models.fund import Fund
from app.models.investor import Investor, InvestorDocument
from app.models.project import Deployment, Project, ProjectReturn, ProjectValuation
from app.models.subscription import (
    Subscription,
    SubscriptionConversion,
    SubscriptionRequest,
)
from app.models.treasury import (
    IN,
    OUT,
    BankMovement,
    CapitalCall,
    Contribution,
    Distribution,
)
from app.models.two_factor import UserTwoFactor
from app.models.user import ADMIN, INVESTOR, MANAGER, User
from app.services import account_deletion_service, licence_state

#: The last second of September 2026 in Paris, as Alice writes it (naive UTC).
ENDED_IN_SEPTEMBER = "2026-09-30T21:59:59"
#: Thirty days after the launch: the first day any space may be erased.
FIRST = self_delete.FIRST_ERASURE_DAY
CURRENCY = "EUR"


@pytest.fixture
async def client(db):
    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://invest.test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# ── The scene ───────────────────────────────────────────────────────────────────────


@pytest.fixture
async def platform_admin(db) -> User:
    """The installation keeps an administrator: the erasure never removes the last one."""
    admin = User(
        email=f"admin-{uuid.uuid4().hex[:8]}@plateforme-essai.fr",
        hashed_password=hash_password("Motdepasse-1234"),
        account_name="Plateforme",
        role=ADMIN,
    )
    db.add(admin)
    await db.flush()
    return admin


async def _account(db, role: str, firm=None, name="Meridian Capital") -> User:
    user = User(
        email=f"{role}-{uuid.uuid4().hex[:8]}@fonds-essai.fr",
        hashed_password=hash_password("Motdepasse-1234"),
        account_name=name,
        role=role,
        firm_id=firm,
    )
    db.add(user)
    await db.flush()
    return user


async def _space(db, name: str = "Meridian Capital") -> User:
    """A subscriber with one of everything, stamped by hand: a fund, a project valued,
    deployed and paying back, an investor with a KYC piece, an account and a request, two
    subscriptions converted one into the other, a capital call paid, a distribution, the
    bank movements behind them, a colleague with a second factor."""
    holder = await _account(db, MANAGER, name=name)
    firm = holder.id
    tag = uuid.uuid4().hex[:10].upper()
    fund = Fund(id=uuid.uuid4(), name=f"Fonds {name}", currency=CURRENCY, firm_id=firm)
    db.add(fund)
    await db.flush()
    project = Project(
        id=uuid.uuid4(),
        fund_id=fund.id,
        name="Projet",
        currency=CURRENCY,
        firm_id=firm,
    )
    investor_account = await _account(db, INVESTOR, firm, name="Grace Hopper")
    investor = Investor(
        id=uuid.uuid4(),
        kind=PERSON,
        last_name="Hopper",
        email=f"investisseur-{tag.lower()}@exemple.fr",
        kyc_status=kyc.ACCEPTED,
        firm_id=firm,
        user_id=investor_account.id,
    )
    money_in = BankMovement(
        id=uuid.uuid4(),
        account_iban=f"FR76{tag}IN",
        direction=IN,
        amount=Decimal("10000"),
        currency=CURRENCY,
        value_date=date(2026, 1, 10),
        firm_id=firm,
    )
    money_out = BankMovement(
        id=uuid.uuid4(),
        account_iban=f"FR76{tag}OUT",
        direction=OUT,
        amount=Decimal("8000"),
        currency=CURRENCY,
        value_date=date(2026, 1, 12),
        firm_id=firm,
    )
    db.add_all([project, investor, money_in, money_out])
    await db.flush()
    loan, equity = (
        Subscription(
            id=uuid.uuid4(),
            fund_id=fund.id,
            investor_id=investor.id,
            instrument=instrument,
            amount=Decimal("50000"),
            currency=CURRENCY,
            signed_on=date(2026, 1, 5),
        )
        for instrument in (instruments.LOAN, instruments.EQUITY)
    )
    db.add_all([loan, equity])
    await db.flush()
    call = CapitalCall(
        id=uuid.uuid4(),
        subscription_id=equity.id,
        reference=f"AP-{tag}",
        amount=Decimal("10000"),
        currency=CURRENCY,
        called_on=date(2026, 1, 6),
        due_on=date(2026, 1, 20),
    )
    db.add(call)
    await db.flush()
    db.add_all(
        [
            Contribution(
                bank_movement_id=money_in.id,
                subscription_id=equity.id,
                capital_call_id=call.id,
                amount=Decimal("10000"),
                currency=CURRENCY,
            ),
            Distribution(
                subscription_id=equity.id,
                currency=CURRENCY,
                decided_on=date(2026, 6, 30),
            ),
            SubscriptionConversion(
                from_subscription_id=loan.id,
                to_subscription_id=equity.id,
                converted_on=date(2026, 3, 1),
                principal_converted=Decimal("50000"),
                currency=CURRENCY,
            ),
            SubscriptionRequest(
                investor_id=investor.id,
                subscription_id=equity.id,
                instrument=instruments.EQUITY,
                amount=Decimal("50000"),
                currency=CURRENCY,
                requested_on=date(2026, 1, 2),
            ),
            InvestorDocument(investor_id=investor.id, kind="piece_identite"),
            Deployment(
                project_id=project.id,
                bank_movement_id=money_out.id,
                amount=Decimal("8000"),
                currency=CURRENCY,
                deployed_on=date(2026, 1, 12),
            ),
            ProjectReturn(
                project_id=project.id,
                bank_movement_id=money_in.id,
                currency=CURRENCY,
                received_on=date(2026, 6, 1),
            ),
            ProjectValuation(
                project_id=project.id,
                valued_on=date(2026, 6, 30),
                amount=Decimal("9000"),
                currency=CURRENCY,
                valued_by="gerant@fonds-essai.fr",
            ),
        ]
    )
    colleague = await _account(db, MANAGER, firm, name="Ada Lovelace")
    db.add(UserTwoFactor(user_id=colleague.id, secret_encrypted="sealed"))
    await db.flush()
    return holder


def _listed(*users, erase_on: date = FIRST, access_until: str = ENDED_IN_SEPTEMBER):
    """Alice's list of the spaces to erase, naming `users`."""
    return patch(
        "app.services.alice_client.erasures_due",
        new=AsyncMock(
            return_value=[
                {
                    "manager_user_id": str(u.id),
                    "access_until": access_until,
                    "erase_on": erase_on.isoformat(),
                    "status": "scheduled",
                }
                for u in users
            ]
        ),
    )


def _licence(**kw) -> dict:
    """Alice's fresh answer for an ended licence whose erasure she schedules."""
    return {
        "is_blocked": True,
        "access_until": ENDED_IN_SEPTEMBER,
        "is_demo": False,
        "erasure_status": "scheduled",
        "erase_on": FIRST.isoformat(),
        **kw,
    }


def _on(day: date):
    """The platform's day and the holder's, both `day`."""
    stack = ExitStack()
    for name in ("platform_today", "holder_today"):
        stack.enter_context(
            patch.object(account_deletion_service, name, new=lambda *_a, _d=day: _d)
        )
    return stack


def _world(
    day: date, *users, answer=None, listed=True, told=True, sent=True, **list_kw
):
    stack = _on(day)
    stack.enter_context(_listed(*users, **list_kw) if listed else _listed())
    stack.enter_context(
        patch(
            "app.services.alice_client.fresh_licence",
            new=AsyncMock(return_value=answer if answer is not None else _licence()),
        )
    )
    stack.enter_context(
        patch(
            "app.services.alice_client.report_account_deleted",
            new=AsyncMock(return_value=told),
        )
    )
    stack.enter_context(
        patch(
            "app.services.mailer.send",
            new=AsyncMock(side_effect=None if sent else RuntimeError("smtp")),
        )
    )
    return stack


async def _run(db, day: date, *users, **kw) -> dict:
    with _world(day, *users, **kw):
        return await account_deletion_service.run_due(db)


async def _rows(db, user_id) -> list[AccountDeletion]:
    return list(
        (
            await db.execute(
                select(AccountDeletion).where(
                    AccountDeletion.user_id == user_id, AccountDeletion.kind == ENDED
                )
            )
        ).scalars()
    )


async def _alive(db, user_id) -> bool:
    return await db.get(User, user_id, populate_existing=True) is not None


async def _count(db, model, firm) -> int:
    """Rows of `model` in `firm`, read across firms (the test is nobody's)."""
    with firm_scope.all_firms():
        return int(
            (
                await db.execute(
                    select(func.count()).select_from(model).where(model.firm_id == firm)
                )
            ).scalar()
            or 0
        )


async def _team(db, firm) -> int:
    return int(
        (
            await db.execute(
                select(func.count()).select_from(User).where(User.firm_id == firm)
            )
        ).scalar()
        or 0
    )


async def _subscriptions(db, firm) -> int:
    with firm_scope.all_firms():
        return int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Subscription)
                    .join(Fund, Fund.id == Subscription.fund_id)
                    .where(Fund.firm_id == firm)
                )
            ).scalar()
            or 0
        )


# ── Nothing on an unknown state ─────────────────────────────────────────────────────


async def test_nothing_is_planned_when_alice_does_not_answer(db, platform_admin):
    holder = await _space(db)
    with (
        _on(FIRST + timedelta(days=1)),
        patch(
            "app.services.alice_client.erasures_due", new=AsyncMock(return_value=None)
        ),
    ):
        await account_deletion_service.run_due(db)

    assert await _rows(db, holder.id) == []


async def test_nothing_is_erased_when_alice_does_not_confirm_on_the_day(
    db, platform_admin
):
    holder = await _space(db)
    await _run(db, FIRST - timedelta(days=10), holder)

    with (
        _on(FIRST + timedelta(days=1)),
        _listed(holder),
        patch(
            "app.services.alice_client.fresh_licence", new=AsyncMock(return_value=None)
        ),
    ):
        done = await account_deletion_service.run_due(db)

    assert done["held"] == 1 and done["purged"] == 0
    assert await _alive(db, holder.id)


async def test_nothing_is_erased_when_alice_s_list_is_silent_on_the_day(
    db, platform_admin
):
    holder = await _space(db)
    await _run(db, FIRST - timedelta(days=10), holder)

    with (
        _on(FIRST + timedelta(days=1)),
        patch(
            "app.services.alice_client.erasures_due", new=AsyncMock(return_value=None)
        ),
        patch(
            "app.services.alice_client.fresh_licence",
            new=AsyncMock(return_value=_licence()),
        ),
    ):
        done = await account_deletion_service.run_due(db)

    assert done["held"] == 1 and done["purged"] == 0
    assert await _alive(db, holder.id)


async def test_nothing_is_erased_on_an_answer_that_lacks_the_day(db, platform_admin):
    holder = await _space(db)
    await _run(db, FIRST - timedelta(days=10), holder)

    done = await _run(
        db, FIRST + timedelta(days=1), holder, answer=_licence(erase_on=None)
    )

    assert done["purged"] == 0
    assert await _alive(db, holder.id)


async def test_nothing_is_erased_when_the_licence_is_not_ended(db, platform_admin):
    holder = await _space(db)
    await _run(db, FIRST - timedelta(days=10), holder)

    done = await _run(
        db, FIRST + timedelta(days=1), holder, answer=_licence(is_blocked=False)
    )

    assert done["purged"] == 0
    assert await _alive(db, holder.id)


# ── Nothing before the day ──────────────────────────────────────────────────────────


async def test_nothing_is_erased_before_the_day(db, platform_admin):
    holder = await _space(db)

    await _run(db, FIRST - timedelta(days=1), holder)

    assert await _alive(db, holder.id)
    assert await _count(db, Fund, holder.id) == 1


async def test_never_before_thirty_days_after_the_launch(db, platform_admin):
    # Alice naming an earlier day (a wrong answer) changes nothing: Invest reads its own.
    holder = await _space(db)

    await _run(db, FIRST - timedelta(days=20), holder, erase_on=date(2026, 11, 25))

    [row] = await _rows(db, holder.id)
    assert row.erase_on == FIRST


async def test_the_launch_day_is_the_one_the_shared_core_fixes():
    assert self_delete.ERASURE_LAUNCH_DAY == date(2026, 11, 20)
    assert FIRST == date(2026, 12, 20)


# ── Never a demonstration account, nor a platform one ───────────────────────────────


async def test_a_demonstration_account_is_never_erased(db, platform_admin):
    holder = await _space(db)
    await _run(db, FIRST - timedelta(days=10), holder)

    done = await _run(
        db, FIRST + timedelta(days=1), holder, answer=_licence(is_demo=True)
    )

    assert done["purged"] == 0
    assert await _alive(db, holder.id)


async def test_a_licence_that_does_not_say_demonstration_is_never_erased(
    db, platform_admin
):
    holder = await _space(db)
    await _run(db, FIRST - timedelta(days=10), holder)
    answer = _licence()
    del answer["is_demo"]

    done = await _run(db, FIRST + timedelta(days=1), holder, answer=answer)

    assert done["purged"] == 0
    assert await _alive(db, holder.id)


async def test_a_platform_account_is_never_planned(db, platform_admin):
    await _run(db, FIRST - timedelta(days=10), platform_admin)

    assert await _rows(db, platform_admin.id) == []


async def test_an_account_that_is_not_the_subscriber_is_never_planned(
    db, platform_admin
):
    holder = await _space(db)
    member = await _account(db, MANAGER, holder.id)

    await _run(db, FIRST - timedelta(days=10), member)

    assert await _rows(db, member.id) == []


async def test_a_platform_account_attached_to_the_firm_holds_the_erasure(
    db, platform_admin
):
    holder = await _space(db)
    await _account(db, ADMIN, holder.id)
    await _run(db, FIRST - timedelta(days=10), holder)

    done = await _run(db, FIRST, holder)

    assert done["held"] == 1 and done["purged"] == 0
    assert await _alive(db, holder.id)


# ── A new subscription, a postponement ──────────────────────────────────────────────


async def test_a_new_subscription_withdraws_the_erasure(db, platform_admin):
    holder = await _space(db)
    await _run(db, FIRST - timedelta(days=10), holder)

    await _run(db, FIRST - timedelta(days=9), listed=False)  # Alice no longer lists it
    done = await _run(db, FIRST + timedelta(days=1), listed=False)

    [row] = await _rows(db, holder.id)
    assert row.cancelled_at is not None and done["purged"] == 0
    assert await _alive(db, holder.id)


async def test_a_postponement_at_alice_moves_the_day(db, platform_admin):
    holder = await _space(db)
    later = FIRST + timedelta(days=90)

    done = await _run(db, FIRST + timedelta(days=1), holder, erase_on=later)

    [row] = await _rows(db, holder.id)
    assert row.erase_on == later and done["purged"] == 0
    assert await _alive(db, holder.id)


async def test_an_account_deleted_from_the_console_is_withdrawn_not_purged(
    db, platform_admin
):
    holder = await _space(db)
    await _run(db, FIRST - timedelta(days=10), holder)
    holder_id = holder.id
    await db.delete(holder)
    await db.flush()

    done = await _run(db, FIRST, listed=False)

    [row] = await _rows(db, holder_id)
    assert row.cancelled_at is not None and row.executed_at is None
    assert done["purged"] == 0
    assert await _count(db, Fund, holder_id) == 1


# ── The notice ──────────────────────────────────────────────────────────────────────


async def test_the_notice_leaves_seven_days_before_once(db, platform_admin):
    holder = await _space(db)
    sent = AsyncMock(return_value=None)
    with (
        _world(FIRST - timedelta(days=7), holder),
        patch("app.services.mailer.send", new=sent),
    ):
        first = await account_deletion_service.run_due(db)
        second = await account_deletion_service.run_due(db)

    assert (first["reminded"], second["reminded"]) == (1, 0)
    assert [c.kwargs["to"] for c in sent.await_args_list] == [holder.email]
    assert FIRST.strftime("%d/%m/%Y") in sent.await_args.kwargs["subject"]
    assert "/investors" in sent.await_args.kwargs["body"]


async def test_the_notice_speaks_the_holder_s_language(db, platform_admin):
    holder = await _space(db)
    holder.locale = "en"
    await db.flush()
    sent = AsyncMock(return_value=None)
    with (
        _world(FIRST - timedelta(days=7), holder),
        patch("app.services.mailer.send", new=sent),
    ):
        await account_deletion_service.run_due(db)

    assert sent.await_args.kwargs["subject"].startswith("Your data will be erased on")


async def test_a_notice_not_sent_is_tried_again(db, platform_admin):
    holder = await _space(db)

    failed = await _run(db, FIRST - timedelta(days=7), holder, sent=False)
    again = await _run(db, FIRST - timedelta(days=6), holder)

    assert (failed["notice_failed"], again["reminded"]) == (1, 1)


# ── The erasure itself ──────────────────────────────────────────────────────────────


async def test_the_space_is_erased_on_its_day(db, platform_admin):
    holder = await _space(db)
    await _run(db, FIRST - timedelta(days=10), holder)

    done = await _run(db, FIRST, holder)

    assert done["purged"] == 1
    assert not await _alive(db, holder.id)
    for model in (Fund, Investor, Project, BankMovement):
        assert await _count(db, model, holder.id) == 0, model
    assert await _team(db, holder.id) == 0


async def test_the_purge_leaves_no_row_of_any_table_of_the_firm(db, platform_admin):
    """Every table below the four that carry the firm is emptied of its rows too."""
    holder = await _space(db)
    before = {}
    models = (
        Contribution,
        Distribution,
        CapitalCall,
        SubscriptionConversion,
        SubscriptionRequest,
        Subscription,
        Deployment,
        ProjectReturn,
        ProjectValuation,
        InvestorDocument,
        UserTwoFactor,
    )
    with firm_scope.all_firms():
        for model in models:
            before[model] = (
                await db.execute(select(func.count()).select_from(model))
            ).scalar()
    await _run(db, FIRST - timedelta(days=10), holder)

    await _run(db, FIRST, holder)

    with firm_scope.all_firms():
        for model in models:
            after = (await db.execute(select(func.count()).select_from(model))).scalar()
            assert after < before[model], model


async def test_the_journal_counts_without_naming(db, platform_admin):
    holder = await _space(db)
    await _run(db, FIRST - timedelta(days=10), holder)

    await _run(db, FIRST, holder)

    journal = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.action == "account.erasure_executed",
                AuditLog.entity_id == str(holder.id),
            )
        )
    ).scalar_one()
    counts = journal.details["counts"]
    assert counts["funds"] == 1 and counts["investors"] == 1
    assert counts["subscriptions"] == 2 and counts["accounts"] == 3
    said = str(journal.details)
    assert holder.email not in said and "Meridian" not in said and "Hopper" not in said


async def test_alice_hears_of_it_with_the_cause_and_keeps_her_invoices(
    db, platform_admin
):
    """Alice is told through the door that keeps the invoices (`account-deleted`), with the
    cause and the numbers; Invest never asks her to delete a licence."""
    holder = await _space(db)
    await _run(db, FIRST - timedelta(days=10), holder)
    told = AsyncMock(return_value=True)
    with (
        _world(FIRST, holder),
        patch("app.services.alice_client.report_account_deleted", new=told),
    ):
        await account_deletion_service.run_due(db)

    assert told.await_args.args[0] == holder.id
    assert told.await_args.kwargs["cause"] == "subscription_ended"
    assert told.await_args.kwargs["counts"]["accounts"] == 3
    [row] = await _rows(db, holder.id)
    assert row.alice_told_at is not None


async def test_alice_unreachable_is_told_again_and_the_purge_never_runs_twice(
    db, platform_admin
):
    holder = await _space(db)
    await _run(db, FIRST - timedelta(days=10), holder)
    first = await _run(db, FIRST, holder, told=False)

    again = await _run(db, FIRST + timedelta(days=1), holder)

    assert (first["purged"], first["alice_to_tell"]) == (1, 1)
    assert (again["purged"], again["alice_told"]) == (0, 1)


async def test_only_the_subscriber_listed_is_erased_its_neighbour_is_intact(
    db, platform_admin
):
    neighbour = await _space(db, name="Voisin Partners")
    holder = await _space(db)
    await _run(db, FIRST - timedelta(days=10), holder)

    await _run(db, FIRST, holder)

    assert not await _alive(db, holder.id)
    assert await _alive(db, neighbour.id)
    for model in (Fund, Investor, Project, BankMovement):
        assert await _count(db, model, neighbour.id) >= 1, model
    assert await _subscriptions(db, neighbour.id) == 2
    assert await _team(db, neighbour.id) == 2


async def test_a_row_shared_with_another_space_holds_the_erasure(db, platform_admin):
    holder = await _space(db)
    neighbour = await _space(db, name="Voisin Partners")
    with firm_scope.all_firms():
        their_fund = (
            await db.execute(select(Fund).where(Fund.firm_id == neighbour.id))
        ).scalar_one()
        our_investor = (
            await db.execute(select(Investor).where(Investor.firm_id == holder.id))
        ).scalar_one()
    db.add(
        Subscription(
            fund_id=their_fund.id,
            investor_id=our_investor.id,
            instrument=instruments.EQUITY,
            amount=Decimal("1000"),
            currency=CURRENCY,
            signed_on=date(2026, 2, 1),
        )
    )
    await db.flush()
    await _run(db, FIRST - timedelta(days=10), holder)

    done = await _run(db, FIRST, holder)

    assert done["held"] == 1 and done["purged"] == 0
    assert await _alive(db, holder.id)


async def test_an_investor_account_of_another_firm_holds_the_erasure(
    db, platform_admin
):
    holder = await _space(db)
    stranger = await _account(db, INVESTOR, uuid.uuid4(), name="Ailleurs")
    with firm_scope.all_firms():
        our_investor = (
            await db.execute(select(Investor).where(Investor.firm_id == holder.id))
        ).scalar_one()
    our_investor.user_id = stranger.id
    await db.flush()
    await _run(db, FIRST - timedelta(days=10), holder)

    done = await _run(db, FIRST, holder)

    assert done["held"] == 1 and done["purged"] == 0


async def test_the_last_administrator_is_never_erased(db):
    holder = await _space(db)
    others = await db.execute(
        select(User).where(User.role.in_((ADMIN, MANAGER)), User.id != holder.id)
    )
    for other in others.scalars():
        other.is_active = False
    await db.flush()
    await _run(db, FIRST - timedelta(days=10), holder)

    done = await _run(db, FIRST, holder)

    assert done["held"] == 1 and await _alive(db, holder.id)


# ── What the holder reads ───────────────────────────────────────────────────────────


async def test_the_subscription_says_the_day_of_the_erasure(db, client, monkeypatch):
    from app.services import alice_client

    holder = await _account(db, MANAGER)
    later = FIRST + timedelta(days=60)
    ended = (datetime.now(UTC) - timedelta(days=5)).replace(tzinfo=None).isoformat()
    licence = _licence(access_until=ended, erase_on=later.isoformat())

    async def get_license(*_a, **_k):
        return licence

    monkeypatch.setattr(alice_client, "console_configured", lambda: True)
    monkeypatch.setattr(alice_client, "get_license", get_license)
    token = create_access_token(str(holder.id), holder.role)
    sub = await client.get(
        "/api/v1/billing", headers={"Authorization": f"Bearer {token}"}
    )

    assert sub.status_code == 200, sub.text
    assert sub.json()["erase_on"] == later.isoformat()


def test_a_space_ended_before_the_launch_reads_until_the_first_erasure():
    state = licence_state.read(_licence(), now=datetime(2026, 11, 21, tzinfo=UTC))

    assert state is not None and state.export_until is not None
    assert licence_state.platform_day(state.export_until) == FIRST - timedelta(days=1)
    assert state.erase_on == FIRST


def test_a_licence_alice_does_not_schedule_says_no_day():
    state = licence_state.read(_licence(erasure_status="unpaid", erase_on=None))

    assert state is not None and state.erase_on is None
