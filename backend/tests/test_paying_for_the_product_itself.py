"""L'abonnement AU LOGICIEL, à ne pas confondre avec les souscriptions AUX FONDS.

🔴 CE QUI EST GARDÉ ICI. Quatre décisions dont aucune ne se voit à l'écran quand elle est
prise à l'envers :

  * un investisseur n'a pas d'abonnement à ce produit et ne doit rien pouvoir en lire ;
  * l'identité du payeur vient de la SESSION, jamais d'un paramètre d'appel : une facture
    se lirait sinon en changeant un identifiant dans l'adresse ;
  * une console absente rend « non piloté », JAMAIS un plan gratuit : traduire « je ne sais
    pas » par « c'est offert » accorde un droit que personne n'a donné ;
  * une action de PAIEMENT qui échoue remonte une erreur, quand une LECTURE qui échoue se
    dégrade. Un gestionnaire persuadé d'avoir payé sans l'avoir fait est un dossier de
    support ; un montant affiché « inconnu » n'est qu'un écran incomplet.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1 import billing as billing_api
from app.core.security import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.models.user import INVESTOR, MANAGER, User
from app.services import alice_client


@pytest.fixture
async def client(db):
    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://invest.test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


async def _user(db, role: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"{role}-{uuid.uuid4().hex[:8]}@fonds.test",
        hashed_password=hash_password("Motdepasse-1234"),
        account_name="Meridian Capital",
        role=role,
    )
    db.add(user)
    await db.flush()
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}


async def test_an_investor_has_no_subscription_to_read(client, db):
    """Le porteur de parts paie SON fonds, pas le logiciel. L'écran ne le concerne pas."""
    investor = await _user(db, INVESTOR)
    for path in ("/api/v1/billing", "/api/v1/billing/invoices", "/api/v1/billing/plans"):
        resp = await client.get(path, headers=_auth(investor))
        assert resp.status_code == 403, f"{path} a répondu {resp.status_code}"


async def test_no_console_means_unknown_and_never_free(client, db, monkeypatch):
    """🔴 « Pas de réponse » ne se traduit pas par « offre gratuite ».

    Sans console, l'écran doit dire qu'il n'est pas piloté. Le piège serait de rendre un
    `plan_name` vide avec un prix à zéro : l'utilisateur y lirait un abonnement gratuit,
    et personne ne le lui a accordé.
    """

    async def _absent(_user_id):
        return None

    monkeypatch.setattr(alice_client, "get_license", _absent)
    manager = await _user(db, MANAGER)
    body = (await client.get("/api/v1/billing", headers=_auth(manager))).json()
    assert body["managed"] is False
    assert body["plan_name"] is None
    assert body["monthly_price"] is None


async def test_the_payer_is_the_session_never_a_parameter(client, db, monkeypatch):
    """L'identifiant transmis à la console est celui du porteur du jeton.

    ⚠️ La garde vérifie l'ARGUMENT REÇU par le client, pas seulement le code de réponse :
    un endpoint qui accepterait un `user_id` en requête répondrait 200 tout pareil, en
    lisant la facture d'un autre fonds.
    """
    seen: list[uuid.UUID] = []

    async def _capture(user_id):
        seen.append(user_id)
        return []

    monkeypatch.setattr(alice_client, "invoices", _capture)
    manager = await _user(db, MANAGER)
    other = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/billing/invoices?user_id={other}", headers=_auth(manager)
    )
    assert resp.status_code == 200
    assert seen == [manager.id], "l'identifiant du payeur ne vient pas de la session"


async def test_a_read_degrades_but_a_payment_refuses(client, db, monkeypatch):
    """La console tombe : la lecture rend une liste vide, le paiement rend une erreur."""

    async def _down(method, action, user_id, *, json=None, strict=True):
        if strict:
            raise alice_client.AliceUnavailable("Le service d'abonnement est indisponible.")
        return None

    monkeypatch.setattr(alice_client, "billing", _down)
    manager = await _user(db, MANAGER)

    lecture = await client.get("/api/v1/billing/plans", headers=_auth(manager))
    assert lecture.status_code == 200 and lecture.json() == []

    paiement = await client.post("/api/v1/billing/checkout", headers=_auth(manager), json={})
    assert paiement.status_code == 503
    # Jamais un « Erreur » nu : le message est celui que l'utilisateur lira.
    assert "indisponible" in paiement.json()["detail"].lower()


async def test_the_fund_limit_reads_alices_shared_field_name(monkeypatch):
    """⚠️ Alice nomme cette limite `property_limit` POUR TOUS LES PRODUITS.

    C'est le contrat inter-produits. La renommer côté console casserait les trois autres ;
    la lire sous un autre nom ici la rendrait toujours vide, et un plan limité passerait
    pour un plan illimité.
    """
    info = billing_api._as_info(
        {"plan_name": "Fonds Pro", "monthly_price": 149.0, "property_limit": 3}
    )
    assert info.fund_limit == 3
    assert info.managed is True
