"""The investor's annual statement: what they were paid, and under which heading."""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import investor_scope
from app.database import get_db
from app.core import i18n
from app.models.investor import Investor
from app.services import notice_service, statement_service
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

    # 🔴 THE HEADINGS ARE THE INVESTOR'S, NOT THE CALLER'S.
    #
    # A manager may ask for any investor's statement, and what they do with it is send it to
    # that investor or attach it to their tax file. Rendering the headings from the caller's
    # `Accept-Language` would put French column titles on a British investor's return, and
    # nothing in the product would look wrong: the figures are identical either way.
    #
    # ⚠️ THE FRONT END STILL HAS ITS OWN CATALOGUE for the screen a manager reads, and that
    # is not a duplicate: on screen the reader IS the caller. These labels exist for the
    # document that LEAVES, which has no front end to translate it.
    investor = await db.get(Investor, target)
    language = (
        await notice_service.language_of(db, investor)
        if investor is not None
        else i18n.DEFAULT
    )
    with i18n.use_lang(language):
        labels = {
            "title": pick(
                f"Relevé annuel {built.year}", f"Annual statement {built.year}"
            ),
            "instrument": pick("Instrument", "Instrument"),
            "currency": pick("Devise", "Currency"),
            "income_gross": pick("Produit brut", "Gross income"),
            "withholding": pick("Retenue à la source", "Withholding at source"),
            "income_net": pick("Produit net", "Net income"),
            "capital_repaid": pick("Capital remboursé", "Capital repaid"),
            "received": pick("Total reçu", "Total received"),
            "capital_at_work": pick("Capital au travail", "Capital at work"),
            "decided_not_paid": pick(
                "Décidé et non encore versé", "Decided and not yet paid"
            ),
            "decided_not_paid_note": pick(
                "Montré à part et jamais additionné : un investisseur à qui l'on annonce "
                "une somme encore sur le compte du fonds déclarerait un revenu qu'il n'a "
                "pas reçu.",
                "Shown apart and never added in: an investor told about money still sitting "
                "in the fund's account would declare income they never received.",
            ),
        }

    return {
        "investor_id": str(built.investor_id),
        "investor_name": built.investor_name,
        "year": built.year,
        "language": language,
        "labels": labels,
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
