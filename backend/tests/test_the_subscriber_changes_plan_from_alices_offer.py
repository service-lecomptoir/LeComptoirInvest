"""The subscriber changes plan from Alice's offer (the owner, 11 Oct 2026).

« Je ne vois pas la possibilité de changer d'offre comme pour Immo [...] faudra les
aligner. » This relay serves Alice's offer (`/internal/billing/plan-offer`), her preview,
her change and the request to the team; the subscriber alone acts, and each act is
journaled. The rules (which plans, the VAT, a cap under the use refused) are Alice's.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1 import billing
from app.services.alice_client import AliceUnavailable

SALE_HELPER = "_sale_accepted"
HOLDS = "holds_the_licence"


def _user(subscriber: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="titulaire@example.test",
        account_name="Titulaire",
        **{HOLDS: subscriber},
    )


@pytest.fixture
def alice(monkeypatch):
    calls: list[tuple] = []
    answers: dict = {
        "plan-offer": {"mode": "change", "plans": [], "current_kind": "catalogue"},
        "change-plan": {
            "status": "ok",
            "plan_name": "Équipe",
            "previous_plan_name": "Solo",
        },
        "change-plan-preview": {"action": "change", "proration_amount": 12.5},
        "change-request": {"status": "received", "id": "r1"},
        "checkout": {"url": "https://checkout.stripe.test/x"},
    }
    journal: list[tuple] = []

    async def billing_call(method, action, user_id, json=None, strict=True):
        calls.append((method, action, json))
        answer = answers[action]
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def no_terms(*args, **kwargs):
        calls.append(("terms",))

    async def journaled(user, action, details):
        journal.append((action, details))

    monkeypatch.setattr(billing.alice_client, "billing", billing_call)
    monkeypatch.setattr(billing, SALE_HELPER, no_terms)
    monkeypatch.setattr(billing, "_journal", journaled)
    return SimpleNamespace(calls=calls, answers=answers, journal=journal)


def _plan(plan_id: str = "p1"):
    fields = billing._PlanIn.model_fields
    return billing._PlanIn(
        **{"plan_id": plan_id, **({"cgv": None} if "cgv" in fields else {})}
    )


REQUEST = SimpleNamespace(headers={}, client=SimpleNamespace(host="1.2.3.4"))


async def test_the_offer_says_who_may_act_on_it(alice):
    assert (await billing.plan_offer(user=_user()))["can_change"] is True
    assert (await billing.plan_offer(user=_user(False)))["can_change"] is False


async def test_a_silent_alice_is_said_never_an_invented_offer(alice):
    alice.answers["plan-offer"] = AliceUnavailable(
        "Le service d'abonnement est indisponible."
    )
    with pytest.raises(HTTPException) as silent:
        await billing.plan_offer(user=_user())
    assert silent.value.status_code == 503


async def test_only_the_subscriber_previews_changes_or_asks(alice):
    other = _user(False)
    for route in (
        billing.change_plan_preview(_plan(), user=other),
        billing.change_plan(_plan(), REQUEST, user=other),
        billing.change_request(billing._ChangeRequestIn(), user=other),
    ):
        with pytest.raises(HTTPException) as refused:
            await route
        assert refused.value.status_code == 403
    assert alice.calls == [] and alice.journal == []


async def test_a_change_takes_the_terms_first_and_is_journaled(alice):
    answer = await billing.change_plan(_plan(), REQUEST, user=_user())
    assert answer["plan_name"] == "Équipe"
    assert alice.calls[0] == ("terms",) and alice.calls[1][1] == "change-plan"
    assert alice.journal == [
        ("subscription.plan_changed", {"plan_id": "p1", "from": "Solo", "to": "Équipe"})
    ]


async def test_alice_s_refusal_reaches_the_page_and_nothing_is_journaled(alice):
    sentence = "La formule Solo permet 5 unités et vous en avez 25 : réduisez d'abord."
    alice.answers["change-plan"] = AliceUnavailable(sentence)
    with pytest.raises(HTTPException) as refused:
        await billing.change_plan(_plan(), REQUEST, user=_user())
    assert refused.value.detail == sentence
    assert alice.journal == []


async def test_asking_the_team_is_relayed_with_who_asks_and_journaled(alice):
    await billing.change_request(
        billing._ChangeRequestIn(plan_id="p2", message="Plus grand"), user=_user()
    )
    sent = [c for c in alice.calls if c[1:2] == ("change-request",)][0][2]
    assert sent == {
        "plan_id": "p2",
        "message": "Plus grand",
        "full_name": "Titulaire",
        "email": "titulaire@example.test",
    }
    assert alice.journal == [("subscription.change_requested", {"plan_id": "p2"})]
