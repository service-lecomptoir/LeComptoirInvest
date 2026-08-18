"""What a late capital call costs, and when it was last chased.

🔴 THE RATE BELONGS TO THE CALL, NOT TO A SETTING. The notice an investor receives states
the late-payment rate; a fund-wide parameter changed six months later would rewrite what
they were told, retroactively, for every call already out. Storing it on the row means a
call keeps the terms it was issued under, which is also the only version anybody can be held
to.

⚠️ NULL MEANS NO LATE INTEREST ON THIS CALL, and it is a decision rather than an omission.
A default of zero would say the same thing while looking like a value somebody entered, and
the day the default changed every silent row would change with it.

⚠️ `last_reminded_on` IS NOT `notified_on`. The first notice and the latest reminder are two
facts: overwriting one with the other would lose the ability to say whether an investor was
ever told at all — and a reminder for a notice that was never sent blames them for the
fund's own omission.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_late_calls"
down_revision: str | None = "0004_investor_eligibility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "capital_calls", sa.Column("late_interest_rate", sa.Float(), nullable=True)
    )
    op.add_column(
        "capital_calls", sa.Column("last_reminded_on", sa.Date(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("capital_calls", "last_reminded_on")
    op.drop_column("capital_calls", "late_interest_rate")
