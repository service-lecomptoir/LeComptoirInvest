"""The account says who it works for.

The console now sends a neutral `acts_for` (« self » or « clients ») instead of a
real-estate role, and this product keeps its own word for it in `users.account_kind`:
`single_fund` or `management_company`. See `app/core/account_kind.py`.

⚠️ EXISTING ROWS STAY NULL. Nobody ever told this product what those accounts are, and the
legacy role « gestionnaire » does not say it either: a value written here would be a guess
presented as a fact.

⚠️ IDEMPOTENT: the column is added only when it is missing, so a replay on a schema that
already carries it is a no-op rather than a container that will not start.

Revision ID: 0013_the_account_says_who_it_works_for
Revises: 0012_audit_journal
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_the_account_says_who_it_works_for"
down_revision: str | None = "0012_audit_journal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, name: str) -> bool:
    """⚠️ Looks in the CURRENT schema, and says so: `information_schema` covers every
    visible schema, and a probe answering for `public` while `op.*` works elsewhere skips
    the work in silence, which looks exactly like success."""
    return bool(
        op.get_bind().scalar(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": name},
        )
    )


def upgrade() -> None:
    if not _has_column("users", "account_kind"):
        op.add_column(
            "users", sa.Column("account_kind", sa.String(length=30), nullable=True)
        )


def downgrade() -> None:
    if _has_column("users", "account_kind"):
        op.drop_column("users", "account_kind")
