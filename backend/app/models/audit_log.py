"""One line of the audit journal: who did what, to which row, from where, and when.

The shape is the house's contract, the one the supervision (Portail360) reads from every
product: `created_at`, `user_id`, `user_email`, `action`, `entity_type`, `entity_id`,
`details`, `ip_address`. A product that named its columns otherwise would need its own
reader, and the journal exists precisely so that one screen shows them all.

⚠️ NO FOREIGN KEY TO `users`, ON PURPOSE. The line « this account was deleted » has to
outlive the account, and a cascade would erase the very trace it was written for.

⚠️ NO `firm_id`, so the per-firm scope does not apply: the journal is read by the
supervision, across firms, behind the internal key alone. No screen of the product
reads it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
