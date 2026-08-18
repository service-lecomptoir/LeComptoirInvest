"""The arithmetic under every distribution: what is owed, and how a sum is split.

These are the two places a fund loses money silently. An interest figure that is slightly
wrong is never questioned, because nobody recomputes their lender's coupon by hand. And a
split that rounds each share independently keeps a few cents per investor, which reconciles
to nothing and is never noticed at any single line.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core import accrual
from app.core.instruments import LoanTerms


class TestInterestIsCountedInDays:
    def test_a_full_year_at_eight_percent(self):
        assert accrual.interest_accrued(
            principal=Decimal("250000"),
            rate=0.08,
            since=date(2026, 1, 1),
            until=date(2027, 1, 1),
            currency="EUR",
        ) == Decimal("20000.00")

    def test_a_half_year_is_not_half_of_it(self):
        """181 days, not 182.5. The convention is stated, and it is applied."""
        assert accrual.interest_accrued(
            principal=Decimal("250000"),
            rate=0.08,
            since=date(2026, 1, 1),
            until=date(2026, 7, 1),
            currency="EUR",
        ) == Decimal("9917.81")

    def test_a_date_before_the_start_owes_nothing_rather_than_a_negative(self):
        assert accrual.interest_accrued(
            principal=Decimal("250000"),
            rate=0.08,
            since=date(2026, 7, 1),
            until=date(2026, 1, 1),
            currency="EUR",
        ) == Decimal("0")


class TestWhatCannotBeComputedIsRefused:
    def test_an_amortising_loan_answers_with_a_reason_not_a_figure(self):
        """A straight line invented here would look exactly like an amount owed."""
        due = accrual.amount_due(
            terms=LoanTerms(rate=0.08, term_months=24, bullet=False),
            principal_contributed=Decimal("250000"),
            currency="EUR",
            drawn_on=date(2026, 1, 1),
            matures_on=date(2028, 1, 1),
            as_of=date(2026, 7, 1),
        )
        assert not due.is_known
        assert due.interest == Decimal("0") and due.capital == Decimal("0")
        assert "échéancier" in due.unavailable_reason

    def test_a_loan_with_no_terms_at_all_owes_nothing_knowable(self):
        due = accrual.amount_due(
            terms=None,
            principal_contributed=Decimal("250000"),
            currency="EUR",
            drawn_on=date(2026, 1, 1),
            matures_on=None,
            as_of=date(2026, 7, 1),
        )
        assert not due.is_known


class TestCapitalIsOwedAtMaturityAndNotBefore:
    def _due(self, as_of: date, **kw):
        return accrual.amount_due(
            terms=LoanTerms(rate=0.08, term_months=24),
            principal_contributed=Decimal("250000"),
            currency="EUR",
            drawn_on=date(2026, 1, 1),
            matures_on=date(2028, 1, 1),
            as_of=as_of,
            **kw,
        )

    def test_before_maturity_only_interest_is_due(self):
        """Treating principal as due early puts the fund in a self-declared default, and
        freezes every distribution to subscribers on a fact that is not true."""
        assert self._due(date(2027, 1, 1)).capital == Decimal("0")

    def test_at_maturity_the_principal_falls_due(self):
        assert self._due(date(2028, 1, 1)).capital == Decimal("250000.00")

    def test_what_was_already_served_is_not_owed_twice(self):
        due = self._due(date(2028, 1, 1), interest_already_paid=Decimal("20000"))
        assert due.interest == Decimal(
            "20000.00"
        )  # two years accrued, one already paid

    def test_serving_ahead_of_the_accrual_does_not_make_the_lender_a_debtor(self):
        due = self._due(date(2027, 1, 1), interest_already_paid=Decimal("50000"))
        assert due.interest == Decimal("0")


class TestASplitLosesNothing:
    @pytest.mark.parametrize(
        "amount,parts,currency",
        [
            ("100.00", 3, "EUR"),
            ("0.05", 3, "EUR"),
            ("1000", 3, "XOF"),
            ("1", 7, "XOF"),
            ("999999.99", 11, "EUR"),
        ],
    )
    def test_the_parts_sum_back_to_the_whole(self, amount, parts, currency):
        """The few cents a naive split keeps are the fund's, and they reconcile to nothing."""
        shares = accrual.allocate(Decimal(amount), [Decimal(1)] * parts, currency)
        assert sum(shares) == Decimal(amount)

    def test_a_currency_without_decimals_is_split_in_whole_units(self):
        shares = accrual.allocate(Decimal("1000"), [Decimal(1)] * 3, "XOF")
        assert shares == [Decimal("334"), Decimal("333"), Decimal("333")]
        assert all(s == s.to_integral_value() for s in shares)

    def test_weights_are_honoured(self):
        assert accrual.allocate(
            Decimal("100.00"), [Decimal("70"), Decimal("30")], "EUR"
        ) == [Decimal("70.00"), Decimal("30.00")]

    def test_the_same_input_always_gives_the_same_split(self):
        """A proposal shown on screen must be the proposal recorded."""
        args = (Decimal("100.00"), [Decimal(1)] * 3, "EUR")
        assert accrual.allocate(*args) == accrual.allocate(*args)

    def test_nothing_to_split_gives_zeros_rather_than_an_error(self):
        assert (
            accrual.allocate(Decimal("0"), [Decimal(1)] * 3, "EUR")
            == [Decimal("0")] * 3
        )
        assert (
            accrual.allocate(Decimal("100"), [Decimal("0")] * 3, "EUR")
            == [Decimal("0")] * 3
        )
