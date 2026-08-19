"""The vehicle: a fund grouping projects and subscribers.

🔴 EVERY EXISTING ROW STAYS UNATTACHED, AND THAT IS THE POINT. `fund_id` is nullable and
nothing is backfilled: inventing a vehicle to put the current projects in would assert a
structure nobody agreed, and every figure computed afterwards would rest on it. NULL is a
real scope — « the unattached pool », which is exactly what a crowdfunding vehicle is.

⚠️ SO THIS MIGRATION CHANGES NO BEHAVIOUR. The waterfall, the net asset value and the
performance all keep working on the unattached pool exactly as before, because that is where
every row is. A fund only starts to matter once somebody creates one.

⚠️ `ondelete="RESTRICT"` ON BOTH LINKS. Deleting a fund that still holds projects or
commitments would orphan money: the rows would fall back into the unattached pool and be
distributed to whoever is left there. The database refuses instead.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_funds"
down_revision: str | None = "0006_project_valuations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "funds",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="raising", nullable=False
        ),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("iban", sa.String(length=34), nullable=True),
        sa.Column("terms", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("opened_on", sa.Date(), nullable=True),
        sa.Column("closed_on", sa.Date(), nullable=True),
        sa.Column("mandate", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_funds_status", "funds", ["status"])
    op.create_index("ix_funds_currency", "funds", ["currency"])
    op.create_index("ix_funds_iban", "funds", ["iban"])

    for table in ("projects", "subscriptions"):
        op.add_column(table, sa.Column("fund_id", sa.UUID(), nullable=True))
        op.create_index(f"ix_{table}_fund_id", table, ["fund_id"])
        op.create_foreign_key(
            f"fk_{table}_fund_id", table, "funds", ["fund_id"], ["id"], ondelete="RESTRICT"
        )


def downgrade() -> None:
    for table in ("subscriptions", "projects"):
        op.drop_constraint(f"fk_{table}_fund_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_fund_id", table_name=table)
        op.drop_column(table, "fund_id")
    op.drop_index("ix_funds_iban", table_name="funds")
    op.drop_index("ix_funds_currency", table_name="funds")
    op.drop_index("ix_funds_status", table_name="funds")
    op.drop_table("funds")
