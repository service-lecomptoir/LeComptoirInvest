"""The erasure of a subscriber's space in Le Comptoir Invest: the product's glue around
`core.self_delete`.

🔴 AN ENDED SUBSCRIPTION, ERASED ONCE ITS THIRTY DAYS TO EXPORT HAVE RUN OUT (the owner,
13 Nov 2026, yes to the erasure after the thirty days; terms of sale 7.4, data processing
agreement 11). docs/THE_SPACE_IS_ERASED_AFTER_THE_EXPORT_DAYS.md.

- `core.self_delete` holds the rules every product shares (the calendar, the launch day);
  this module holds what is Invest's: who is the subscriber (`User.holds_the_licence`),
  whom to tell, and when; `firm_purge.purge_firm` holds what is erased.
- 🔴 ALICE DECIDES, INVEST CHECKS. A row is planned on Alice's list
  (`/internal/erasures`), at the later of her day and this product's own reading of the
  same end; on the day it is run only on her FRESH answer (never the cache) that the
  licence ended, is not a demonstration and has its day reached. Anything else HOLDS the
  erasure, says why in the journal, and asks again the next morning.
- The same rows, the same purge and the same door to Alice will serve « Supprimer mon
  compte » the day this product gets the button.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import email_envelope
from app.core import self_delete as core
from app.core.fund_time import platform_today, zone_for_country
from app.core.i18n import pick, use_lang
from app.models.account_deletion import ENDED, AccountDeletion
from app.models.audit_log import AuditLog
from app.models.user import FUND_WIDE_ROLES, User
from app.services.licence_state import platform_day

logger = logging.getLogger(__name__)

#: Who the journal says acted: not an account, the daily pass itself.
ACTOR = "account-erasure (scheduled)"

#: The journal's words (numbers and days only, never a name nor an address).
ERASURE_PLANNED = "account.erasure_planned"
ERASURE_WITHDRAWN = "account.erasure_withdrawn"
ERASURE_HELD = "account.erasure_held"
ERASURE_EXECUTED = "account.erasure_executed"

#: What Alice is told of each kind of erasure (`account-deleted`, `cause`).
CAUSE_BY_KIND = {ENDED: "subscription_ended"}

#: 🔴 WHERE THE NOTICE SENDS THE HOLDER. This product has NO page that exports a firm's
#: data (13 Nov 2026): the register of the investors is the nearest, the screen from which
#: the funds, the subscriptions and the treasury are read. The letter says « consult », never
#: « export », and promises no button the product does not have.
EXPORT_PATH = "/investors"

#: Any fixed number: it names this job's lock among the database's advisory locks (two
#: workers each start the loop, the first one works and the second one skips).
_LOCK_KEY = 13_112_026

#: The first pass waits after start, so a restart loop never hammers Alice.
FIRST_DELAY_SECONDS = 300
#: Then one pass a day: the erasure is counted in days.
SWEEP_SECONDS = 24 * 3600


def _day_words(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _journal(db: AsyncSession, action: str, user_id: uuid.UUID, details: dict) -> None:
    """A named line of the journal, written with the unit of work: the account by its id,
    the days and the numbers, never a name nor an address."""
    db.add(
        AuditLog(
            id=uuid.uuid4(),
            created_at=datetime.now(UTC),
            user_id=None,
            user_email=ACTOR,
            action=action,
            entity_type="user",
            entity_id=str(user_id),
            details=details,
            ip_address=None,
        )
    )


def holder_today(user: User) -> date:
    """The holder's own day, where the account says it stands (`country`, the platform's
    zone when unknown): with the platform's day, the erasure waits for the later one."""
    return datetime.now(ZoneInfo(zone_for_country(user.country))).date()


def _own_erase_on(ends: datetime) -> date:
    """This product's own reading of the day, from the end alone (`licence_state`)."""
    from app.services.licence_state import EXPORT_DAYS

    return core.ended_erase_on(platform_day(ends + timedelta(days=EXPORT_DAYS)))


def _listed(item: dict) -> tuple[uuid.UUID, date, datetime] | None:
    """One line of Alice's list, or None when any piece is missing or malformed."""
    from app.services.licence_state import ERASURE_DUE, _day, _instant

    try:
        uid = uuid.UUID(str(item.get("manager_user_id")))
    except (TypeError, ValueError):
        return None
    day, ends = _day(item.get("erase_on")), _instant(item.get("access_until"))
    if day is None or ends is None or item.get("status") not in ERASURE_DUE:
        return None
    return uid, day, ends


async def _pending_ended(db: AsyncSession) -> list[AccountDeletion]:
    return list(
        (
            await db.execute(
                select(AccountDeletion).where(
                    AccountDeletion.kind == ENDED,
                    AccountDeletion.executed_at.is_(None),
                    AccountDeletion.cancelled_at.is_(None),
                )
            )
        ).scalars()
    )


