"""A sign-out closes the session on the server: `revoked_sessions`.

« Déconnexion » used to clear the browser only. The token stayed good on the server for the
rest of its lifetime, so a copy of it (a shared computer, a stolen browser profile) kept
opening the account after the person had signed out. Each token now carries the id of its
sign-in, and signing out writes that id here.

Revision ID: 0015_a_sign_out_closes_the_session
Revises: 0014_the_account_chooses_the_look_of_its_letters
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_a_sign_out_closes_the_session"
down_revision: str | None = "0014_the_account_chooses_the_look_of_its_letters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "revoked_sessions",
        sa.Column("sid", sa.String(64), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_revoked_sessions_expires_at", "revoked_sessions", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_revoked_sessions_expires_at", table_name="revoked_sessions")
    op.drop_table("revoked_sessions")
