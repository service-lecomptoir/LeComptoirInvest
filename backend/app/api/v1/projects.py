"""Where the money went, and what came back.

The other half of the treasury. Every figure here is an attribution of a BANK MOVEMENT: a
project whose performance is keyed in by hand reports whatever its manager believes, and
believing is what an investor pays a fund not to have to do.
"""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_manager, current_user
from app.database import get_db
from app.models.project import PROJECT_STATUSES, STUDY, Project
from app.models.treasury import BankMovement
from app.models.user import User
from app.services import project_service

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectIn(BaseModel):
    name: str
    currency: str
    description: str | None = None
    status: str = STUDY
    target_amount: Decimal | None = None
    started_on: date | None = None
    expected_end_on: date | None = None
    immo_property_id: str | None = None


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    currency: str
    target_amount: Decimal | None
    deployed: Decimal
    capital_returned: Decimal
    income_returned: Decimal
    outstanding: Decimal
    gain: Decimal
    multiple: Decimal | None


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create(
    data: ProjectIn,
    _: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    if data.status not in PROJECT_STATUSES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Statut inconnu : {data.status!r}. Attendus : {', '.join(PROJECT_STATUSES)}.",
        )
    project = Project(**data.model_dump() | {"currency": data.currency.upper()})
    db.add(project)
    await db.flush()
    return ProjectOut(
        id=project.id,
        name=project.name,
        status=project.status,
        currency=project.currency,
        target_amount=project.target_amount,
        deployed=Decimal("0"),
        capital_returned=Decimal("0"),
        income_returned=Decimal("0"),
        outstanding=Decimal("0"),
        gain=Decimal("0"),
        multiple=None,
    )


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    _: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    """Every project with what actually moved.

    ⚠️ READABLE BY AN INVESTOR, and deliberately so: they are told where their money went,
    which is the whole promise. No investor-specific figure appears here — a project is the
    fund's, never one subscriber's — so there is nothing to scope.
    """
    projects = {p.id: p for p in (await db.execute(select(Project))).scalars().all()}
    return [
        ProjectOut(
            id=r.project_id,
            name=r.name,
            status=r.status,
            currency=r.currency,
            target_amount=projects[r.project_id].target_amount,
            deployed=r.deployed,
            capital_returned=r.capital_returned,
            income_returned=r.income_returned,
            outstanding=r.outstanding,
            gain=r.gain,
            multiple=r.multiple(),
        )
        for r in await project_service.results(db)
    ]


class DeployIn(BaseModel):
    bank_movement_id: uuid.UUID
    amount: Decimal
    note: str | None = None


@router.post("/{project_id}/deployments", status_code=status.HTTP_201_CREATED)
async def deploy(
    project_id: uuid.UUID,
    data: DeployIn,
    user: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Money leaves for a project, against the outgoing transfer that carried it."""
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Projet introuvable.")
    movement = await db.get(BankMovement, data.bank_movement_id)
    if movement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mouvement introuvable.")
    try:
        deployment = await project_service.deploy(
            db,
            project=project,
            movement=movement,
            amount=data.amount,
            decided_by=user.email,
            note=data.note,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"id": str(deployment.id), "amount": str(deployment.amount)}


class ReturnIn(BaseModel):
    bank_movement_id: uuid.UUID
    #: 🔴 BOTH REQUIRED, and neither defaults. A return recorded as one figure lets a
    #: project that merely gave the money back be shown as having performed.
    capital_amount: Decimal
    income_amount: Decimal
    note: str | None = None


@router.post("/{project_id}/returns", status_code=status.HTTP_201_CREATED)
async def record_return(
    project_id: uuid.UUID,
    data: ReturnIn,
    _: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Money comes back, split between the fund's own capital and what was earned."""
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Projet introuvable.")
    movement = await db.get(BankMovement, data.bank_movement_id)
    if movement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mouvement introuvable.")
    try:
        returned = await project_service.record_return(
            db,
            project=project,
            movement=movement,
            capital_amount=data.capital_amount,
            income_amount=data.income_amount,
            note=data.note,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"id": str(returned.id), "total": str(returned.total)}


class StatusIn(BaseModel):
    status: str
    closed_on: date | None = None


@router.post("/{project_id}/status", response_model=ProjectOut)
async def set_status(
    project_id: uuid.UUID,
    data: StatusIn,
    _: User = Depends(current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Change where a project stands.

    ⚠️ « CLOSED » AND « WRITTEN OFF » ARE NOT THE SAME NEWS, and the model keeps them apart
    for that reason. Closing a project that lost money would report a wind-down where there
    was a loss, and the investor is owed the difference in plain words.
    """
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Projet introuvable.")
    if data.status not in PROJECT_STATUSES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Statut inconnu : {data.status!r}. Attendus : {', '.join(PROJECT_STATUSES)}.",
        )
    project.status = data.status
    if data.closed_on is not None:
        project.closed_on = data.closed_on
    await db.flush()
    result = next(
        r for r in await project_service.results(db) if r.project_id == project.id
    )
    return ProjectOut(
        id=result.project_id,
        name=result.name,
        status=result.status,
        currency=result.currency,
        target_amount=project.target_amount,
        deployed=result.deployed,
        capital_returned=result.capital_returned,
        income_returned=result.income_returned,
        outstanding=result.outstanding,
        gain=result.gain,
        multiple=result.multiple(),
    )
