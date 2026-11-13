"""The DEFINITIVE erasure of a subscriber's firm: its funds, its register, its money, its team.

🔴 ONE PURGE, WRITTEN ONCE (the owner, 13 Nov 2026: the space of an ended subscription is
erased once its thirty days to export have run out, terms of sale 7.4). The daily job of
`account_deletion_service` runs it today; « Supprimer mon compte », when this product gets
the button, runs the same function, as Le Comptoir Immo's two doors share
`agency_purge.purge_agency`. docs/THE_SPACE_IS_ERASED_AFTER_THE_EXPORT_DAYS.md.

⚠️ NOT THE CONSOLE'S DELETION. `DELETE /internal/managers/{id}` removes the ACCOUNT alone
(its second factor goes by CASCADE, the investors it signed in for keep their record) and
leaves the firm's funds, register and money where they are: that route is left as it was,
and whether it should erase the firm too is the owner's to decide.

What goes, in one transaction the caller commits:

- every row of every table of the firm, leaves first (`PURGE_ORDER`): the four tables that
  carry it (`core.firm_scope.SCOPED_TABLES`: funds, investors, projects, bank movements),
  read off `firm_id`, and every table below them, read off its foreign keys to those four
  (subscriptions and their requests and conversions, capital calls, contributions,
  distributions, deployments, returns, valuations, the investors' KYC pieces);
- every account of the firm (colleagues and investor accounts, `users.firm_id`), with their
  second factor, then the holder.

What stays: the audit journal (its own retention, ninety days), the closed sessions
(`revoked_sessions`, an id and an expiry, gone by themselves), the `account_deletions` row
(no personal data), and at Alice every subscription invoice. No file: this product keeps
none on disk (its only volume is the database's; a statement is drawn on demand).

🔴 BULK DELETES, ON PURPOSE: the journal's listeners snapshot every row an ORM delete
removes (`core/audit.py`), which would copy the names, addresses and IBAN fingerprints
being erased into the journal. The erasure writes its own line instead, with numbers only.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import firm_scope
from app.models.base import Base
from app.models.two_factor import UserTwoFactor
from app.models.user import INVESTOR, MANAGER, User

#: 🔴 THE ORDER OF THE PURGE, LEAVES FIRST: a row is deleted before the rows it points to,
#: so a RESTRICT key (a contribution on its bank movement, a subscription on its fund) never
#: refuses. A guard compares this tuple to the whole schema: a table added tomorrow is
#: purged, kept on purpose (`KEPT`) or an account table (`ACCOUNT_TABLES`), or the suite
#: says so.
PURGE_ORDER: tuple[str, ...] = (
    "contributions",
    "distributions",
    "capital_calls",
    "subscription_conversions",
    "subscription_requests",
    "subscriptions",
    "deployments",
    "project_returns",
    "project_valuations",
    "investor_documents",
    "projects",
    "bank_movements",
    "investors",
    "funds",
)

#: The accounts of the firm, erased after its rows: the second factor, then the account.
ACCOUNT_TABLES: tuple[str, ...] = ("user_two_factors", "users")

#: Kept on purpose, never purged with a firm: the journal (its own retention), the closed
#: sessions (an id and an expiry, no account), the erasures themselves (no personal data).
KEPT: tuple[str, ...] = ("audit_logs", "revoked_sessions", "account_deletions")

#: The numbers the journals keep (never a name): table -> the word for it.
COUNTED: dict[str, str] = {
    "funds": "funds",
    "investors": "investors",
    "subscriptions": "subscriptions",
    "projects": "projects",
    "bank_movements": "bank_movements",
    "contributions": "contributions",
    "distributions": "distributions",
    "investor_documents": "investor_documents",
}


def _table(name: str):
    return Base.metadata.tables[name]


def owned(name: str) -> str:
    """The SQL condition, on the columns of table `name`, under which a row belongs to the
    firm bound as `:f`. A table that carries the firm reads its `firm_id`; any other table
    of `PURGE_ORDER` belongs through its foreign keys to the purged tables, ANY of them (a
    contribution through its bank movement OR its subscription). Built from the models'
    keys, never written by hand: a key added tomorrow is followed with the rest."""
    if name in firm_scope.SCOPED_TABLES:
        return "firm_id = :f"
    paths = [
        f"{fk.parent.name} IN (SELECT {fk.column.name} FROM {fk.column.table.name} "
        f"WHERE {owned(fk.column.table.name)})"
        for fk in sorted(_table(name).foreign_keys, key=lambda k: k.parent.name)
        if fk.column.table.name in PURGE_ORDER and fk.column.table.name != name
    ]
    # A table with no path to the firm would be purged by nobody: the guard refuses it.
    assert paths, f"{name} reaches no table that carries a firm"
    return "(" + " OR ".join(paths) + ")"


#: An account of the firm: the holder (who IS the firm) and every account attached to it.
_ACCOUNT_OF_FIRM = "COALESCE(firm_id, id) = :f"


def _accounts_of(firm: uuid.UUID):
    """The same accounts, as a clause of the ORM."""
    return func.coalesce(User.firm_id, User.id) == firm


async def shared_with_another_space(db: AsyncSession, firm: uuid.UUID) -> int:
    """How many links tie this firm's rows to ANOTHER firm's: a row of one side pointing to
    a row of the other, on every foreign key between the purged tables, and from an
    investor to the account that signs in for it (an account counts as its firm,
    `COALESCE(firm_id, id)`).

    🔴 ZERO IS THE ONLY ANSWER UNDER WHICH THE PURGE RUNS. A shared row would be erased for
    the neighbour too, or left dangling: the erasure is then held and someone looks."""
    total = 0
    for name in PURGE_ORDER:
        for fk in _table(name).foreign_keys:
            parent = fk.column.table.name
            if parent == "users":
                parent_owned = _ACCOUNT_OF_FIRM
            elif parent in PURGE_ORDER and parent != name:
                parent_owned = owned(parent)
            else:
                continue
            sql = (
                f"SELECT count(*) FROM {name} c JOIN {parent} p "
                f"ON c.{fk.parent.name} = p.{fk.column.name} "
                f"WHERE (c.id IN (SELECT id FROM {name} WHERE {owned(name)})) "
                f"<> (p.id IN (SELECT id FROM {parent} WHERE {parent_owned}))"
            )
            total += int((await db.execute(text(sql), {"f": firm})).scalar() or 0)
    return total


async def platform_accounts_in(db: AsyncSession, firm: uuid.UUID) -> int:
    """How many accounts of the firm are not a manager's or an investor's (the platform's
    administrator attached to a firm by mistake): never erased with it, the erasure holds."""
    rows = await db.execute(
        select(User.id).where(
            User.firm_id == firm, User.role.not_in((MANAGER, INVESTOR))
        )
    )
    return len(rows.all())


async def purge_firm(
    db: AsyncSession, holder: User, counts: dict | None = None
) -> dict[str, int]:
    """Erase the holder's firm and the holder. Does not commit: the caller commits.
    `counts`, when given, is filled with what was erased, in numbers only; the same numbers
    are returned."""
    firm = firm_scope.firm_of(holder)
    # Never reached by the job (it purges a licence holder only); a programming error.
    assert firm == holder.id, "purge_firm takes a firm's root account"
    numbers: dict[str, int] = {}
    for name in PURGE_ORDER:
        result = await db.execute(
            text(f"DELETE FROM {name} WHERE {owned(name)}"), {"f": firm}
        )
        if name in COUNTED:
            numbers[COUNTED[name]] = int(getattr(result, "rowcount", 0) or 0)
    accounts = select(User.id).where(_accounts_of(firm))
    await db.execute(
        delete(UserTwoFactor)
        .where(UserTwoFactor.user_id.in_(accounts))
        .execution_options(synchronize_session=False)
    )
    team = await db.execute(
        delete(User)
        .where(User.firm_id == firm, User.id != holder.id)
        .execution_options(synchronize_session=False)
    )
    await db.execute(
        delete(User)
        .where(User.id == holder.id)
        .execution_options(synchronize_session=False)
    )
    # The holder's object is gone from the database: out of the session too, so no later
    # flush of the caller tries to write it back.
    if holder in db:
        db.expunge(holder)
    numbers["accounts"] = 1 + int(getattr(team, "rowcount", 0) or 0)
    if counts is not None:
        counts.update(numbers)
    return numbers
