"""Eligibility: the cap, the reflection period, and what happens when nobody asked.

🔴 THE FAILURE MODE OF A PROTECTION MUST BE « TOO MUCH PROTECTION ». Every default in this
module leans that way on purpose, and each one is tested here because leaning the other way
is invisible: an investor who was never assessed, never warned and never given a period to
step back looks exactly like one who was cleared.

The three that matter:

  * an unrecorded category is PROTECTED, not exempt — the investor nobody assessed is
    precisely the one the cap is for;
  * an undeclared loss-bearing capacity yields NO THRESHOLD rather than an unlimited one,
    and the caller must refuse instead of proceeding;
  * the reflection period runs from the REQUEST, never from the fund's decision, so a fund
    that answers within the hour cannot bind somebody who has not had their days.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core import eligibility as e


class TestTheThresholdAboveWhichAWarningIsOwed:
    def test_it_is_the_greater_of_the_flat_amount_and_a_share_of_capacity(self):
        """A small saver is not held to five per cent of very little; a larger one is not
        waved through on the flat figure alone."""
        modest = e.warning_threshold(
            category=e.RETAIL, loss_bearing_capacity=Decimal("5000")
        )
        assert modest.amount == e.FLAT_THRESHOLD

        larger = e.warning_threshold(
            category=e.RETAIL, loss_bearing_capacity=Decimal("200000")
        )
        assert larger.amount == Decimal("10000")

    def test_an_undeclared_capacity_gives_no_threshold_and_never_an_unlimited_one(self):
        """🔴 SILENCE IS NOT A LARGE NET WORTH. Reading « undeclared » as « no cap applies »
        would let the one investor nobody assessed commit the most."""
        got = e.warning_threshold(category=e.RETAIL, loss_bearing_capacity=None)
        assert got.amount is None
        assert got.is_known is False
        assert "n'a pas été déclarée" in got.unavailable_reason

    def test_a_professional_has_no_threshold_and_that_is_not_the_same_as_unknown(self):
        got = e.warning_threshold(category=e.PROFESSIONAL, loss_bearing_capacity=None)
        assert got.amount is None
        assert got.is_known is True


class TestConsentIsRequiredOnlyWhereItProtects:
    def test_below_the_threshold_no_consent_is_needed(self):
        needed, reason = e.needs_explicit_consent(
            category=e.RETAIL,
            amount=Decimal("900"),
            loss_bearing_capacity=Decimal("200000"),
        )
        assert needed is False and reason is None

    def test_above_the_threshold_consent_is_required(self):
        needed, reason = e.needs_explicit_consent(
            category=e.RETAIL,
            amount=Decimal("15000"),
            loss_bearing_capacity=Decimal("200000"),
        )
        assert needed is True and reason is None

    def test_an_unmeasurable_threshold_is_reported_and_not_treated_as_met(self):
        """⚠️ THE TRAP. Returning `False` here would read as « no consent needed », which is
        the opposite of what an unmeasured cap means. The caller gets a reason and must
        refuse."""
        needed, reason = e.needs_explicit_consent(
            category=e.RETAIL, amount=Decimal("999999"), loss_bearing_capacity=None
        )
        assert needed is False
        assert reason is not None

    def test_a_professional_needs_none_however_large(self):
        needed, reason = e.needs_explicit_consent(
            category=e.PROFESSIONAL,
            amount=Decimal("5000000"),
            loss_bearing_capacity=None,
        )
        assert needed is False and reason is None


class TestTheCategoryNobodyRecorded:
    def test_an_unknown_category_is_protected(self):
        """🔴 THE DEFAULT THAT DECIDES WHETHER THIS MODULE IS WORTH ANYTHING."""
        assert e.is_protected(None) is True
        assert e.is_protected("") is True

    def test_the_protected_set_is_declared_not_derived_by_exclusion(self):
        """⚠️ A test written as « not professional » answers « unprotected » for every
        category invented after it. The set is enumerated, so a new one must be placed in
        it on purpose."""
        assert e.RETAIL in e.PROTECTED_CATEGORIES
        assert e.PROFESSIONAL not in e.PROTECTED_CATEGORIES
        assert e.SOPHISTICATED not in e.PROTECTED_CATEGORIES


class TestTheReflectionPeriod:
    def test_it_runs_from_the_request_never_from_the_decision(self):
        """🔴 THE DELAY BELONGS TO THE INVESTOR. Starting it at the fund's decision would
        make it depend on how fast the fund works: answer in an hour and the investor is
        bound before they have had their days; answer in a fortnight and it starts late."""
        assert e.reflection_period_ends(
            requested_on=date(2026, 3, 1), category=e.RETAIL
        ) == date(2026, 3, 5)

    def test_a_professional_has_none(self):
        assert (
            e.reflection_period_ends(
                requested_on=date(2026, 3, 1), category=e.PROFESSIONAL
            )
            is None
        )

    def test_binding_inside_the_period_is_refused_with_the_date(self):
        allowed, why = e.may_bind(
            requested_on=date(2026, 3, 1), category=e.RETAIL, on=date(2026, 3, 3)
        )
        assert allowed is False
        assert "2026-03-05" in why

    def test_binding_after_it_is_allowed(self):
        allowed, why = e.may_bind(
            requested_on=date(2026, 3, 1), category=e.RETAIL, on=date(2026, 3, 6)
        )
        assert allowed is True and why is None

    def test_the_last_day_of_the_period_still_protects(self):
        """The boundary belongs to the investor: on the closing day they may still step
        back, and a fund that signed that morning would have taken a day from them."""
        allowed, _ = e.may_bind(
            requested_on=date(2026, 3, 1), category=e.RETAIL, on=date(2026, 3, 5)
        )
        assert allowed is False
