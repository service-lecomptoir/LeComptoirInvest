"""The invoice still to pay, as Alice names it (the owner, 9 Nov 2026).

After the billing start, a subscriber paying by transfer, or with no means of payment, had
nothing on screen between the invoice e-mail and the suspension. Alice serves `invoice_due`
in `/internal/license/{id}`; Invest relays it as she sends it, for the holder's banner.
Measured before: the licence state kept four billing keys and dropped this one.
"""

from __future__ import annotations

from app.api.v1 import billing
from app.services import licence_state

ALICE = {
    "number": "ABO-2027-0001",
    "period_year": 2027,
    "period_month": 1,
    "left_ttc": 120,
    "currency": "eur",
    "due_on": "2027-01-15",
    "overdue": False,
}
RELAYED = {
    "number": "ABO-2027-0001",
    "period_year": 2027,
    "period_month": 1,
    "left_ttc": 120.0,
    "currency": "EUR",
    "due_on": "2027-01-15",
    "overdue": False,
}


def test_the_invoice_alice_names_is_kept_as_she_sends_it():
    state = licence_state.read({"is_blocked": False, "invoice_due": ALICE})
    assert state.invoice_due == RELAYED


def test_the_subscription_relays_it_to_the_banner():
    licence = {"is_blocked": False, "plan_name": "Essentiel", "invoice_due": ALICE}
    assert billing._as_info(licence).invoice_due == RELAYED
    overdue = {**licence, "invoice_due": {**ALICE, "overdue": True}}
    assert billing._as_info(overdue).invoice_due["overdue"] is True


def test_nothing_to_pay_an_older_alice_or_a_malformed_answer_is_none():
    assert licence_state.read({"is_blocked": False}).invoice_due is None
    assert licence_state.read({"invoice_due": None}).invoice_due is None
    for broken in (
        {**ALICE, "number": ""},
        {**ALICE, "period_month": 13},
        {**ALICE, "left_ttc": "120"},
        {**ALICE, "left_ttc": True},
        {**ALICE, "due_on": None},
        {**ALICE, "overdue": "no"},
        "ABO-2027-0001",
    ):
        assert licence_state.read({"invoice_due": broken}).invoice_due is None
