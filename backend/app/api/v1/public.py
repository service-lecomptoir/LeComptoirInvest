"""What is open to somebody who has no account yet: the plans, and the sign-up.

🔴 THIS PRODUCT DOES NOT CREATE ITS OWN ACCOUNTS: the console (Alice) does, because it
holds the plan, the licence and the billing. The product owner, 28-29 Sept 2026: every
Le Comptoir has a sign-up with a plan and a public pricing page, as on Immo, and « seules
les offres catalogues sont publiques ». The prospect CHOOSES a catalogue plan here; Alice
runs the double opt-in (a confirmation e-mail, then the account and its credentials).
A management company running several vehicles for clients is quoted instead: no plan is
sent, an operator answers. Same contract, same answers as Le Comptoir RH, the reference.

⚠️ THE ANSWER IS ALICE'S, NOT A FIXED SENTENCE: `confirmation_sent`, `account_exists`
(with the sign-in and subscription addresses) or `received`. The screen says which.

⚠️ AND IF ALICE IS NOT CONFIGURED OR FAILS, WE SAY SO (503). A request swallowed in
silence is worse than a refusal: the prospect believes they have been heard.

⚠️ THE BILLED UNIT IS THE INVESTOR: Alice's `managed_limit` is a number of investors here
(`investor_limit`), never a number of funds or vehicles.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.core import account_kind
from app.core.i18n import current_lang, pick
from app.core.landlord_kind_values import COMPANY, PERSON
from app.core.visitor_window import VisitorWindow
from app.services import alice_client

router = APIRouter(prefix="/public", tags=["public"])

#: What the console will see in « Demandes », so as to know where the prospect comes from.
_SOURCE = "invest_login"

#: 🔴 WHO IS ASKING, IN TWO QUESTIONS. A club or a fund managing its own money takes a
#: catalogue plan; a management company running several vehicles for clients is quoted.
#: The words are the ones this product already stores for the account (`account_kind`).
SINGLE_FUND = account_kind.SINGLE_FUND
MANAGEMENT_COMPANY = account_kind.MANAGEMENT_COMPANY
PROFILES: tuple[str, ...] = (SINGLE_FUND, MANAGEMENT_COMPANY)

#: The account is opened for a natural person or for a company: the console's own two
#: words (`owner_kind`), which are also the ones this product stores on an investor.
REQUESTER_KINDS: tuple[str, ...] = (PERSON, COMPANY)


def _profile_sentence(profile: str) -> str:
    """What the console reads first in the request. French: it is the operators' language,
    and the console files it as it is."""
    if profile == MANAGEMENT_COMPANY:
        return "Société de gestion : gère plusieurs véhicules pour des clients."
    return "Un club ou un fonds."


class AccessRequest(BaseModel):
    #: A person gives a first name and a last name; a company, its name and number. The
    #: account's name is built from them (`holder_name`), never typed a second time.
    first_name: str = Field(default="", max_length=75)
    last_name: str = Field(default="", max_length=75)
    email: EmailStr
    profile: str = Field(default=SINGLE_FUND, max_length=30)
    requester_kind: str = Field(default=PERSON, max_length=10)
    company: str = Field(default="", max_length=200)
    company_number: str = Field(default="", max_length=50)
    phone: str = Field(default="", max_length=40)
    message: str = Field(default="", max_length=2000)
    #: The catalogue plan chosen; None for a quotation.
    plan_id: str | None = Field(default=None, max_length=64)
    #: The address the invoice is sent to.
    street: str = Field(default="", max_length=300)
    zip_code: str = Field(default="", max_length=20)
    city: str = Field(default="", max_length=120)
    region: str = Field(default="", max_length=120)
    #: The country's ISO code (or its name): France by default.
    country: str = Field(default="FR", max_length=60)


class Outcome(BaseModel):
    #: Alice's word: `confirmation_sent`, `account_exists`, `account_created`, `received`.
    status: str = "received"
    message: str
    login_url: str | None = None
    subscription_url: str | None = None


class PublicPlan(BaseModel):
    id: str
    name: str
    description: str | None = None
    #: The most investors the plan covers; None: no ceiling.
    investor_limit: int | None = None
    monthly_price: float = 0
    overage_price: float = 0
    tva_rate: float = 20
    prices: dict[str, float] | None = None
    billable_currencies: list[str] = []
    #: A quotation: no price shown, the request goes to an operator.
    sur_devis: bool = False


def holder_name(data: AccessRequest, company: str) -> str:
    """Whose name the account bears: the company's, or the person's « Prénom Nom »."""
    if data.requester_kind == COMPANY:
        return company
    return f"{data.first_name.strip()} {data.last_name.strip()}".strip()


def lead_payload(data: AccessRequest, company: str) -> dict:
    """What the console receives: its own words for the notions it already knows.

    ⚠️ `quote_only` FOR A MANAGEMENT COMPANY, and never a plan with it: a catalogue plan
    sent along would open an account at a catalogue price for several vehicles.
    """
    message = _profile_sentence(data.profile)
    if data.message.strip():
        message = f"{message} {data.message.strip()}"
    quoted = data.profile == MANAGEMENT_COMPANY
    return {
        # 🔴 A SIGN-UP, SAID AS SUCH: the console then applies the common rule (names,
        # company number checked against the register, phone, whole address) -- the rule
        # lives there, for every product, and not here.
        "kind": "signup",
        "first_name": data.first_name.strip() or None,
        "last_name": data.last_name.strip() or None,
        "full_name": holder_name(data, company),
        "email": str(data.email).strip().lower(),
        "phone": data.phone.strip() or None,
        "company": company or None,
        "message": message,
        "source": _SOURCE,
        "product": alice_client.PRODUCT,
        "quote_only": quoted,
        "owner_kind": data.requester_kind,
        "owner_account_name": holder_name(data, company),
        "owner_company": company or None,
        "owner_company_number": data.company_number.strip() or None,
        "plan_id": None if quoted else (data.plan_id or None),
        "street": data.street.strip() or None,
        "zip_code": data.zip_code.strip() or None,
        "city": data.city.strip() or None,
        "region": data.region.strip() or None,
        "country": data.country.strip() or "FR",
    }


#: At most this many sign-ups a minute from one visitor: a form open to the internet is
#: filled by robots too, and each one would send a confirmation e-mail.
SIGNUPS_PER_MINUTE = 5
_window = VisitorWindow(SIGNUPS_PER_MINUTE)


def rate_limited(request: Request) -> None:
    """Refuse the sixth sign-up of a minute from the same visitor (429)."""
    if not _window.admit(request):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            pick(
                "Trop de demandes d'un coup : réessayez dans une minute.",
                "Too many requests at once: try again in a minute.",
            ),
        )


def _plan_of(row: dict) -> PublicPlan | None:
    try:
        return PublicPlan(
            id=str(row["id"]),
            name=row.get("name") or "",
            description=row.get("description"),
            investor_limit=row.get("managed_limit"),
            monthly_price=float(row.get("monthly_price") or 0),
            overage_price=float(row.get("overage_price") or 0),
            tva_rate=float(row.get("tva_rate") or 20),
            prices=row.get("prices") or None,
            billable_currencies=row.get("billable_currencies") or [],
            sur_devis=bool(row.get("sur_devis") or row.get("quote_only")),
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


@router.get("/plans", response_model=list[PublicPlan])
async def plans() -> list[PublicPlan]:
    """The plans of Le Comptoir Invest, as Alice sells them. Empty when the console cannot
    be reached: the page then says so and still offers the request."""
    rows = await alice_client.public_plans()
    found = [_plan_of(row) for row in rows if isinstance(row, dict)]
    return [plan for plan in found if plan is not None]


def _own_sentence(word: str) -> str:
    """This product's sentence for each of the console's answers, in the reader's language."""
    if word == "confirmation_sent":
        return pick(
            "Un e-mail de confirmation vient de partir : cliquez sur le lien qu'il contient "
            "pour activer votre compte. Vos identifiants vous seront envoyés ensuite.",
            "A confirmation e-mail is on its way: click the link it contains to activate "
            "your account. Your credentials will be sent to you next.",
        )
    if word == "account_exists":
        return pick(
            "Un compte Le Comptoir Invest existe déjà avec cette adresse.",
            "A Le Comptoir Invest account already exists with this address.",
        )
    if word == "account_created":
        return pick(
            "Votre compte est créé : vos identifiants vous sont envoyés par e-mail.",
            "Your account is created: your credentials are being sent to you by e-mail.",
        )
    return pick(
        "Votre demande est enregistrée. Nous revenons vers vous très vite.",
        "Your request is recorded. We will get back to you very soon.",
    )


