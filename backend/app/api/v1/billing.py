"""The fund manager's own subscription: what they pay for this product, and how they pay it.

🔴 CE FICHIER NE S'APPELLE PAS `subscription.py`, ET C'EST DÉLIBÉRÉ. Dans ce produit, une
« souscription » est l'engagement d'un investisseur dans un fonds : c'est le mot du métier,
il est pris, et `api/v1/subscriptions.py` le porte déjà. Appeler l'abonnement au logiciel
« subscription » aurait mis deux notions sans rapport sous un seul nom, dans un domaine où
la confusion se lit en euros. Ici, l'abonnement au produit s'appelle « billing ».

🔴 AUCUN MONTANT N'EST DÉCIDÉ ICI. Le plan, le prix, le blocage et les factures
appartiennent à la console (Alice) : ce module est un relais qui ajoute l'identité de
l'appelant et rien d'autre. Écrire un prix ici en ferait une deuxième vérité, et c'est
exactement la classe de défaut que ce dépôt paie ailleurs.

⚠️ LA LECTURE EST DÉGRADABLE, LE PAIEMENT NE L'EST PAS. Si la console est injoignable,
l'écran affiche « inconnu » et le fonds continue de tourner. Mais une action de paiement
qui échoue en silence laisse un gestionnaire persuadé d'avoir payé : celles-là remontent
une erreur.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.api.deps import current_manager
from app.models.user import User
from app.services import alice_client
from app.services.alice_client import AliceUnavailable

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["billing"])


class SubscriptionInfo(BaseModel):
    """What the subscription screen shows at the top.

    ⚠️ `plan_name is None` NE VEUT PAS DIRE « GRATUIT ». Il veut dire « nous ne savons
    pas » : soit aucune console ne pilote cette instance, soit elle n'a pas répondu. Un
    écran qui traduirait l'absence en « offre gratuite » annoncerait un droit que personne
    n'a accordé.
    """

    #: False quand aucune console ne pilote cette instance : l'écran le dit, plutôt que
    #: d'afficher un abonnement vide qui ressemble à une panne.
    managed: bool
    plan_name: str | None = None
    monthly_price: float | None = None
    is_blocked: bool = False
    features: list[str] | None = None
    access_until: str | None = None
    #: Nombre de fonds inclus dans le plan, quand le plan en fixe un.
    fund_limit: int | None = None


def _as_info(license_: dict | None) -> SubscriptionInfo:
    if not license_:
        return SubscriptionInfo(managed=False)
    return SubscriptionInfo(
        managed=True,
        plan_name=license_.get("plan_name"),
        monthly_price=license_.get("monthly_price"),
        is_blocked=bool(license_.get("is_blocked")),
        features=license_.get("features"),
        access_until=license_.get("access_until"),
        # Alice nomme cette limite `property_limit` pour tous les produits : c'est le
        # contrat inter-produits, on le lit tel quel et on le renomme pour NOS écrans
        # seulement. Le renommer à la source casserait les trois autres produits.
        fund_limit=license_.get("property_limit"),
    )


@router.get("", response_model=SubscriptionInfo, summary="Mon abonnement")
async def my_subscription(user: User = Depends(current_manager)) -> SubscriptionInfo:
    return _as_info(await alice_client.get_license(user.id))


@router.get("/payment-methods", summary="Moyens de paiement proposés")
async def payment_methods(_: User = Depends(current_manager)) -> dict:
    """Ce que ce produit sait encaisser : carte/SEPA par Stripe, et/ou virement.

    ⚠️ LES DEUX PEUVENT ÊTRE FERMÉS EN MÊME TEMPS, et l'écran doit alors le dire au lieu
    de montrer deux boutons qui ne mènent nulle part.
    """
    cfg = await alice_client.payment_config()
    return {
        "card_enabled": bool(cfg.get("stripe_enabled")),
        "transfer_enabled": bool(cfg.get("rib_enabled")),
        "currency": cfg.get("stripe_currency") or "eur",
        "transfer": {
            "holder": cfg.get("rib_holder"),
            "iban": cfg.get("rib_iban"),
            "bic": cfg.get("rib_bic"),
            "bank": cfg.get("rib_bank"),
            "instructions": cfg.get("rib_instructions"),
        }
        if cfg.get("rib_enabled")
        else None,
    }


@router.get("/status", summary="État de l'abonnement payant")
async def billing_status(user: User = Depends(current_manager)) -> dict:
    """Abonnement Stripe en cours, s'il y en a un. Dégradable."""
    data = await alice_client.billing("GET", "status", user.id, strict=False)
    return data or {"stripe_enabled": False, "has_subscription": False}


