"""Performance: the arithmetic, and the four things it refuses to answer.

🔴 THE FIGURES ARE THE EASY HALF. Any tool can divide distributions by paid-in. What
decides whether a fund report can be trusted is what happens when the answer does not
exist — and there are more of those cases than of the clean one:

  * nothing has come back yet, so no rate exists;
  * everything is still held and nobody valued it, so TVPI cannot be computed;
  * the flows change sign several times, so several rates fit and none is « the » one.

A tool that returned zero, or the edge of its search, or a residual it assumed to be
nothing, would answer all three with a number. Each of those numbers is wrong in the
direction nobody disputes: an under-stated return.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.performance import Flow, internal_rate_of_return, measure

EUR = "EUR"


class TestTheRateItself:
    def test_ten_per_cent_over_one_year(self):
        """The reference case, and the one a reader checks by hand."""
        rate, reason = internal_rate_of_return(
            [
                Flow(date(2025, 1, 1), Decimal("-100000")),
                Flow(date(2026, 1, 1), Decimal("110000")),
            ]
        )
        assert reason is None
        assert abs(rate - Decimal("0.10")) < Decimal("0.0001")

    def test_a_doubling_over_two_years_is_not_fifty_per_cent(self):
        """🔴 THE MISTAKE A SPREADSHEET MAKES. Doubling in two years is 41.4 % a year
        compounded, not 50 %: the second year earns on the first year's gain. A tool that
        divided the total gain by the number of years would over-state every multi-year
        holding, and it would look right."""
        rate, reason = internal_rate_of_return(
            [
                Flow(date(2024, 1, 1), Decimal("-100000")),
                Flow(date(2026, 1, 1), Decimal("200000")),
            ]
        )
        assert reason is None
        assert abs(rate - Decimal("0.4142")) < Decimal("0.001")

    def test_the_dates_matter_not_only_the_amounts(self):
        """Same money in, same money back, five years apart instead of one."""
        early, _ = internal_rate_of_return(
            [
                Flow(date(2025, 1, 1), Decimal("-100000")),
                Flow(date(2026, 1, 1), Decimal("150000")),
            ]
        )
        late, _ = internal_rate_of_return(
            [
                Flow(date(2025, 1, 1), Decimal("-100000")),
                Flow(date(2030, 1, 1), Decimal("150000")),
            ]
        )
        assert early > late
        assert early > Decimal("0.49") and late < Decimal("0.09")

    def test_a_loss_gives_a_negative_rate_not_a_refusal(self):
        """Losing money is an answer, and the report must carry it."""
        rate, reason = internal_rate_of_return(
            [
                Flow(date(2025, 1, 1), Decimal("-100000")),
                Flow(date(2026, 1, 1), Decimal("80000")),
            ]
        )
        assert reason is None
        assert rate < 0


class TestWhatItRefusesToAnswer:
    def test_nothing_has_come_back_yet(self):
        """⚠️ NOT ZERO, AND NOT MINUS A HUNDRED PER CENT. An investor who paid in last month
        and has received nothing has no rate of return: the question has no solution yet,
        and « 0 % » would read as a fund that earns nothing."""
        rate, reason = internal_rate_of_return(
            [
                Flow(date(2025, 1, 1), Decimal("-100000")),
                Flow(date(2025, 6, 1), Decimal("-50000")),
            ]
        )
        assert rate is None
        assert "même sens" in reason

    def test_a_single_movement_has_no_rate(self):
        rate, reason = internal_rate_of_return(
            [Flow(date(2025, 1, 1), Decimal("-100000"))]
        )
        assert rate is None
        assert "deux mouvements" in reason

    def test_everything_on_one_day_has_no_annualised_rate(self):
        """A duration of zero cannot carry an annualised anything."""
        rate, reason = internal_rate_of_return(
            [
                Flow(date(2025, 1, 1), Decimal("-100000")),
                Flow(date(2025, 1, 1), Decimal("120000")),
            ]
        )
        assert rate is None
        assert "durée nulle" in reason


class TestTheValuationItDoesNotInvent:
    def test_without_a_valuation_tvpi_is_unavailable_never_equal_to_dpi(self):
        """🔴 THE ERROR THAT WOULD NEVER BE DISPUTED. Treating what is still held as worth
        nothing makes TVPI equal DPI, which for an open fund under-states it by the whole
        residual. Nobody queries a return that looks too low."""
        got = measure(
            currency=EUR,
            as_of=date(2026, 1, 1),
            flows=[
                Flow(date(2025, 1, 1), Decimal("-100000")),
                Flow(date(2026, 1, 1), Decimal("30000")),
            ],
        )
        assert got.dpi == Decimal("0.3")
        assert got.tvpi is None
        assert got.rvpi is None
        assert got.irr_is_realised_only is True
        assert "valorisation" in got.unavailable_reason

    def test_a_valuation_supplied_completes_every_figure(self):
        """100 000 in, 30 000 back, 90 000 still held: 1.2× and 20 % a year."""
        got = measure(
            currency=EUR,
            as_of=date(2026, 1, 1),
            flows=[
                Flow(date(2025, 1, 1), Decimal("-100000")),
                Flow(date(2026, 1, 1), Decimal("30000")),
            ],
            residual_value=Decimal("90000"),
        )
        assert got.dpi == Decimal("0.3")
        assert got.rvpi == Decimal("0.9")
        assert got.tvpi == Decimal("1.2")
        assert got.moic == got.tvpi
        assert got.irr_is_realised_only is False
        assert abs(got.irr - Decimal("0.20")) < Decimal("0.001")

    def test_no_money_in_is_said_rather_than_divided_by_zero(self):
        got = measure(currency=EUR, as_of=date(2026, 1, 1), flows=[])
        assert got.paid_in == Decimal("0")
        assert got.dpi is None
        assert "Aucun versement" in got.unavailable_reason


class TestTheSignConvention:
    def test_paid_in_and_distributed_read_the_investors_side(self):
        """⚠️ THE SIGN IS THE INVESTOR'S. Reading the fund's books instead would give a
        plausible rate of the wrong sign, and nothing on the screen would look odd."""
        got = measure(
            currency=EUR,
            as_of=date(2026, 1, 1),
            flows=[
                Flow(date(2025, 1, 1), Decimal("-60000")),
                Flow(date(2025, 7, 1), Decimal("-40000")),
                Flow(date(2026, 1, 1), Decimal("25000")),
            ],
        )
        assert got.paid_in == Decimal("100000")
        assert got.distributed == Decimal("25000")
