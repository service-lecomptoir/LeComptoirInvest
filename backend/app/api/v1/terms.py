"""The terms of use and the terms of sale, relayed from Alice for the signed-in account.

The manager, 2 Oct 2026: every person who signs in accepts the terms of use (`cgu`) for
themself, at their first sign-in and again at each new version; only the subscriber, the
account that holds the licence and pays, accepts the terms of sale (`cgv`). Alice holds
the texts, the versions and the proof; this product keeps nothing of its own and relays
through its server, because the internal key never reaches a browser.

🔴 THE FAILURE MODE, DECIDED AND TESTED: AN ALICE OUTAGE NEVER LOCKS ANYONE OUT. When
Alice does not answer, `GET /terms/status` says `unavailable: true` with nothing pending,
and every account already here keeps working; the question comes back at the next
sign-in. This fails OPEN for existing accounts, and CLOSED for a new sign-up: the public
text route answers 503 and the form refuses to send (`api/v1/public.py`), because a
sign-up that cannot record its acceptance must not go through.

⚠️ WHO IS ASKED, BY THE WORD ALICE'S REGISTRY USES (`audience`): `manager` for the fund's
management, `investor` for an investor's login. The platform's own `admin` is NOT asked:
it is the publisher of these terms, not a party to them.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.core import audit
from app.core.i18n import current_lang, french_colons, pick
from app.models.user import INVESTOR, MANAGER, User
from app.services import alice_client

router = APIRouter(prefix="/terms", tags=["terms"])

#: The two documents, in Alice's words.
USE = "cgu"
SALE = "cgv"
KINDS: tuple[str, ...] = (USE, SALE)

#: The terms of sale are one text for every kind of account (Alice's `all`).
EVERYONE = "all"

#: 🔴 THE ROLE AND THE WORD ALICE'S REGISTRY NAMES IT BY. `admin` is deliberately absent:
#: the operator publishes the terms, it is never asked to accept them.
AUDIENCES: dict[str, str] = {MANAGER: "manager", INVESTOR: "investor"}


def audience_of(user: User) -> str | None:
    """The word this account is asked under, or None for the operator."""
    return AUDIENCES.get(user.role)


def known_kind(kind: str) -> str:
    if kind not in KINDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            pick(
                "Le document est « cgu » (utilisation) ou « cgv » (vente).",
                "The document is « cgu » (use) or « cgv » (sale).",
            ),
        )
    return kind


def _alice_says(sentence: str) -> str:
    """Alice writes in French: the French reader gets her sentence with its spacing."""
    return french_colons(sentence) if current_lang() == "fr" else sentence


class DocumentStatus(BaseModel):
    """Alice's status of one document, plus the one thing the screen decides on."""

    version: str | None = None
    product: str | None = None
    audience: str | None = None
    effective_from: str | None = None
    accepted_version: str | None = None
    accepted_at: str | None = None
    up_to_date: bool = True
    anything_to_accept: bool = False
    #: Owed now: a published version this account has not accepted.
    pending: bool = False


class TermsStatus(BaseModel):
    cgu: DocumentStatus | None = None
    #: Only for the subscriber; None for every other account.
    cgv: DocumentStatus | None = None
    #: Alice did not answer. Nothing is pending, and the account goes on working.
    unavailable: bool = False
    #: This account holds the licence (`User.holds_the_licence`): the screens show it the
    #: terms of sale and name its own way of closing the account.
    subscriber: bool = False


def _document(raw: object) -> DocumentStatus | None:
    if not isinstance(raw, dict):
        return None
    found = DocumentStatus.model_validate(
        {key: raw.get(key) for key in DocumentStatus.model_fields if key != "pending"}
        | {
            "up_to_date": bool(raw.get("up_to_date", True)),
            "anything_to_accept": bool(raw.get("anything_to_accept", False)),
        }
    )
    found.pending = found.anything_to_accept and not found.up_to_date
    return found


@router.get("/status", response_model=TermsStatus)
async def my_terms_status(user: User = Depends(current_user)) -> TermsStatus:
    """What this account still owes, document by document."""
    audience = audience_of(user)
    if audience is None:
        return TermsStatus()
    subscriber = user.holds_the_licence
    raw = await alice_client.terms_status(
        user.id, audience=audience, subscriber=subscriber
    )
    if raw is None:
        # 🔴 FAIL OPEN: see the module's docstring.
        return TermsStatus(unavailable=True, subscriber=subscriber)
    return TermsStatus(
        cgu=_document(raw.get("cgu")),
        cgv=_document(raw.get("cgv")) if subscriber else None,
        subscriber=subscriber,
    )


def _terms_unavailable() -> HTTPException:
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        pick(
            "Les conditions générales ne peuvent pas être chargées pour le moment : "
            "réessayez dans quelques minutes.",
            "The terms cannot be loaded at the moment: try again in a few minutes.",
        ),
    )


