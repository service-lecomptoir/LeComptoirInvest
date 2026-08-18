"""Investor category, loss-bearing capacity, reflection period and risk acknowledgement.

🔴 FOUR COLUMNS THAT RECORD A PROTECTION, AND THEY ARE ALL NULLABLE ON PURPOSE. An investor
already in the register was never asked their category, and writing one for them would turn
a missing assessment into a recorded decision. `eligibility.is_protected` reads NULL as
PROTECTED, which is the safe direction: the failure mode of a protection must be « too much
protection », never « none ».

⚠️ SO THERE IS NO BACKFILL HERE, AND THAT IS THE WHOLE POINT. A migration that stamped
« retail » on every existing row would look tidy and would assert something nobody
established; one that stamped « professional » would silently lift the cap off everyone. The
column stays empty until a human answers the question.

⚠️ `loss_bearing_capacity` IS NUMERIC(18, 2), like every other amount in this schema. A
float would round a declared net worth, and the threshold is five per cent of it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_investor_eligibility"
down_revision: str | None = "0003_manager_postal_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("investors", sa.Column("category", sa.String(length=20), nullable=True))
    op.create_index("ix_investors_category", "investors", ["category"])
    op.add_column(
        "investors",
        sa.Column("loss_bearing_capacity", sa.Numeric(precision=18, scale=2), nullable=True),
    )
    op.add_column(
        "subscription_requests", sa.Column("reflection_ends_on", sa.Date(), nullable=True)
    )
    op.add_column(
        "subscription_requests", sa.Column("risk_acknowledged_on", sa.Date(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("subscription_requests", "risk_acknowledged_on")
    op.drop_column("subscription_requests", "reflection_ends_on")
    op.drop_column("investors", "loss_bearing_capacity")
    op.drop_index("ix_investors_category", table_name="investors")
    op.drop_column("investors", "category")
