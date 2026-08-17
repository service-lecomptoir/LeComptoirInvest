"""The four rules nothing else may re-implement, tested without a database.

Each of these decides where somebody's money goes, and each is a pure function precisely so
it can be exercised here rather than through a screen. What is checked is the RULE, not a
run of it: a test that walks an endpoint proves the endpoint, and leaves the rule free to be
re-spelt somewhere else.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.core import instruments, kyc, references
from app.core.matching import (
    BY_PAYER_IBAN,
    BY_REFERENCE,
    BY_VIRTUAL_IBAN,
    UNMATCHED,
    Candidate,
    propose,
)
from app.core.money import Money, total


class TestTheVerdictBlocks:
    """A KYC that stops nothing is a tidy screen beside a fund that took the money anyway."""

    def test_only_an_acceptance_lets_money_in(self):
        assert kyc.blocks_money(kyc.PENDING)
        assert kyc.blocks_money(kyc.REFUSED)
        assert kyc.blocks_money(kyc.REVIEW)
        assert not kyc.blocks_money(kyc.ACCEPTED)

    def test_a_missing_status_blocks(self):
        """« Nobody has looked » must never read as « nothing was found »."""
        assert kyc.blocks_money(None)
        assert kyc.blocks_money("")
        assert kyc.blocks_money("quelque_chose_dinvente")

    def test_an_acceptance_goes_stale_and_a_high_risk_one_goes_stale_sooner(self):
        accepted = date(2026, 1, 1)
        assert not kyc.is_stale(
            kyc.ACCEPTED, accepted, kyc.RISK_STANDARD, date(2028, 6, 1)
        )
        assert kyc.is_stale(kyc.ACCEPTED, accepted, kyc.RISK_HIGH, date(2027, 6, 1))

    def test_a_refusal_without_a_reason_is_refused(self):
        """It could neither be reconsidered nor explained to the investor."""
        with pytest.raises(ValueError):
            kyc.Verdict(
                status=kyc.REFUSED, decided_by="SC", decided_on=date(2026, 8, 18)
            )


class TestTheOrderOfRepayment:
    def test_a_lender_is_served_before_a_subscriber(self):
        assert instruments.distribution_rank(
            instruments.LOAN
        ) < instruments.distribution_rank(instruments.EQUITY)

    def test_the_liquidation_order_is_the_law_and_not_a_preference(self):
        """Two constants holding the same two words, and they must stay two.

        One is imposed by insolvency law, the other is the fund's contract. They agree today
        because the contract chose the usual order — not because they are the same fact. A
        future change to the distribution order must not silently rewrite the other.
        """
        assert instruments.LIQUIDATION_RANK == (instruments.LOAN, instruments.EQUITY)
        assert instruments.LIQUIDATION_RANK is not instruments.DISTRIBUTION_ORDER

    def test_an_unknown_instrument_raises_rather_than_being_served_last(self):
        with pytest.raises(ValueError):
            instruments.distribution_rank("obligation_lunaire")

    def test_equity_never_becomes_debt(self):
        """One direction only: the reverse would move an investor ahead of the others in a
        wind-down after the fact, which is a preference, and preferences get unwound."""
        assert instruments.may_convert(
            instruments.LOAN, instruments.LoanTerms(rate=0.08, term_months=24)
        )
        assert not instruments.may_convert(
            instruments.EQUITY, instruments.EquityTerms()
        )


class TestMoneyRefusesToMix:
    def test_two_currencies_never_add(self):
        with pytest.raises(ValueError):
            Money(Decimal("1000"), "EUR") + Money(Decimal("1000"), "XOF")

    def test_a_mixed_list_totals_per_currency_and_never_into_one_number(self):
        got = total(
            [
                Money(Decimal("10"), "EUR"),
                Money(Decimal("5"), "EUR"),
                Money(Decimal("3000"), "XOF"),
            ]
        )
        assert got["EUR"].amount == Decimal("15.00")
        assert got["XOF"].amount == Decimal("3000")

    def test_the_cfa_franc_has_no_centime(self):
        """Showing « 3 000 000,00 » to an Ivorian investor writes a figure their bank never
        does, and Côte d'Ivoire is already a market of this house."""
        assert Money(Decimal("3000000.4"), "XOF").amount == Decimal("3000000")
        assert Money(Decimal("10.005"), "EUR").amount == Decimal("10.01")