def _nothing_published() -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND,
        pick(
            "Aucune version de ce document n'est publiée.",
            "No version of this document is published.",
        ),
    )


async def relay_text(
    kind: str,
    *,
    language: str,
    audience: str,
    product: str = alice_client.PRODUCT,
    version: str | None = None,
    newcomer: bool = False,
) -> dict:
    """One text as Alice serves it: 404 when nothing is published, 503 when she is silent."""
    reply = await alice_client.terms_text(
        kind,
        language=language,
        audience=audience,
        product=product,
        version=version,
        newcomer=newcomer,
    )
    if reply is None:
        raise _terms_unavailable()
    if reply.status == 404:
        raise _nothing_published()
    if reply.status != 200 or not isinstance(reply.body, dict):
        raise _terms_unavailable()
    return reply.body


@router.get("/text")
async def read_terms_text(
    kind: str = Query(max_length=3),
    language: str = Query(default="fr", max_length=5),
    version: str | None = Query(default=None, max_length=20),
    product: str | None = Query(default=None, max_length=20),
    audience: str | None = Query(default=None, max_length=20),
    user: User = Depends(current_user),
) -> dict:
    """A text to read: the version a status names, or one this account accepted.

    ⚠️ `product` AND `audience` ARE THE SCOPE THE TEXT WAS WRITTEN FOR, as a history entry
    or a status names it: rereading an acceptance asks for that exact text, not for the
    version of the same number in another scope.
    """
    known_kind(kind)
    return await relay_text(
        kind,
        language=language,
        audience=audience
        or (EVERYONE if kind == SALE else (audience_of(user) or EVERYONE)),
        product=product or alice_client.PRODUCT,
        version=version,
    )


class AcceptIn(BaseModel):
    kind: str = Field(max_length=3)
    #: The version the screen SHOWED. Alice refuses it (409) when it is not the one owed.
    version: str = Field(max_length=20)
    language: str = Field(default="fr", max_length=5)


def _not_recorded() -> HTTPException:
    return HTTPException(
        status.HTTP_502_BAD_GATEWAY,
        pick(
            "Votre acceptation n'a pas pu être enregistrée : réessayez dans un instant.",
            "Your acceptance could not be recorded: try again in a moment.",
        ),
    )


async def record_acceptance(
    user: User, request: Request, *, kind: str, version: str, language: str, method: str
) -> dict:
    """Have Alice record that this account accepted this version, with its proof.

    🔴 THE ADDRESS AND THE BROWSER ARE THE PERSON'S, read from the request THIS product
    received (`audit.client_address`, the hop the edge proxy wrote). Alice is called server
    to server: her own view of the request would name this product.
    """
    known_kind(kind)
    audience = audience_of(user)
    if audience is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            pick(
                "Ce compte publie les conditions générales : il n'a rien à accepter.",
                "This account publishes the terms: it has nothing to accept.",
            ),
        )
    if kind == SALE and not user.holds_the_licence:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            pick(
                "Seul le titulaire de l'abonnement accepte les conditions générales de vente.",
                "Only the subscription holder accepts the terms of sale.",
            ),
        )
    reply = await alice_client.accept_terms(
        {
            "account_product": alice_client.PRODUCT,
            "account_id": str(user.id),
            "account_kind": audience,
            "account_email": user.email,
            "kind": kind,
            "audience": audience if kind == USE else EVERYONE,
            "version": version,
            "language": language,
            "method": method,
            "ip_address": audit.client_address(request),
            "user_agent": request.headers.get("user-agent"),
        }
    )
    if reply is None:
        raise _not_recorded()
    if reply.status in (200, 201):
        return reply.body if isinstance(reply.body, dict) else {}
    if reply.status in (404, 409) and reply.detail:
        # 409: the page showed a version that is no longer the one owed. 404: nothing is.
        # Alice's sentence says which, and what to do.
        raise HTTPException(reply.status, _alice_says(reply.detail))
    raise _not_recorded()


@router.post("/accept", status_code=status.HTTP_201_CREATED)
async def accept(
    body: AcceptIn, request: Request, user: User = Depends(current_user)
) -> dict:
    """The person accepted, on the page that asked at sign-in."""
    return await record_acceptance(
        user,
        request,
        kind=body.kind,
        version=body.version,
        language=body.language,
        method="update",
    )


class TermsHistory(BaseModel):
    entries: list[dict] = []
    #: Alice did not answer: the screen says it cannot tell, never « nothing accepted ».
    unavailable: bool = False


@router.get("/history", response_model=TermsHistory)
async def my_terms_history(user: User = Depends(current_user)) -> TermsHistory:
    """What this account accepted, most recent first, for its profile."""
    if audience_of(user) is None:
        return TermsHistory()
    found = await alice_client.terms_history(user.id)
    if found is None:
        return TermsHistory(unavailable=True)
    return TermsHistory(entries=[row for row in found if isinstance(row, dict)])
