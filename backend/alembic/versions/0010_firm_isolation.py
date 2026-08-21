"""Which management company owns what. The column this product never had.

🔴 THIS PRODUCT WAS SINGLE-TENANT BY CONSTRUCTION, AND NOTHING SAID SO. There was no
owner column anywhere: not on a fund, not on a project, not on an investor. Every manager
account of an installation therefore saw the WHOLE register — every investor's KYC file,
IBAN and subscriptions — and that was not a bug in the sense of code disagreeing with a
design. It WAS the design, and it only became visible when a second manager account
appeared and its holder recognised somebody else's projects on their screen.

⚠️ THE SIBLING PRODUCT HAS ALWAYS ISOLATED. Le Comptoir Immo scopes by agency, with
invariants and guards of its own. Invest was the outlier, and it sells to fund management
companies through the same console: the day Alice provisions a second real firm, it would
read the first one's investors.

🔴 FOUR TABLES CARRY THE COLUMN, NOT FOURTEEN. The others derive it by join, and that is
deliberate: a column repeated on every table is fourteen chances to forget to stamp it, and
the one that is forgotten is a row nobody can attribute afterwards.

  * `funds`          — a vehicle belongs to the firm that runs it
  * `investors`      — the register belongs to the firm that keeps it
  * `projects`       — because `fund_id` is NULLABLE: a project without a fund would have
                       no firm to derive, and would then belong to everybody
  * `bank_movements` — the treasury has no parent at all, and it is the money

`users.firm_id` defines the scope itself, exactly as Immo's `agency_id` does: NULL means
« this account IS a firm », so the scope is `COALESCE(firm_id, id)` and a lone account
points at itself.

⚠️ NULLABLE, AND BACKFILLED. Existing rows predate the notion. They are attached to the
OLDEST manager account, which on any real installation is the firm that created them. A
NOT NULL from the start would have refused to migrate a database that has data.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_firm_isolation"
down_revision: str | None = "0009_manager_national_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The four roots. Everything else hangs off one of them by foreign key.
ROOTS: tuple[str, ...] = ("funds", "investors", "projects", "bank_movements")


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "firm_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
            comment=(
                "The management company this account belongs to. NULL means the account "
                "IS the firm: the scope is COALESCE(firm_id, id)."
            ),
        ),
    )
    op.create_index("ix_users_firm_id", "users", ["firm_id"])

    for table in ROOTS:
        op.add_column(
            table,
            sa.Column(
                "firm_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                nullable=True,
                comment="The management company that owns this row.",
            ),
        )
        # 🔴 INDEXED, BECAUSE EVERY SINGLE QUERY WILL CARRY IT. The scope is injected into
        # every read of these tables; an unindexed column there is a sequential scan on the
        # busiest predicate of the product.
        op.create_index(f"ix_{table}_firm_id", table, ["firm_id"])

    # ── Le rattachement des lignes existantes ────────────────────────────────
    #
    # ⚠️ AU COMPTE GESTIONNAIRE LE PLUS ANCIEN, et pas au premier venu. Sur une
    # installation réelle, c'est le compte de la société qui a créé ces données. Si aucun
    # compte gestionnaire n'existe, il n'y a rien à rattacher et la migration ne touche
    # rien : une valeur inventée serait pire qu'une valeur absente.
    firm = sa.text(
        "SELECT id FROM users WHERE role = 'manager' ORDER BY created_at, id LIMIT 1"
    )
    connection = op.get_bind()
    owner = connection.execute(firm).scalar()
    if owner is not None:
        connection.execute(
            sa.text("UPDATE users SET firm_id = NULL WHERE id = :owner"), {"owner": owner}
        )
        for table in ROOTS:
            connection.execute(
                sa.text(f"UPDATE {table} SET firm_id = :owner WHERE firm_id IS NULL"),
                {"owner": owner},
            )
        # Les autres comptes gestionnaires rejoignent cette société : ils voyaient déjà
        # tout, les rattacher ailleurs leur RETIRERAIT un accès qu'ils avaient. Un
        # découpage réel se fait à la main, en connaissance de cause.
        connection.execute(
            sa.text(
                "UPDATE users SET firm_id = :owner "
                "WHERE role = 'manager' AND id <> :owner AND firm_id IS NULL"
            ),
            {"owner": owner},
        )


def downgrade() -> None:
    for table in ROOTS:
        op.drop_index(f"ix_{table}_firm_id", table_name=table)
        op.drop_column(table, "firm_id")
    op.drop_index("ix_users_firm_id", table_name="users")
    op.drop_column("users", "firm_id")
