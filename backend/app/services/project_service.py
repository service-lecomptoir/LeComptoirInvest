"""What a project has consumed, what it has given back, and what that means.

⚠️ « PERFORMANCE » IS THE WORD THAT HIDES THE MOST. A project that returned exactly what it
was given has earned nothing, and reporting the gross return as performance is the oldest
flattering mistake in the business. Everything below keeps capital and income apart, so that
the figure an investor is shown is the one that was actually made.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Deployment, Project, ProjectReturn
from app.models.treasury import IN, OUT, BankMovement


@dataclass(frozen=True)
class ProjectResult:
    project_id: uuid.UUID
    name: str
    status: str
    currency: str
    deployed: Decimal
    capital_returned: Decimal
    income_returned: Decimal

    @property
    def outstanding(self) -> Decimal:
        """The fund's money still inside the project.

        ⚠️ Not clamped at zero: a project that has returned MORE capital than it was given
        is either a data error or a repayment of somebody else's money, and both are things
        somebody must look at rather than see rounded away.
        """
        return self.deployed - self.capital_returned

    @property
    def gain(self) -> Decimal:
        """What was actually earned. Never the gross return."""
        return self.income_returned

    def multiple(self) -> Decimal | None:
        """Total returned over total deployed. None until something has come back.

        🔴 NONE, PAS ZÉRO, ET LA PREMIÈRE VERSION NE COUVRAIT QUE LA MOITIÉ DU CAS. Elle
        rendait `None` tant que rien n'était déployé — mais un projet financé hier, qui n'a
        simplement pas encore eu le temps de rendre quoi que ce soit, affichait « 0,00x ».
        Vu à l'écran le 18 août : c'est exactement la lecture « il a tout perdu » que le
        commentaire d'origine disait vouloir éviter, et elle était pire, parce qu'elle
        portait sur un projet en bonne santé.

        Un ratio de ce qui n'est pas encore arrivé n'est pas nul : il est INCONNU. Et une
        perte réelle est déjà dite par le STATUT (« perte constatée ») et par `outstanding`,
        qui sont faits pour ça.
        """
        if self.deployed <= 0:
            return None
        returned = self.capital_returned + self.income_returned
        if returned <= 0:
            return None
        return returned / self.deployed


async def results(db: AsyncSession) -> list[ProjectResult]:
    """Every project with what actually moved. Three queries, never one per project."""
    projects = (
        (await db.execute(select(Project).order_by(Project.name))).scalars().all()
    )
    if not projects:
        return []

    deployed: dict[uuid.UUID, Decimal] = {}
    for project_id, amount in (
        await db.execute(select(Deployment.project_id, Deployment.amount))
    ).all():
        deployed[project_id] = deployed.get(project_id, Decimal("0")) + amount

    capital: dict[uuid.UUID, Decimal] = {}
    income: dict[uuid.UUID, Decimal] = {}
    for project_id, cap, inc in (
        await db.execute(
            select(
                ProjectReturn.project_id,
                ProjectReturn.capital_amount,
                ProjectReturn.income_amount,
            )
        )
    ).all():
        capital[project_id] = capital.get(project_id, Decimal("0")) + (
            cap or Decimal("0")
        )
        income[project_id] = income.get(project_id, Decimal("0")) + (
            inc or Decimal("0")
        )

    return [
        ProjectResult(
            project_id=p.id,
            name=p.name,
            status=p.status,
            currency=p.currency,
            deployed=deployed.get(p.id, Decimal("0")),
            capital_returned=capital.get(p.id, Decimal("0")),
            income_returned=income.get(p.id, Decimal("0")),
        )
        for p in projects
    ]


async def deploy(
    db: AsyncSession,
    *,
    project: Project,
    movement: BankMovement,
    amount: Decimal,
    decided_by: str,
    note: str | None = None,
) -> Deployment:
    """Send money to a project, against the outgoing transfer that carried it.

    ⚠️ THE MOVEMENT MUST BE AN OUTGOING ONE. Recording a deployment against money that came
    IN would balance the treasury by counting the same euro twice, in opposite directions,
    and the total would look right.
    """
    if movement.direction != OUT:
        raise ValueError(
            "Un déploiement s'impute sur un virement SORTANT : ce mouvement est une entrée."
        )
    if movement.currency != project.currency:
        raise ValueError(
            f"Le virement est en {movement.currency} et le projet en {project.currency}. "
            f"Une conversion est un événement daté, à un cours donné."
        )
    already = (
        (
            await db.execute(
                select(Deployment.amount).where(
                    Deployment.bank_movement_id == movement.id
                )
            )
        )
        .scalars()
        .all()
    )
    remaining = movement.amount - sum(already, Decimal("0"))
    if amount > remaining:
        raise ValueError(
            f"Ce virement ne porte plus que {remaining} {movement.currency} à imputer, "
            f"et {amount} sont demandés."
        )

    deployment = Deployment(
        project_id=project.id,
        bank_movement_id=movement.id,
        amount=amount,
        currency=movement.currency,
        deployed_on=movement.value_date,
        decided_by=decided_by,
        note=note,
    )
    db.add(deployment)
    await db.flush()
    return deployment


async def record_return(
    db: AsyncSession,
    *,
    project: Project,
    movement: BankMovement,
    capital_amount: Decimal,
    income_amount: Decimal,
    note: str | None = None,
) -> ProjectReturn:
    """Record money coming back, split between the fund's own capital and what was earned.

    🔴 THE SPLIT IS REQUIRED, not optional. A return recorded as one figure makes the fund's
    own result uncomputable, and lets a project that merely gave the money back be shown as
    having performed.
    """
    if movement.direction != IN:
        raise ValueError(
            "Un retour de projet s'impute sur un virement ENTRANT : ce mouvement est une sortie."
        )
    if movement.currency != project.currency:
        raise ValueError(
            f"Le virement est en {movement.currency} et le projet en {project.currency}."
        )
    total = capital_amount + income_amount
    if total <= 0:
        raise ValueError(
            "Un retour porte au moins un montant : capital, produit, ou les deux."
        )

    already = (
        await db.execute(
            select(ProjectReturn.capital_amount, ProjectReturn.income_amount).where(
                ProjectReturn.bank_movement_id == movement.id
            )
        )
    ).all()
    used = sum((c + i for c, i in already), Decimal("0"))
    if total > movement.amount - used:
        raise ValueError(
            f"Ce virement ne porte plus que {movement.amount - used} {movement.currency} "
            f"à imputer, et {total} sont demandés."
        )

    returned = ProjectReturn(
        project_id=project.id,
        bank_movement_id=movement.id,
        capital_amount=capital_amount,
        income_amount=income_amount,
        currency=movement.currency,
        received_on=movement.value_date,
        note=note,
    )
    db.add(returned)
    await db.flush()
    return returned
