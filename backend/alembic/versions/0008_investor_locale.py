"""The language an investor is written to in, recorded on the investor and not only on a login.

🔴 MOST INVESTORS HAVE NO PORTAL ACCOUNT. `User.locale` already held the language somebody
picked in the switcher, which covers the ones who sign in. A capital call notice goes to
everybody, and `Investor.user_id` is nullable: without this column, the fund's only way to
write to an unregistered investor in their own language is to guess.

⚠️ AND NULL IS NOT « FRENCH », IT IS « THEY NEVER SAID ». That distinction is the whole reason
the column is nullable rather than defaulted. Nothing infers a language from
`country_code`: Belgium is French and Dutch, Switzerland French, German and Italian, Canada
French and English. A guess from a country is wrong for a whole nation of investors at a time,
and it is wrong silently - the letter goes out looking perfectly normal.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_investor_locale"
down_revision: str | None = "0007_funds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "investors",
        sa.Column(
            "locale",
            sa.String(length=5),
            nullable=True,
            comment=(
                "Language the fund writes to this investor in. NULL means they never "
                "stated one, which is not the same as French."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("investors", "locale")
