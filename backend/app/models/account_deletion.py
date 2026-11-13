"""The erasure of a subscriber's space, one row per erasure planned.

🔴 THE SAME TABLE AS EVERY PRODUCT OF THE HOUSE (`account_deletions`, Le Comptoir Immo's
shape): the day the space is erased once the subscription has ENDED and its thirty days to
export have run out (terms of sale 7.4; the owner, 13 Nov 2026), and tomorrow the day of
« Supprimer mon compte » on the same rows.
docs/THE_SPACE_IS_ERASED_AFTER_THE_EXPORT_DAYS.md.

The row is kept AFTER the space is gone: the proof of what was planned, when, and what
followed (GDPR art. 5.2). It therefore holds no foreign key to `users` (the holder's row
goes with the purge) and no personal data: the account's id, its role and firm, the days,
and what the purge erased in numbers only.

⚠️ `agency_id`, NOT `firm_id`, on purpose: the house's name for the column, and a column
named `firm_id` would make this table a SCOPED one (`core/firm_scope`), filtered to the
reader's firm and stamped with it; the daily job reads every firm's rows.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk

#: Nobody asked: the subscription ENDED and its thirty days to export ran out. Planned on
#: Alice's day, withdrawn when she no longer schedules it, run only on her fresh answer.
ENDED = "ended"


class AccountDeletion(Base):
    __tablename__ = "account_deletions"

    id: Mapped[uuid.UUID] = uuid_pk()
    #: The licence holder whose space is erased.
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    #: The firm (`firm_of` the holder: the holder's own id).
    agency_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )
    account_role: Mapped[str] = mapped_column(String(40), nullable=False)
    #: ENDED (« Supprimer mon compte » will add its own kind).
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    erase_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: When the notice left, seven days before; emptied when Alice moves the day.
    reminded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Withdrawn: Alice no longer lists the space (a new subscription, a plan changed).
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: When Alice heard of the purge (`/internal/license/{id}/account-deleted`). Empty on an
    #: executed row = « Alice à prévenir »: the next pass tells her again, and never runs
    #: the purge twice.
    alice_told_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: When the paid access ended at Alice (`access_until`).
    access_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: What the purge erased, in numbers only (accounts, funds, investors, subscriptions,
    #: bank movements...): the audit logs of Invest and Alice keep them, never a name.
    counts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<AccountDeletion {self.kind} {self.user_id}>"
