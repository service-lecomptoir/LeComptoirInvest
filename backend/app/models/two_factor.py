"""The second factor of an account (TOTP, RFC 6238), one row per account that set it up.

A table of its own rather than four columns on `users`: the factor is read at sign-in and
in the « Sécurité » section only, never by the queries that load an account, and the same
table, under the same name, carries it in every product of Le Comptoir.

- `secret_encrypted`: the TOTP secret, encrypted by `core/crypto` (the data keyring that
  already encrypts the investors' bank details, walked by `services/reencrypt`);
- `enabled_at`: NULL while the set-up waits for its first valid code, then the moment it
  was switched on (the factor counts only from then on);
- `last_step`: the last time step accepted, so that no code is accepted twice;
- `backup_codes_hashed`: the keyed fingerprints of the backup codes left (never in clear).

⚠️ NO `firm_id`, like `users`: the row belongs to an account, which is what DECIDES the
management company. It is read by the account's id, never listed across accounts.

⚠️ LEFT OUT OF THE GENERIC JOURNAL (`core/audit_rules.NEVER_AUDITED`): its events are
written by name, `two_factor.*`, never a code; the columns would be masked anyway by
their names (« secret », « hash »).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class UserTwoFactor(Base, TimestampMixin):
    __tablename__ = "user_two_factors"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    enabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    backup_codes_hashed: Mapped[list | None] = mapped_column(JSONB, nullable=True)
