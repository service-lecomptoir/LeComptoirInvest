"""A subscriber is never sold a second subscription, and is told so in clear.

The owner's recipe of 9 Nov 2026: « Changer de moyen de paiement » opened Alice's Checkout
for a licence that already held a running Stripe subscription. A second subscription
opened, the licence followed it and the first one kept charging. Alice refuses that
Checkout since (409, `X-Refusal: already_subscribed`, her sentence in French only); this
product says it in the reader's language, naming its own button (« Gérer mon abonnement »),
and keeps it a 409: something to do on this page, never « the service is unavailable ».
"""

from __future__ import annotations

import pytest

from app.api.v1 import billing as billing_api
from app.core.i18n import use_lang
from app.services.alice_client import AliceRefused


@pytest.mark.parametrize(
    ("lang", "said"),
    [("fr", "Gérer mon abonnement"), ("en", "Manage my subscription")],
)
def test_the_second_checkout_is_refused_in_clear(lang, said):
    refused = AliceRefused(
        "Votre abonnement est déjà actif", 409, refusal="already_subscribed"
    )
    with use_lang(lang):
        answer = billing_api._unavailable(refused)
    assert answer.status_code == 409
    assert said in answer.detail