async def plan_ended(db: AsyncSession, done: dict) -> set[uuid.UUID] | None:
    """Alice's list of the spaces to erase, read once a day: a row per holder she
    schedules, at the later of her day and this product's own reading; a row she no longer
    lists is withdrawn (a new subscription, a plan changed, a licence reopened). Alice not
    answering plans and withdraws NOTHING. Never a demonstration account (Alice leaves it
    out, and the day itself asks again), never a platform account nor an account that is
    not the licence holder here. Returns the accounts Alice lists today (None when she did
    not answer): only those may be erased today."""
    from app.services import alice_client

    listed = await alice_client.erasures_due()
    if listed is None:
        logger.warning(
            "ended erasures: Alice did not answer, nothing planned nor withdrawn"
        )
        return None
    planned: dict[uuid.UUID, tuple[date, datetime]] = {}
    for item in listed:
        line = _listed(item)
        if line is not None:
            planned[line[0]] = (line[1], line[2])
    try:
        now = datetime.now(UTC)
        pending = {row.user_id: row for row in await _pending_ended(db)}
        for uid, row in pending.items():
            if uid in planned:
                continue
            row.cancelled_at = now
            done["withdrawn"] += 1
            _journal(
                db,
                ERASURE_WITHDRAWN,
                uid,
                {"kind": ENDED, "erase_on": _iso(row.erase_on)},
            )
        for uid, (alice_day, ends) in planned.items():
            user = await db.get(User, uid)
            if user is None or not user.holds_the_licence:
                continue
            day = max(alice_day, _own_erase_on(ends))
            row = pending.get(uid)
            if row is None:
                db.add(
                    AccountDeletion(
                        user_id=uid,
                        agency_id=uid,
                        account_role=user.role,
                        kind=ENDED,
                        requested_at=now,
                        erase_on=day,
                        access_until=ends,
                    )
                )
                done["planned"] += 1
                _journal(
                    db,
                    ERASURE_PLANNED,
                    uid,
                    {
                        "kind": ENDED,
                        "erase_on": day.isoformat(),
                        "ended": ends.isoformat(),
                    },
                )
            elif row.erase_on != day:
                # Alice moved the day (a postponement, a correction): a new notice for it.
                row.erase_on, row.access_until, row.reminded_at = day, ends, None
        await db.commit()
    except Exception:  # noqa: BLE001 - planning never stops the day's other work
        await db.rollback()
        done["failed"] += 1
        logger.exception("ended erasures: planning failed")
    return set(planned)


async def _others_can_administer(db: AsyncSession, user: User) -> bool:
    """Whether an active account outside this firm can still administer the installation
    once it is gone (the console's own deletion refuses the last one)."""
    others = await db.scalar(
        select(func.count())
        .select_from(User)
        .where(
            User.role.in_(FUND_WIDE_ROLES),
            User.is_active.is_(True),
            User.id != user.id,
            func.coalesce(User.firm_id, User.id) != user.id,
        )
    )
    return bool(others)


async def why_not_erase(
    db: AsyncSession, user: User, row: AccountDeletion, today: date
) -> str | None:
    """Why the space must NOT be erased now, or None when everything agrees: the account is
    the licence holder, Alice answers NOW (no cache) that the licence is not a
    demonstration, that it ended, and schedules a day; this product's own reading of the
    end gives a day too; the later of the two, like the row's, has come; nothing of the
    firm is shared with another one, no platform account hangs from it; and the
    installation keeps an administrator."""
    from app.services import alice_client, licence_state
    from app.services.firm_purge import platform_accounts_in, shared_with_another_space

    if not user.holds_the_licence:
        return "not_the_subscriber"
    state = licence_state.read(await alice_client.fresh_licence(user.id))
    if state is None:
        return "alice_unknown"
    if state.is_demo is not False:
        return "demo_or_unsaid"
    if not state.terminated or state.ends_at is None:
        return "not_ended"
    day = state.erase_on
    if day is None:
        return f"alice_{state.erasure_status or 'silent'}"
    if row.erase_on is None or not (
        core.is_due(today, day) and core.is_due(today, row.erase_on)
    ):
        return "not_due"
    if await shared_with_another_space(db, user.id):
        return "shared_with_another_space"
    if await platform_accounts_in(db, user.id):
        return "platform_account_in_the_firm"
    if not await _others_can_administer(db, user):
        return "last_administrator"
    return None