class TestTheReferenceSurvivesAHuman:
    def test_a_generated_reference_validates(self):
        for _ in range(50):
            assert references.is_valid(references.generate())

    def test_it_is_found_inside_whatever_a_bank_label_contains(self):
        ref = references.generate()
        for label in (
            f"VIR {ref} SOUSCRIPTION",
            ref.lower().replace("-", ""),
            f"SEPA {ref}/AOUT",
        ):
            assert references.normalise(label) == ref, label

    def test_a_single_typo_is_rejected_rather_than_matched_to_someone_else(self):
        ref = references.generate()
        body = ref[4:-1]
        wrong = ("3" if body[0] != "3" else "4") + body[1:]
        assert not references.is_valid(f"INV-{wrong}{ref[-1]}")

    def test_two_transposed_characters_are_rejected(self):
        """The other mistake a human actually makes when copying a code."""
        ref = references.generate()
        body = ref[4:-1]
        if body[0] == body[1]:
            return
        swapped = body[1] + body[0] + body[2:]
        assert not references.is_valid(f"INV-{swapped}{ref[-1]}")

    def test_the_euro_only_qr_refuses_another_currency(self):
        with pytest.raises(ValueError):
            references.epc_qr_payload(
                beneficiary="Le Comptoir Invest",
                iban="FR7630006000011234567890189",
                amount="1000",
                currency="XOF",
                reference="INV-ABCDEFG",
            )


class TestWhoseMoneyIsThis:
    RAY = Candidate(
        "i1",
        "Raymonde Alphanor",
        virtual_iban="FR7612345000011111111111111",
        iban_fingerprint="fp-ray",
        open_call_references={"INV-G6C846P": "call-1"},
    )
    ERIC = Candidate("i2", "Eric Chacha", iban_fingerprint="fp-eric")

    def _propose(self, **kw):
        kw.setdefault("received_on_iban", None)
        kw.setdefault("label", None)
        kw.setdefault("payer_name", None)
        kw.setdefault("payer_iban_fingerprint", None)
        kw.setdefault("amount", Decimal("50000"))
        kw.setdefault("candidates", [self.RAY, self.ERIC])
        return propose(**kw)

    def test_the_account_it_arrived_on_needs_no_interpretation(self):
        got = self._propose(received_on_iban="FR76 1234 5000 0111 1111 1111 111")
        assert got.basis == BY_VIRTUAL_IBAN and got.investor_id == "i1"

    def test_a_reference_identifies_the_call_not_merely_the_investor(self):
        got = self._propose(label="VIR INV-G6C846P AOUT", payer_name="R. Alphanor")
        assert got.basis == BY_REFERENCE and got.capital_call_id == "call-1"

    def test_a_payer_account_identifies_the_investor_and_NOT_the_call(self):
        """A lender with four open calls pays them all from the same account."""
        got = self._propose(payer_iban_fingerprint="fp-eric")
        assert got.basis == BY_PAYER_IBAN and got.investor_id == "i2"
        assert got.capital_call_id is None

    def test_a_payer_who_is_not_the_investor_is_flagged(self):
        got = self._propose(label="INV-G6C846P", payer_name="SCI DU PORT")
        assert got.third_party_payer is True

    def test_the_same_person_spelt_differently_is_not_flagged(self):
        """A warning that is usually wrong is one nobody reads on the day it is right."""
        got = self._propose(label="INV-G6C846P", payer_name="ALPHANOR RAYMONDE")
        assert got.third_party_payer is False

    def test_an_account_shared_by_two_investors_is_refused_not_guessed(self):
        other = Candidate("i3", "Guerard Larame", iban_fingerprint="fp-ray")
        got = self._propose(
            payer_iban_fingerprint="fp-ray", candidates=[self.RAY, other]
        )
        assert got.basis == UNMATCHED and got.investor_id is None

    def test_the_amount_alone_identifies_nobody(self):
        """Two investors called for 50 000 € in one week is not a coincidence, it is a
        Tuesday."""
        got = self._propose(amount=Decimal("50000"))
        assert got.basis == UNMATCHED

    def test_an_unidentified_line_says_what_was_looked_at(self):
        got = self._propose(label="VIR INV-ZZZZZZZ")
        assert got.explanation and "INV" in got.explanation
