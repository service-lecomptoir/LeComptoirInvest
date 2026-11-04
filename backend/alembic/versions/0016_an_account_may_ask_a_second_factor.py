"""An account may ask a second factor: a TOTP code after the password (3 Nov 2026).

The owner, 2 Nov 2026: every account may switch on a second factor (a 6-digit code from an
authenticator app, RFC 6238), recommended to whoever runs the fund. One new table,
`user_two_factors`, one row per account that set it up: the encrypted secret, the moment
it was switched on, the last time step accepted, the fingerprints of the backup codes.

Nothing existing is touched, and nothing is switched on here. The downgrade drops it.

Revision ID: 0016_an_account_may_ask_a_second_factor
Revises: 0015_a_sign_out_closes_the_session
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0016_an_account_may_ask_a_second_factor"
down_revision: str | None = "0015_a_sign_out_closes_the_session"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_two_factors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_step", sa.BigInteger(), nullable=True),
        sa.Column("backup_codes_hashed", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("user_two_factors")
