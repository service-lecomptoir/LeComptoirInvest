"""The investor's annual statement: what they were paid, and under which heading."""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import investor_scope
from app.database import get_db
from app.services import statement_service
from app.core.i18n import pick

router = APIRouter(tags=["statements"])


@router.get("/statements/{year}")
async def statement(
    year: int,
    investor_id: uuid.UUID | None = None,
    scope: uuid.UUID | None = Depends(investor_scope),
    db: AsyncSession = Depends(get_db),
):
    """One investor, one year.

    A manager may ask for any investor; an investor is always themselves, and the query
    parameter is IGNORED for them rather than refused — a scope a parameter can widen is
    not a scope. Same rule as the portfolio endpoint, written the same way on purpose.
    """
    target = scope if scope is not None else investor_id
    if target is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            pick(
                "Préciser l'investisseur dont on veut le relevé.",
                "Say which investor the statement is for.",
            ),
        )
    if year < 2000 or year > 2200:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            pick("Année invalide.", "Invalid year."),
        )
    try:
        built = await statement_service.statement_for(db, investor_id=target, year=year)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    def money(value: Decimal) -> str:
        return str(value)

    return {
        "investor_id": str(built.investor_id),
        "investor_name": built.investor_name,
        "year": built.year,
        "lines": [
            {
                "instrument": line.instrument,
                "currency": line.currency,
                "income_gross": money(line.income_gross),
                "withholding": money(line.withholding),
                "income_net": money(line.income_net),
                "capital_repaid": money(line.capital_repaid),
                "received": money(line.received),
            }
            for line in built.lines
        ],
        "totals_by_currency": {
            currency: {k: money(v) for k, v in block.items()}
            for currency, block in built.totals_by_currency().items()
        },
        "capital_at_work": {c: money(v) for c, v in built.capital_at_work.items()},
        # Shown apart and never added: an investor told they received money still sitting in
        # the fund's account would declare income they never got.
        "decided_not_paid": {c: money(v) for c, v in built.decided_not_paid.items()},
    }