async def run_ended(
    db: AsyncSession, done: dict, listed: set[uuid.UUID] | None
) -> None:
    """The planned erasures: on or after the day (the platform's day AND the holder's,
    `holder_today`), the purge, only for an account Alice LISTS today (`listed`, None
    when her list did not come) and only when `why_not_erase` finds nothing; then Alice is
    told (`tell_alice`). Seven days before, the notice, once per day planned. Each row in
    its own transaction: one failing leaves the others."""
    from app.services.firm_purge import purge_firm

    for row in await _pending_ended(db):
        row_id = row.id  # read before a rollback expires the row
        try:
            if row.erase_on is None:
                continue
            user = await db.get(User, row.user_id)
            if user is None:
                # 🔴 DELETED FROM ALICE'S CONSOLE IN THE MEANTIME. Here that deletion takes
                # the ACCOUNT alone and leaves the firm's rows (`firm_purge`): with no holder
                # left to check, nothing is erased on its behalf. The row is withdrawn and
                # says why; what becomes of the rows left is the owner's to decide.
                row.cancelled_at = datetime.now(UTC)
                done["withdrawn"] += 1
                _journal(
                    db,
                    ERASURE_WITHDRAWN,
                    row.user_id,
                    {
                        "kind": ENDED,
                        "erase_on": _iso(row.erase_on),
                        "why": "account_deleted_from_the_console",
                    },
                )
                await db.commit()
                continue
            today = min(platform_today(), holder_today(user))
            if core.is_due(today, row.erase_on):
                reason = (
                    "alice_list_unknown"
                    if listed is None
                    else "not_listed"
                    if row.user_id not in listed
                    else await why_not_erase(db, user, row, today)
                )
                if reason is not None:
                    done["held"] += 1
                    _journal(
                        db,
                        ERASURE_HELD,
                        row.user_id,
                        {"kind": ENDED, "erase_on": _iso(row.erase_on), "why": reason},
                    )
                    await db.commit()
                    continue
                counts: dict = {}
                await purge_firm(db, user, counts)
                row.executed_at = datetime.now(UTC)
                row.counts = counts
                _journal(
                    db,
                    ERASURE_EXECUTED,
                    row.user_id,
                    {
                        "kind": ENDED,
                        "erase_on": row.erase_on.isoformat(),
                        "ran_on": today.isoformat(),
                        "counts": counts,
                    },
                )
                await db.commit()
                done["purged"] += 1
                if await tell_alice(db, row):
                    done["alice_told"] += 1
                else:
                    done["alice_to_tell"] += 1
            elif core.reminder_due(
                today, row.erase_on, already_reminded=row.reminded_at is not None
            ):
                if await send_erasure_notice(db, user, row.erase_on):
                    row.reminded_at = datetime.now(UTC)
                    await db.commit()
                    done["reminded"] += 1
                else:
                    # Not sent: asked again at the next pass, still before the day.
                    done["notice_failed"] += 1
        except Exception:  # noqa: BLE001 - one erasure failing leaves the others
            await db.rollback()
            done["failed"] += 1
            logger.exception("ended erasure %s failed", row_id)


def notice_letter(user: User, erase_on: date, url: str) -> email_envelope.Letter:
    """The whole notice, in the holder's language (`User.locale`), written like this
    product's other letters (the password link): there is no library of editable letters
    in Invest."""
    from app.config import get_settings

    product = get_settings().APP_NAME
    day = _day_words(erase_on)
    with use_lang(user.locale):
        name = (user.account_name or "").strip()
        greeting = (
            pick(f"Bonjour {name},", f"Hello {name},")
            if name
            else pick("Bonjour,", "Hello,")
        )
        title = pick(
            f"Vos données seront effacées le {day}",
            f"Your data will be erased on {day}",
        )
        paragraphs = [
            pick(
                f"Votre abonnement {product} a pris fin. Comme le prévoient nos "
                "conditions de vente, les données de votre espace seront effacées le "
                f"{day} : vos fonds et leurs projets, le registre de vos investisseurs "
                "et leurs pièces, les souscriptions, les appels de fonds, les versements, "
                "les distributions et les mouvements bancaires, ainsi que les comptes de "
                "votre équipe et de vos investisseurs.",
                f"Your {product} subscription has ended. As our terms of sale provide, "
                f"the data of your space will be erased on {day}: your funds and their "
                "projects, the register of your investors and their documents, the "
                "subscriptions, the capital calls, the contributions, the distributions "
                "and the bank movements, and the accounts of your team and of your "
                "investors.",
            ),
            pick(
                "D'ici là, vous pouvez les consulter depuis votre espace, avec le lien "
                "ci-dessous, et en garder copie. Pour garder votre espace, réabonnez-vous "
                "depuis « Mon abonnement ».",
                "Until then, you can read them in your space, with the link below, and "
                "keep a copy. To keep your space, subscribe again from « My "
                "subscription ».",
            ),
            pick(
                "Vos factures d'abonnement sont conservées dix ans, comme la loi "
                "l'impose.",
                "Your subscription invoices are kept ten years, as the law requires.",
            ),
        ]
        return email_envelope.Letter(
            title=title,
            brand=product,
            body="\n\n".join([greeting, *paragraphs]),
            signature=(pick("Cordialement,", "Kind regards,"), product),
            footer=pick(
                f"{product} · Ce message est automatique, merci de ne pas y répondre.",
                f"{product} · This message is automatic, please do not reply to it.",
            ),
            lang=user.locale or "fr",
            action=(pick("Ouvrir mon espace", "Open my space"), url),
        )


