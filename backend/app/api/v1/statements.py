"""The investor's annual statement: what they were paid, and under which heading.

🔴 TWO ROUTES, ONE PIECE OF WORK, AND THEREFORE ONE FUNCTION. The screen reads JSON and the
investor files a PDF, but « whose statement is this, for which year, and in whose language »
is the same question both times. `_prepared` answers it once. Writing the scope check twice
is this repository's most expensive habit: the second copy is always the weaker one, and the
weakness here would be an investor reading somebody else's payments.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import investor_scope
from app.database import get_db
from app.core import firm_scope, i18n
from app.models.investor import Investor
from app.services import notice_service, statement_pdf, statement_service
from app.core.i18n import pick

router = APIRouter(tags=["statements"])


@dataclass
class _Prepared:
    """One investor, one year, and the language the DOCUMENT must speak."""

    built: statement_service.Statement
    language: str
    labels: dict


async def _prepared(
    db: AsyncSession,
    *,
    year: int,
    scope: uuid.UUID | None,
    investor_id: uuid.UUID | None,
) -> _Prepared:
    """Resolve who this is for, build it, and settle its language. For BOTH routes.

    A manager may ask for any investor; an investor is always themselves, and the query
    parameter is IGNORED for them rather than refused — a scope a parameter can widen is
    not a scope. Same rule as the portfolio endpoint, written the same way on purpose.

    🔴 THE HEADINGS ARE THE INVESTOR'S, NOT THE CALLER'S.

    A manager may pull any investor's statement, and what they do with it is send it to that
    investor or attach it to their tax file. Rendering the headings from the caller's
    `Accept-Language` would put French column titles on a British investor's return, and
    nothing in the product would look wrong: the figures are identical either way.

    ⚠️ THE FRONT END STILL HAS ITS OWN CATALOGUE for the screen a manager reads, and that is
    not a duplicate: on screen the reader IS the caller. These labels exist for the document
    that LEAVES, which has no front end to translate it.
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

    investor = await db.get(Investor, target)
    # 🔴 A SCOPE A PARAMETER CAN WIDEN IS NOT A SCOPE.
    #
    # `investor_id` is accepted from the request for managers, and the per-firm filter does
    # NOT cover this lookup: `Session.get()` answers from the identity map when the object
    # is already loaded, and then no query is issued for the filter to reach. Naming
    # another firm's investor therefore returned their statement, with their name on it.
    #
    # ⚠️ 404 AND NOT 403: answering « forbidden » would confirm that this investor exists
    # somewhere on the installation, which is itself a thing a competitor should not learn
    # by changing a digit in the address.
    if investor is not None and not firm_scope.owns(investor):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            pick("Investisseur introuvable.", "Investor not found."),
        )
    language = (
        await notice_service.language_of(db, investor)
        if investor is not None
        else i18n.DEFAULT
    )
    with i18n.use_lang(language):
        labels = statement_service.labels(built.year)
    return _Prepared(built=built, language=language, labels=labels)


@router.get("/statements/{year}")
async def statement(
    year: int,
    investor_id: uuid.UUID | None = None,
    scope: uuid.UUID | None = Depends(investor_scope),
    db: AsyncSession = Depends(get_db),
):
    """One investor, one year, as the screen reads it."""
    ready = await _prepared(db, year=year, scope=scope, investor_id=investor_id)
    built = ready.built

    def money(value: Decimal) -> str:
        return str(value)

    return {
        "investor_id": str(built.investor_id),
        "investor_name": built.investor_name,
        "year": built.year,
        "language": ready.language,
        "labels": ready.labels,
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


@router.get("/statements/{year}/pdf")
async def statement_as_pdf(
    year: int,
    investor_id: uuid.UUID | None = None,
    scope: uuid.UUID | None = Depends(investor_scope),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The same statement, as the document an investor files.

    🔴 THE WHOLE DOCUMENT IS BUILT INSIDE `use_lang`, headings AND figures. The third caller
    of that context manager, after the capital-call notice and the labels above. A statement
    is read by somebody who never signs in, months later, next to a tax form: it must speak
    their language including its decimal separator, because « 1,234 » under the wrong
    convention is a thousand or it is one.

    ⚠️ IT IS SERVED INLINE, not as a forced download. A manager checking a figure before
    forwarding it should not have to open their downloads folder; the browser's own viewer
    is the fastest path to « is this right », and `Content-Disposition: inline` with a
    filename still saves correctly.
    """
    ready = await _prepared(db, year=year, scope=scope, investor_id=investor_id)

    # ⚠️ THE ISSUER DEGRADES, THE DOCUMENT DOES NOT. This name comes from the console; if
    # nobody set it, or the console is unreachable, the line simply does not appear. Failing
    # the whole statement because a cosmetic header could not be read would deny an
    # investor their figures over a subscription service.
    issuer = ""
    try:
        from app.services.comm_config import get_effective_comm

        issuer = (await get_effective_comm()).SMTP_FROM_NAME or ""
    except Exception:  # noqa: BLE001
        issuer = ""

    with i18n.use_lang(ready.language):
        content = statement_pdf.render_pdf(ready.built, ready.labels, issuer=issuer)

    name = f"{ready.built.year}-{ready.built.investor_id}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{name}"'},
    )
