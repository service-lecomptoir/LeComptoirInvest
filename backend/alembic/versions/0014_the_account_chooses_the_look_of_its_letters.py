"""The account chooses the look of its letters.

`users.email_theme` holds a key of Alice's catalogue of e-mail looks
(`GET /internal/email-themes`). NULL means the product's own look, the default the console
sets for this product. See `app/services/email_themes.py`.

⚠️ EXISTING ROWS STAY NULL: nobody chose anything yet, and writing today's default would
freeze it, where NULL follows the console when its default changes.

⚠️ IDEMPOTENT: the column is added only when it is missing, so a replay on a schema that
already carries it is a no-op rather than a container that will not start.

Revision ID: 0014_the_account_chooses_the_look_of_its_letters
Revises: 0013_the_account_says_who_it_works_for
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_the_account_chooses_the_look_of_its_letters"
down_revision: str | None = "0013_the_account_says_who_it_works_for"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, name: str) -> bool:
    """⚠️ Looks in the CURRENT schema: `information_schema` covers every visible schema,
    and a probe answering for `public` while `op.*` works elsewhere skips the work."""
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
    if not _has_column("users", "email_theme"):
        op.add_column(
            "users", sa.Column("email_theme", sa.String(length=40), nullable=True)
        )


def downgrade() -> None:
    if _has_column("users", "email_theme"):
        op.drop_column("users", "email_theme")
