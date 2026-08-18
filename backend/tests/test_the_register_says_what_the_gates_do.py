"""The register must not tell a manager something the endpoints would refuse.

🔴 A SCREEN THAT DISAGREES WITH THE GATE IS WORSE THAN EITHER ANSWER ALONE. `accepts_money`
on the register read the KYC status by itself, so an acceptance three years past its review
date still showed « accepts money » — while both places that actually move money refused it.
A manager who meets that once stops believing the screen, and from then on believes whichever
of the two agrees with what they wanted to do.

⚠️ AND A REFUSAL HAS TO SAY WHICH ONE IT IS. « Never accepted » means open a file; « the
acceptance is out of date » means review one that already exists. A shared « refused » sends
both to the same wrong place, which is why the register carries the reason and not a flag.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.api.v1.investors import _out
from app.core import eligibility, kyc
from app.core.landlord_kind_values import PERSON
from app.models.investor import Investor

#: The review cycle is measured in months from the acceptance; three years is past any of
#: them, which is the point.
LONG_AGO = date(2021, 1, 1)
TODAY = date(2026, 6, 30)


def _investor(**kwargs) -> Investor:
    base = dict(
        id=uuid.uuid4(),
        kind=PERSON,
        last_name="Bernard",
        kyc_status=kyc.ACCEPTED,
        kyc_risk_level=kyc.RISK_STANDARD,
        kyc_decided_on=TODAY,
    )
    base.update(kwargs)
    return Investor(**base)


def test_a_current_acceptance_reads_as_accepting_money():
    out = _out(_investor(), today=TODAY)
    assert out.accepts_money is True
    assert out.refusal_reason is None


def test_a_stale_acceptance_no_longer_reads_as_accepting_money():
    """🔴 THE DIVERGENCE. Before this, the register said « yes » here and both gates said
    « no »."""
    out = _out(_investor(kyc_decided_on=LONG_AGO), today=TODAY)

    assert out.accepts_money is False
    assert "revue" in out.refusal_reason


def test_the_two_refusals_are_told_apart():
    """« Never accepted » and « out of date » need different actions from the reader."""
    never = _out(_investor(kyc_status=kyc.PENDING, kyc_decided_on=None), today=TODAY)
    stale = _out(_investor(kyc_decided_on=LONG_AGO), today=TODAY)

    assert never.refusal_reason != stale.refusal_reason
    assert "pending" in never.refusal_reason
    assert "revue" in stale.refusal_reason


def test_an_unassessed_investor_shows_no_threshold_and_says_why():
    """⚠️ NOT « NO LIMIT ». The register carries the reason so the gap is actionable rather
    than merely blank."""
    out = _out(_investor(), today=TODAY)

    assert out.category is None
    assert out.warning_threshold is None
    assert "n'a pas été déclarée" in out.threshold_reason


def test_a_declared_capacity_produces_the_threshold_on_the_register():
    out = _out(
        _investor(category=eligibility.RETAIL, loss_bearing_capacity=Decimal("200000")),
        today=TODAY,
    )

    assert out.warning_threshold == Decimal("10000")
    assert out.threshold_reason is None


def test_a_professional_has_no_threshold_and_no_reason():
    """The absence is a fact about them, not a missing assessment."""
    out = _out(_investor(category=eligibility.PROFESSIONAL), today=TODAY)

    assert out.warning_threshold is None
    assert out.threshold_reason is None
