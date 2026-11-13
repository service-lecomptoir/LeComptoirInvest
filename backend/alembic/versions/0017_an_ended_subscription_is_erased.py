"""The space of an ended subscription is erased after its thirty days to export (the owner,
13 Nov 2026).

One new table, `account_deletions`, one row per erasure planned: the holder's id, the firm,
the days (planned, notice, withdrawn, executed, Alice told) and what the purge erased in
numbers. No foreign key to `users`: the row outlives the account it names.

Idempotent: the table and its indexes are created only when missing, no row is written and
nothing is erased here. The downgrade drops the table.
docs/THE_SPACE_IS_ERASED_AFTER_THE_EXPORT_DAYS.md.

Revision ID: 0017_an_ended_subscription_is_erased
Revises: 0016_an_account_may_ask_a_second_factor
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017_an_ended_subscription_is_erased"
down_revision: str | None = "0016_an_account_may_ask_a_second_factor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS account_deletions (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL,
            agency_id UUID,
            account_role VARCHAR(40) NOT NULL,
            kind VARCHAR(12) NOT NULL,
            requested_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            erase_on DATE,
            reminded_at TIMESTAMP WITH TIME ZONE,
            cancelled_at TIMESTAMP WITH TIME ZONE,
            executed_at TIMESTAMP WITH TIME ZONE,
            alice_told_at TIMESTAMP WITH TIME ZONE,
            access_until TIMESTAMP WITH TIME ZONE,
            counts JSONB
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_account_deletions_user_id "
        "ON account_deletions (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_account_deletions_agency_id "
        "ON account_deletions (agency_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS account_deletions")
