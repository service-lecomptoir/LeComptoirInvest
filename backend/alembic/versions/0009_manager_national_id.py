"""The management company's registration number, on the account Alice provisions.

🔴 IT WAS ASKED FOR NOWHERE AND STORED NOWHERE. The console's « new fund manager » form
collects a company name, an e-mail and an address, and no registration number — while the
sibling products all collect one, verify its check digit, and look the company up in the
public register. A fund's management company is precisely the kind of counterparty whose
identity a fund's own records should carry.

⚠️ IT IS NOT `owner_national_id`, AND THE DISTINCTION IS NOT COSMETIC. Alice already sends
a landlord identity down to every product (`owner_kind`, `owner_company`,
`owner_national_id`) and this one declares it as received-and-not-kept: a fund has no
landlord. THIS column is the identity of the management company itself, the entity that
signs the subscription to the software and appears on its invoices. Storing one in the
other's column would have put a landlord's number on a fund's record.

⚠️ NULLABLE, AND IT STAYS NULLABLE. Accounts exist already, created before this column;
and a management company outside France has a registration number of another shape, or the
operator simply does not have it to hand at creation time. A NOT NULL here would have made
the console unable to provision an account it can provision today.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_manager_national_id"
down_revision: str | None = "0008_investor_locale"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "national_id",
            # 40 rather than 14: a SIREN is 9 digits and a SIRET 14, but this product is
            # not French-only. A German HRB number, a UK company number and a Luxembourg
            # RCS all fit differently, and a column too narrow refuses an account rather
            # than truncating a number, which is the right failure and still a failure.
            sa.String(length=40),
            nullable=True,
            comment=(
                "Registration number of the MANAGEMENT COMPANY that holds this account "
                "(SIREN/SIRET in France). Not a landlord identity: a fund has none."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "national_id")
