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

    # ── Attaching what already exists ────────────────────────────────────────
    #
    # ⚠️ TO THE OLDEST MANAGER ACCOUNT, and not to whoever comes first. On a real
    # installation that is the account of the firm which created this data. If no manager
    # account exists there is nothing to attach and this migration touches nothing: an
    # invented value would be worse than an absent one.
    firm = sa.text(
        "SELECT id FROM users WHERE role = 'manager' ORDER BY created_at, id LIMIT 1"
    )
    connection = op.get_bind()
    owner = connection.execute(firm).scalar()
    if owner is None:
        return

    connection.execute(
        sa.text("UPDATE users SET firm_id = NULL WHERE id = :owner"), {"owner": owner}
    )
    for table in ROOTS:
        connection.execute(
            sa.text(f"UPDATE {table} SET firm_id = :owner WHERE firm_id IS NULL"),
            {"owner": owner},
        )

    # 🔴 EVERY OTHER MANAGER ACCOUNT BECOMES ITS OWN FIRM, and that is the whole point of
    # this migration. They saw the first firm's register because there was nothing to stop
    # them; attaching them to it here would keep exactly that, and this file would change
    # nothing for the only installation that has two of them.
    #
    # ⚠️ SO IT DOES TAKE AN ACCESS AWAY, deliberately: an access nobody granted. On this
    # installation the second manager account is the operator's own. A real firm with two
    # colleagues is set up by naming the second account's `firm_id` by hand, which is one
    # UPDATE and a decision somebody makes knowingly -- the opposite of a default that
    # silently pools two customers.

    # ⚠️ THE ACCOUNTS THAT ARE NOT MANAGERS FOLLOW THEIR REGISTER ENTRY, never themselves.
    # An investor's login left without a firm would resolve its scope to its own id, own no
    # row anywhere, and open on an empty portfolio -- the isolation working perfectly
    # against the person it exists to serve.
    connection.execute(
        sa.text(
            "UPDATE users u SET firm_id = i.firm_id FROM investors i "
            "WHERE i.user_id = u.id AND u.role <> 'manager' AND u.firm_id IS NULL"
        )
    )
    # And those with no register entry at all join the firm that owns the data, for the
    # same reason: an account of nobody reads nothing.
    connection.execute(
        sa.text(
            "UPDATE users SET firm_id = :owner "
            "WHERE role <> 'manager' AND firm_id IS NULL"
        ),
        {"owner": owner},
    )


def downgrade() -> None:
    for table in ROOTS:
        op.drop_index(f"ix_{table}_firm_id", table_name=table)
        op.drop_column(table, "firm_id")
    op.drop_index("ix_users_firm_id", table_name="users")
    op.drop_column("users", "firm_id")