_KNOWN_ANSWERS = ("confirmation_sent", "account_exists", "account_created", "received")


@router.post(
    "/access-request", response_model=Outcome, status_code=status.HTTP_201_CREATED
)
async def access_request(
    data: AccessRequest, _: None = Depends(rate_limited)
) -> Outcome:
    """Files a sign-up with the console: with a catalogue plan, Alice sends the
    confirmation e-mail and creates the account; without one, an operator answers."""
    if not alice_client.console_configured():
        # ⚠️ 503 AND NOT 500: an incomplete installation, not a breakdown, and the
        # difference changes what the reader must do.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            pick(
                "Les demandes d'accès ne sont pas configurées sur cette installation. "
                "Écrivez-nous à contact@lecomptoir.services.",
                "Access requests are not configured on this installation. "
                "Write to us at contact@lecomptoir.services.",
            ),
        )
    if data.profile not in PROFILES or data.requester_kind not in REQUESTER_KINDS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            pick("Précisez qui demande l'accès.", "Say who is asking for access."),
        )
    payload = lead_payload(data, data.company.strip())
    try:
        said = await alice_client.file_lead(payload)
    except alice_client.SignupRefused as refused:
        # The console's own sentence (« Indiquez votre prénom et votre nom. »): it is what
        # the person must correct, said once, for every product.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(refused)) from None
    except alice_client.AliceUnavailable as failed:
        # ⚠️ WE DO NOT PRETEND: the request exists nowhere if the call failed.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(failed)) from None

    word = str(said.get("status") or "received")
    theirs = said.get("message")
    # ⚠️ THE CONSOLE WRITES IN FRENCH ONLY. A French reader gets its sentence as it is; any
    # other reader gets this product's own for a known answer, not a French paragraph.
    if (
        isinstance(theirs, str)
        and theirs.strip()
        and (current_lang() == "fr" or word not in _KNOWN_ANSWERS)
    ):
        message = theirs.strip()
    else:
        message = _own_sentence(word)
    return Outcome(
        status=word,
        message=message,
        login_url=said.get("login_url"),
        subscription_url=said.get("subscription_url"),
    )
