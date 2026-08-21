"""Which management company the current request belongs to, and how that becomes a filter.

🔴 THE SCOPE IS INJECTED, NOT WRITTEN 68 TIMES. This product has sixty-eight `select()`
calls. Adding `.where(Fund.firm_id == ...)` to each of them would work on the day it is
done and leak on the first one somebody forgets — and the forgotten one is never the one
being reviewed. This repository's most expensive recurring defect is exactly that: a rule
applied at one site out of N.

So the filter is applied by SQLAlchemy itself, on every query touching a scoped table,
through `do_orm_execute` and `with_loader_criteria`. **A query that forgets the scope is
scoped anyway.** Adding an endpoint cannot open a leak; only removing this listener can,
and removing it fails a guard.

🔴 AND THE FAILURE MODE IS « SEE NOTHING », NEVER « SEE EVERYTHING ». If no firm has been
established — a background job, a code path nobody thought about — the criteria resolve to
a scope that matches no row. A protection whose default leans towards « none » is the only
kind worth having; the opposite is a leak that looks like a working screen.

⚠️ THE ONE DELIBERATE EXCEPTION IS NAMED, AND IT IS `/internal`. The console (Alice)
legitimately reads across firms: it counts what it bills and lists the accounts it
provisions. That is opened by `all_firms()`, explicitly, around the smallest possible
block — never by forgetting to set a scope.

⚠️ AND THE CONTEXT NEVER SURVIVES A REQUEST. It is a `ContextVar`, restored on the way out.
This product has already paid for a leaked ContextVar once (the reader's language), fixed
by an autouse fixture in the test suite; the same guard exists here.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

#: The four tables that CARRY the firm. Everything else derives it by join, so scoping
#: these four scopes the whole product.
#:
#: ⚠️ THIS TUPLE IS THE CONTRACT, and a guard compares it to the columns actually present
#: in the models: a table that gains `firm_id` without joining this list would be filtered
#: by nobody, and a table listed here without the column would raise on every query.
SCOPED_TABLES: tuple[str, ...] = ("funds", "investors", "projects", "bank_movements")

#: A scope that matches nothing. Used when no firm has been established, so the default is
#: « see nothing » rather than « see everything ».
NOBODY = uuid.UUID("00000000-0000-0000-0000-000000000000")

_current_firm: ContextVar[uuid.UUID | None] = ContextVar("current_firm", default=None)
_all_firms: ContextVar[bool] = ContextVar("all_firms", default=False)


def firm_of(user) -> uuid.UUID:
    """The firm an account belongs to.

    🔴 `COALESCE(firm_id, id)`, exactly as the sibling product scopes an agency. NULL means
    « this account IS the firm », so a lone account points at itself and needs no row of
    its own anywhere.
    """
    return user.firm_id or user.id


def set_current_firm(firm: uuid.UUID | None) -> None:
    """Set the management company for the rest of this request.

    ⚠️ WITHOUT RESTORING, and that is correct here: every FastAPI request runs in its own
    task, with its own copy of the context, so the value never crosses a request boundary.
    `use_firm` exists for the blocks that DO have to hand the context back: background jobs
    and tests.
    """
    _current_firm.set(firm)


@contextmanager
def use_firm(firm: uuid.UUID | None) -> Iterator[None]:
    """Run a block on behalf of one management company, then put the context back."""
    token = _current_firm.set(firm)
    try:
        yield
    finally:
        _current_firm.reset(token)


@contextmanager
def all_firms() -> Iterator[None]:
    """Read across every firm. THE ONLY EXCEPTION, AND IT HAS A NAME.

    🔴 RESERVED TO THE `/internal` CONTRACT, which the console calls to count what it bills
    and to list the accounts it provisions. Opening it anywhere else would hand a manager
    another firm's register, and the screen would look perfectly normal.

    ⚠️ It is a CONTEXT MANAGER and not a flag, so the exception has a visible end. A boolean
    set once and never cleared is how an exception becomes the rule.
    """
    token = _all_firms.set(True)
    try:
        yield
    finally:
        _all_firms.reset(token)


def set_unrestricted() -> None:
    """Read across every firm for the rest of this request. THE ONE EXCEPTION.

    🔴 RESERVED TO THE `/internal` CONTRACT, and reachable only by presenting the
    console's key. Everywhere else, a query is filtered to one firm whether its author
    thought about it or not.

    ⚠️ LIKE THE FIRM ITSELF, it is a ContextVar of the request's own task and does not
    cross a request boundary. `all_firms()` is the block form, for jobs and tests that must
    hand the context back.
    """
    _all_firms.set(True)


def current_firm() -> uuid.UUID:
    """The firm in force, or a scope that matches nothing."""
    return _current_firm.get() or NOBODY


def is_unrestricted() -> bool:
    return _all_firms.get()


def _criteria_for(entity, firm: uuid.UUID):
    """The filter applied to one scoped entity, at query time.

    ⚠️ THE FIRM IS RESOLVED OUTSIDE THE LAMBDA, and SQLAlchemy insists on it: a lambda
    criteria is cached by its code object and its bound values are extracted WITHOUT being
    called. A `current_firm()` call inside would either be refused (as it is) or, worse in
    another version, be evaluated once and then frozen -- serving the first caller's firm to
    everybody afterwards. Closing over a plain value is what makes the cache safe.
    """
    return with_loader_criteria(
        entity,
        lambda cls: cls.firm_id == firm,
        # ⚠️ INCLUDING RELATIONSHIP LOADS. Without this, `fund.projects` would load a
        # neighbour's projects through a relationship, having passed the scoped query that
        # found the fund. The leak would be one attribute access away from every screen.
        include_aliases=True,
    )


#: The entities the scope was actually installed on, recorded so a guard can compare them
#: to `SCOPED_TABLES`. Without this, the tuple above would be a comment: a rule written and
#: applied nowhere is this repository's other named defect.
_installed: tuple = ()


def installed_tables() -> tuple[str, ...]:
    """The tables the scope is actually filtering, as the listener sees them."""
    return tuple(sorted(entity.__tablename__ for entity in _installed))


def install(scoped_entities) -> None:
    """Teach SQLAlchemy to scope every query on the four roots.

    ⚠️ CALLED ONCE, AT IMPORT OF THE MODELS. Installing it per session would leave the
    first query of a fresh session unscoped, which is the query that fills a screen.
    """
    global _installed
    _installed = tuple(scoped_entities)

    @event.listens_for(Session, "do_orm_execute")
    def _scope(orm_execute_state):
        if not orm_execute_state.is_select or orm_execute_state.is_column_load:
            return
        if is_unrestricted():
            return
        firm = current_firm()
        for entity in scoped_entities:
            orm_execute_state.statement = orm_execute_state.statement.options(
                _criteria_for(entity, firm)
            )

    stamped = tuple(scoped_entities)

    @event.listens_for(Session, "before_flush")
    def _stamp(session, _flush_context, _instances):
        """Every new row of a SCOPED table gets the current firm, without being asked.

        🔴 STAMPED HERE AND NOT AT EACH CALL SITE, for the same reason the filter is
        injected: a row written without a firm belongs to nobody, is visible to nobody, and
        is found again only by somebody reading the table by hand. The screen that created
        it would show it disappearing.

        🔴 AND ONLY THE FOUR SCOPED ENTITIES, NEVER `User`. The account table carries a
        `firm_id` too, and it means something ELSE there: NULL is « this account IS the
        firm ». Stamping it would attach every account created under a firm to that firm,
        including the one being created to BE a new firm -- which then resolves its own
        scope to its creator's and reads their register. Measured on 21 August: a manager
        account minted inside a firm context came back owning the wrong company, and the
        isolation guard that caught it was reading its own fixture's firm.
        """
        if is_unrestricted():
            return
        firm = _current_firm.get()
        if firm is None:
            return
        for instance in session.new:
            if isinstance(instance, stamped) and instance.firm_id is None:
                instance.firm_id = firm


def owns(row) -> bool:
    """Does the current firm own this row?

    🔴 FOR THE PLACES WHERE A CALLER NAMES AN OBJECT BY ID, and only those. The injected
    filter covers queries; it does NOT cover `Session.get()` when the object is already in
    the identity map, because then no query is issued at all. A route that accepts an
    identifier must therefore ask this question out loud.

    ⚠️ AND A ROW WITH NO FIRM BELONGS TO NOBODY, so it is refused rather than shared. Rows
    that predate the isolation were attached by migration 0010; one that appears without a
    firm is a write that escaped the stamp, and handing it to whoever asks would be the
    worst possible reading of « we do not know ».
    """
    firm = getattr(row, "firm_id", None)
    return firm is not None and firm == current_firm()