@router.get("/plans", summary="Offres auxquelles souscrire")
async def available_plans(user: User = Depends(current_manager)) -> list:
    """Les plans « fonds » vendables, et eux seuls.

    ⚠️ Le filtrage par produit est fait par la console : demander la liste sans dire qui
    l'on est ferait apparaître les offres des produits frères dans cet écran.
    """
    data = await alice_client.billing("GET", "available-plans", user.id, strict=False)
    return data if isinstance(data, list) else []


class _PlanIn(BaseModel):
    plan_id: str | None = None


def _unavailable(exc: AliceUnavailable) -> HTTPException:
    # 503 et non 500 : la demande était valide, c'est l'aval qui manque. Le message est
    # celui que l'utilisateur lira, jamais un « Erreur » nu.
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


@router.post("/checkout", summary="Payer par carte ou prélèvement SEPA")
async def checkout(body: _PlanIn | None = None, user: User = Depends(current_manager)) -> dict:
    """Ouvre une session de paiement et rend l'adresse où le gestionnaire la termine."""
    payload: dict = {"currency": "eur"}
    if body and body.plan_id:
        payload["plan_id"] = body.plan_id
    try:
        return await alice_client.billing("POST", "checkout", user.id, json=payload) or {}
    except AliceUnavailable as exc:
        raise _unavailable(exc)


@router.post("/portal", summary="Gérer son moyen de paiement")
async def portal(user: User = Depends(current_manager)) -> dict:
    """Le portail où l'on change sa carte, consulte ses reçus, résilie."""
    try:
        return await alice_client.billing("POST", "portal", user.id) or {}
    except AliceUnavailable as exc:
        raise _unavailable(exc)


@router.post("/declare-transfer", summary="Déclarer un paiement par virement")
async def declare_transfer(user: User = Depends(current_manager)) -> dict:
    """Le gestionnaire signale avoir viré : la console attend et rapproche.

    ⚠️ CETTE DÉCLARATION NE VAUT PAS PAIEMENT et ne débloque rien par elle-même. C'est une
    annonce, rapprochée ensuite par la console avec le vrai mouvement bancaire.
    """
    try:
        return await alice_client.billing("POST", "declare-transfer", user.id) or {}
    except AliceUnavailable as exc:
        raise _unavailable(exc)


@router.post("/cancel-transfer", summary="Annuler sa déclaration de virement")
async def cancel_transfer(user: User = Depends(current_manager)) -> dict:
    try:
        return await alice_client.billing("POST", "cancel-transfer", user.id) or {}
    except AliceUnavailable as exc:
        raise _unavailable(exc)


@router.post("/change-plan", summary="Changer d'offre")
async def change_plan(body: _PlanIn, user: User = Depends(current_manager)) -> dict:
    if not body.plan_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Préciser l'offre choisie.")
    try:
        return (
            await alice_client.billing(
                "POST", "change-plan", user.id, json={"plan_id": body.plan_id, "currency": "eur"}
            )
            or {}
        )
    except AliceUnavailable as exc:
        raise _unavailable(exc)


@router.post("/change-plan-preview", summary="Estimer le coût d'un changement d'offre")
async def change_plan_preview(body: _PlanIn, user: User = Depends(current_manager)) -> dict:
    """Le montant au prorata, avant de s'engager. Dégradable : une estimation absente vaut
    mieux qu'un écran de changement d'offre inaccessible."""
    if not body.plan_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Préciser l'offre choisie.")
    data = await alice_client.billing(
        "POST",
        "change-plan-preview",
        user.id,
        json={"plan_id": body.plan_id, "currency": "eur"},
        strict=False,
    )
    return data or {}


@router.get("/invoices", summary="Mes factures d'abonnement")
async def invoices(user: User = Depends(current_manager)) -> list:
    return await alice_client.invoices(user.id)


@router.get("/invoices/{invoice_id}/pdf", summary="Le PDF d'une facture")
async def invoice_pdf(invoice_id: str, user: User = Depends(current_manager)) -> Response:
    """⚠️ L'IDENTIFIANT DU GESTIONNAIRE EST CELUI DE LA SESSION, jamais un paramètre. La
    console range ses factures par gestionnaire : accepter un identifiant venu de l'appel
    laisserait lire la facture d'un autre fonds en changeant un chiffre dans l'adresse."""
    found = await alice_client.invoice_pdf(user.id, invoice_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Facture introuvable.")
    content, disposition = found
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )


@router.get("/payments", summary="Historique des paiements")
async def payments(user: User = Depends(current_manager)) -> list:
    data = await alice_client.billing("GET", "payments", user.id, strict=False)
    return data if isinstance(data, list) else []