async def send_erasure_notice(db: AsyncSession, user: User, erase_on: date) -> bool:
    """Seven days before: the day, and where to read the data, in the holder's language,
    dressed in the firm's look. Never raises: False when not sent, and the next pass tries
    again (the row says once it left)."""
    from app.config import get_settings
    from app.services import email_themes, mailer

    url = get_settings().PUBLIC_APP_URL.rstrip("/") + EXPORT_PATH
    written = notice_letter(user, erase_on, url)
    try:
        look = await email_themes.look_for_firm(db, user.id)
        await mailer.send(
            to=user.email,
            subject=written.title + " · " + written.brand,
            body=written.text(),
            html=email_envelope.render(look, written),
        )
    except Exception as exc:  # noqa: BLE001 - reported as « not sent », tried again
        logger.warning("Erasure notice not sent (%s): %s", user.id, exc)
        return False
    return True


async def tell_alice(db: AsyncSession, row: AccountDeletion) -> bool:
    """Alice hears that the holder's space was purged (`report_account_deleted`, with the
    cause and the numbers): she stops the billing, purges the licence and writes the day on
    the invoices she KEEPS. Told, the row carries `alice_told_at`; refused or unreachable,
    it stays « Alice à prévenir » and the next pass tells her again. Never runs the purge."""
    from app.services import alice_client

    assert row.executed_at is not None
    if not await alice_client.report_account_deleted(
        row.user_id,
        deleted_on=platform_day(row.executed_at),
        cause=CAUSE_BY_KIND[row.kind],
        counts=row.counts,
    ):
        logger.warning("erasure %s: Alice still to be told", row.id)
        return False
    row.alice_told_at = datetime.now(UTC)
    await db.commit()
    return True


async def _tell_alice_what_she_missed(db: AsyncSession, done: dict) -> None:
    """The catch-up: every purge Alice has not heard of yet, told again (a failed call, or
    a pass stopped between the purge and the call)."""
    rows = list(
        (
            await db.execute(
                select(AccountDeletion).where(
                    AccountDeletion.executed_at.is_not(None),
                    AccountDeletion.alice_told_at.is_(None),
                )
            )
        ).scalars()
    )
    for row in rows:
        row_id = row.id
        try:
            if await tell_alice(db, row):
                done["alice_told"] += 1
            else:
                done["alice_to_tell"] += 1
        except Exception:  # noqa: BLE001 - one call failing leaves the others
            await db.rollback()
            done["alice_to_tell"] += 1
            logger.exception("erasure %s: telling Alice failed", row_id)


async def run_due(db: AsyncSession) -> dict:
    """One pass: Alice told of what she missed, the plan read from her list, then the
    erasures and notices whose day came."""
    done = {
        "planned": 0,
        "withdrawn": 0,
        "held": 0,
        "purged": 0,
        "reminded": 0,
        "notice_failed": 0,
        "failed": 0,
        "alice_told": 0,
        "alice_to_tell": 0,
    }
    await _tell_alice_what_she_missed(db, done)
    listed = await plan_ended(db, done)
    await run_ended(db, done, listed)
    return done


async def run_once() -> dict | None:
    """One pass under the job's lock, in sessions of its own; None when the other worker
    holds the lock. The lock lives on a connection of its own, held for the whole pass: the
    pass commits row by row, and a lock bound to one of those transactions would be gone at
    the first commit."""
    from app.database import AsyncSessionLocal, engine

    async with engine.connect() as lock:
        got = (
            await lock.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": _LOCK_KEY}
            )
        ).scalar()
        if not got:
            return None
        try:
            async with AsyncSessionLocal() as db:
                done = await run_due(db)
        finally:
            await lock.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_KEY})
            await lock.commit()
    if any(done.values()):
        logger.info("Erasures of ended subscriptions: %s", done)
    return done


async def run_forever() -> None:
    """The in-process schedule, the product's own (`audit_retention.run_forever`): a first
    pass a few minutes after start, then one a day. A failed pass is logged and the loop
    carries on: a day missed is caught up (`core.is_due` reads `>=`)."""
    await asyncio.sleep(FIRST_DELAY_SECONDS)
    while True:
        try:
            await run_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - logged, retried at the next pass
            logger.exception("Erasures of ended subscriptions: the pass failed")
        await asyncio.sleep(SWEEP_SECONDS)
