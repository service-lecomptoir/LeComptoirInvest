"""What the fund puts the money INTO, and what comes back out of it.

THE OTHER HALF OF THE TREASURY. Money in from investors, money out to projects, money back
from projects, money out to investors: four movements, and until now the model held only the
two that involve investors. A fund that cannot say where the money went is not tracking
anything — it is a bank account with names on it.

⚠️ SAME DISCIPLINE AS THE INVESTOR SIDE: a deployment and a return are attributions of BANK
MOVEMENTS, never figures typed on their own. A project whose « performance » is keyed in by
hand reports whatever its manager believes, and believing is exactly what an investor is
paying not to have to do.

⚠️ AND A PROJECT IS NOT A SUBSCRIPTION. No investor is tied to one: they subscribe to the
FUND, the fund deploys where it chooses, and the project risk sits with the fund and then
with the subscribers. Tying an investor to a project would make the model unable to answer
what a lender is owed when the project they were « in » fails — which is: everything,
because they lent to the fund.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, uuid_pk

#: Being studied. No money committed.
STUDY = "etude"
#: Money committed and being deployed.
ACTIVE = "en_cours"
#: Finished: everything that was going to come back has.
CLOSED = "cloture"
#: Written off, wholly or in part. A state of its own, because « closed » and « lost » are
#: not the same news and an investor is owed the difference.
WRITTEN_OFF = "perdu"

PROJECT_STATUSES: tuple[str, ...] = (STUDY, ACTIVE, CLOSED, WRITTEN_OFF)

#: What came back: the fund's own money returning.
RETURN_CAPITAL = "capital"
#: What the project earned on top.
RETURN_INCOME = "produit"


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=STUDY, server_default=STUDY
    )
    #: The currency this project is financed in. May differ from an investor's: the fund can
    #: raise in euros and deploy in CFA francs, and the two never add.
    currency: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    #: What the fund intends to put in. An INTENTION, like a subscription's commitment: what
    #: actually went in is the sum of the deployments.
    target_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    started_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_end_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    #: A property of Le Comptoir Immo, when the project is one. A REFERENCE, not a foreign
    #: key: the two products have separate databases, and a constraint across them would
    #: make one unable to start without the other. Empty for a project that is not a lot.
    immo_property_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    deployments: Mapped[list["Deployment"]] = relationship(
        "Deployment", back_populates="project", cascade="all, delete-orphan"
    )
    returns: Mapped[list["ProjectReturn"]] = relationship(
        "ProjectReturn", back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Project {self.name} [{self.status}]>"


class Deployment(Base, TimestampMixin):
    """Money leaving the fund for a project.

    Anchored on the outgoing bank movement, for the same reason a contribution is anchored
    on the incoming one: a deployment nobody can point at in a statement is a figure, and a
    figure is what a fund reports when it has stopped reconciling.
    """

    __tablename__ = "deployments"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    bank_movement_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("bank_movements.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    deployed_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: Who decided. A deployment is the fund spending its investors' money, and « who
    #: authorised this » is the first question anyone reviewing it asks.
    decided_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="deployments")

    def __repr__(self) -> str:
        return f"<Deployment {self.amount} {self.currency} on {self.deployed_on}>"


class ProjectReturn(Base, TimestampMixin):
    """Money coming back from a project, split the same way a distribution is.

    🔴 CAPITAL AND INCOME ARE SEPARATE HERE TOO, and for the same reason as on the investor
    side: getting the fund's own money back is not a gain. A project that returned exactly
    what it was given has earned nothing, and a single figure would let it be reported as
    performance.

    That split is also what makes the fund's own result computable: the sum of what came back
    as income, less what the fund pays out as income, is what it actually made.
    """

    __tablename__ = "project_returns"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    bank_movement_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("bank_movements.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    #: The fund's own money returning.
    capital_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    #: What the project earned on top.
    income_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    received_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="returns")

    @property
    def total(self) -> Decimal:
        """Derived, never stored beside its parts: a stored total is a third number that can
        disagree with the two it sums."""
        return (self.capital_amount or Decimal("0")) + (
            self.income_amount or Decimal("0")
        )

    def __repr__(self) -> str:
        return f"<ProjectReturn cap={self.capital_amount} inc={self.income_amount}>"
