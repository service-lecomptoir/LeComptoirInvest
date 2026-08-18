"""Manager postal identity, pushed down by Alice.

🔴 THESE COLUMNS EXIST BECAUSE ALICE SENDS THEM, AND A SCHEMA THAT DOES NOT NAME A FIELD
DROPS IT IN SILENCE. The sister product learnt that the expensive way: a Pydantic model
quietly swallowed `real_charges`, and the consequence surfaced in production as NaN. When
the console pushes an address down and the product has nowhere to put it, nothing fails —
the invoice simply goes out with an empty recipient, months later.

⚠️ WHAT IS DELIBERATELY ABSENT. Alice also sends `owner_kind`, `owner_account_name`,
`owner_company` and `owner_national_id`: the LANDLORD identity of a manager who is also an
owner. A fund has no landlord. Those four are named in the API schema and explicitly not
stored, so the omission is a decision somebody can read rather than a field that vanished.

Revision ID: 0003_manager_postal_identity
Revises: 0002_projects
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_manager_postal_identity"
down_revision: str | None = "0002_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("phone", sa.String(length=30)),
    ("address", sa.Text()),
    ("zip_code", sa.String(length=20)),
    ("city", sa.String(length=120)),
    ("country", sa.String(length=80)),
)


def upgrade() -> None:
    # ⚠️ Unqualified `to_regclass`-style idempotence, never `public.users`. A hard-coded
    # schema is what silently skipped thirteen renames in the sister product and killed its
    # migration chain fifty-two revisions later; the test schema is NOT `public`.
    for name, kind in _COLUMNS:
        op.add_column("users", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        op.drop_column("users", name)
