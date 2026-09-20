"""The audit journal: who changed what, written as the unit of work passes.

🔴 EVERY PRODUCT OF THE HOUSE KEEPS ONE (the manager, 20 Sept 2026: « à ajouter,
toujours ajouter », for every new product). This product went to production without: three
products did, and the supervision (Portail360) had nothing to show for them. The journal
is part of the foundation, like sign-in and the four languages, not a later refinement.

🔴 LISTENERS, NOT CALLS SPRINKLED IN THE ROUTES. A call has to be remembered by whoever
writes the next route, and the journal then holds what people thought of. A listener on
the unit of work sees every row the ORM writes, including the routes not written yet.

🔴 THE ACTOR COMES FROM A CONTEXT VARIABLE, AND IT MUST BE PUT BACK. A `ContextVar` set and
never reset leaks from one request into the next: the journal would then attribute a
manager's change to the previous account. Paid for on a sister product, and only visible
when somebody reads the journal months later.

⚠️ FAIL-SAFE, ALWAYS. A journal that breaks the operation it observes is worse than no
journal: every failure here is logged and swallowed.

⚠️ WHAT THIS MODULE DOES NOT SEE: bulk `UPDATE` and `DELETE` statements, which do not go
through the unit of work. Said here rather than promised wrongly.
"""

from __future__ import annotations

import contextvars
import logging
from datetime import UTC, datetime

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.core import audit_rules

logger = logging.getLogger(__name__)

_actor: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "audit_actor", default=None
)


def set_actor(*, user_id=None, user_email=None, ip=None):
    """Sets the actor of the current request. Returns the TOKEN that puts it back."""
    return _actor.set(
        {
            "user_id": str(user_id) if user_id else None,
            "user_email": user_email,
            "ip": ip,
        }
    )


def reset_actor(token) -> None:
    try:
        _actor.reset(token)
    except (ValueError, RuntimeError):
        # Another context's token, or one already spent: emptying beats a 500, and beats
        # letting the previous actor stamp what follows.
        _actor.set(None)


def identify(*, user_id, user_email) -> None:
    """Adds the identity to the actor already set, WITHOUT losing the address the
    middleware put there. Called where the account is already loaded."""
    current = dict(_actor.get() or {})
    current["user_id"] = str(user_id) if user_id else None
    current["user_email"] = user_email or None
    _actor.set(current)


def current_actor() -> dict:
    return _actor.get() or {}


def _table_of(instance) -> str:
    return getattr(type(instance), "__tablename__", "")


def _snapshot(instance) -> dict:
    state = inspect(instance)
    return {
        attribute.key: audit_rules.masked(
            attribute.key, getattr(instance, attribute.key, None)
        )
        for attribute in state.mapper.column_attrs
    }


def _changes(instance) -> dict:
    """What really changed, old value included. A save that changes nothing, or only the
    columns that move on their own, is not an event."""
    state = inspect(instance)
    out = {}
    for attribute in state.mapper.column_attrs:
        column = attribute.key
        history = state.attrs[column].history
        if not history.has_changes():
            continue
        before = history.deleted[0] if history.deleted else None
        after = history.added[0] if history.added else None
        if before == after:
            continue
        out[column] = {
            "old": audit_rules.masked(column, before),
            "new": audit_rules.masked(column, after),
        }
    if out and all(column in audit_rules.NOISE for column in out):
        return {}
    return out


def _entry(action: str, instance, details: dict) -> dict:
    import uuid

    actor = current_actor()
    identifier = getattr(instance, "id", None)
    return {
        "id": uuid.uuid4(),
        "created_at": datetime.now(UTC),
        "user_id": actor.get("user_id"),
        "user_email": actor.get("user_email"),
        "action": action,
        "entity_type": _table_of(instance),
        "entity_id": str(identifier) if identifier is not None else None,
        "details": details,
        "ip_address": actor.get("ip"),
    }


def _collect(session: Session) -> list[tuple]:
    """The journal lines of this flush, BEFORE the ORM applies it: a deletion read after
    the flush has lost its values, and the journal would say « something was deleted »."""
    entries = []
    for instance in session.new:
        table = _table_of(instance)
        # A row that ARRIVES BY IMPORT is not somebody's act (see `audit_rules.IMPORTED`);
        # what a person does to it afterwards is.
        if audit_rules.is_audited(table) and table not in audit_rules.IMPORTED:
            entries.append(
                (audit_rules.CREATE, instance, {"snapshot": _snapshot(instance)})
            )
    for instance in session.dirty:
        if not audit_rules.is_audited(_table_of(instance)):
            continue
        changed = _changes(instance)
        if changed:
            entries.append((audit_rules.UPDATE, instance, {"changes": changed}))
    for instance in session.deleted:
        if audit_rules.is_audited(_table_of(instance)):
            entries.append(
                (audit_rules.DELETE, instance, {"snapshot": _snapshot(instance)})
            )
    return entries


_installed = False


def install() -> None:
    """Plugs the listeners on every session. Idempotent: the application module is
    imported more than once under the test runner, and two sets of listeners would write
    every line twice."""
    global _installed
    if _installed:
        return
    _installed = True

    @event.listens_for(Session, "before_flush")
    def _remember(session: Session, _context, _instances) -> None:
        try:
            pending = _collect(session)
        except Exception:  # noqa: BLE001 - the journal never breaks the operation
            logger.warning("[audit] could not collect", exc_info=True)
            return
        if pending:
            session.info.setdefault("audit_pending", []).extend(pending)

    @event.listens_for(Session, "after_flush")
    def _write(session: Session, _context) -> None:
        pending = session.info.pop("audit_pending", None)
        if not pending:
            return
        from app.models.audit_log import AuditLog

        try:
            # ⚠️ `bulk_insert_mappings` RATHER THAN `session.add`: adding objects inside an
            # `after_flush` starts another flush, hence the listeners, hence the audit of
            # the audit. The direct insert cuts the loop. A created row has its id by now,
            # which is why the entry is BUILT here and only collected before.
            session.bulk_insert_mappings(
                AuditLog,
                [
                    _entry(action, instance, details)
                    for action, instance, details in pending
                ],
            )
        except Exception:  # noqa: BLE001 - never blocking, that is the module's promise
            logger.warning("[audit] could not write", exc_info=True)


def client_address(request) -> str:
    """Where the request came from: the LAST hop of `X-Forwarded-For` (the one the edge
    proxy wrote, the only one a caller cannot forge), else the socket's peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else "unknown"


__all__ = [
    "client_address",
    "current_actor",
    "identify",
    "install",
    "reset_actor",
    "set_actor",
]
