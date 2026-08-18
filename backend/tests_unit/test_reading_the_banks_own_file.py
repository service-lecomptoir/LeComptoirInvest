"""CAMT.053: the five readings that, taken the wrong way, move somebody's money.

🔴 A PARSER OF SOMEBODY ELSE'S FORMAT IS WHERE SILENT ERRORS COME FROM, because the input is
never wrong on our side: the bank's file is authoritative, and any misreading looks like the
bank said it. These five are the ones that cost money rather than merely failing:

  * the VALUE date and the booking date are different days, and this product accrues interest
    on the value date;
  * `CdtDbtInd` decides whether money came IN or went OUT;
  * a batched entry bundles several transfers, each with its own reference and payer;
  * a reversal is money that came in and went straight back out;
  * a line that cannot be read must be REPORTED, never dropped.

The last one is the quiet one. A statement short of an entry reconciles to a figure that is
wrong and looks right.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core import camt

IBAN = "FR7630006000011234567890189"


def _document(
    entries: str, namespace: str = "urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"
) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Document xmlns="{namespace}"><BkToCstmrStmt><Stmt>'
        f"<Acct><Id><IBAN>{IBAN}</IBAN></Id></Acct>{entries}"
        "</Stmt></BkToCstmrStmt></Document>"
    )


class TestTheDateThatCarriesInterest:
    def test_the_value_date_wins_over_the_booking_date(self):
        """🔴 THE TWO ARE NOT THE SAME DAY. Taking the booking date would shift every accrual
        by the settlement delay — two or three days per movement, on every loan the fund
        holds, silently."""
        parsed = camt.parse(
            _document(
                "<Ntry><Amt Ccy='EUR'>1000.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>"
                "<BookgDt><Dt>2026-03-05</Dt></BookgDt>"
                "<ValDt><Dt>2026-03-03</Dt></ValDt></Ntry>"
            )
        )
        assert parsed.lines[0].value_date == date(2026, 3, 3)

    def test_the_booking_date_is_used_only_when_there_is_no_value_date(self):
        parsed = camt.parse(
            _document(
                "<Ntry><Amt Ccy='EUR'>1000.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>"
                "<BookgDt><Dt>2026-03-05</Dt></BookgDt></Ntry>"
            )
        )
        assert parsed.lines[0].value_date == date(2026, 3, 5)

    def test_an_entry_with_no_usable_date_is_refused_and_named(self):
        parsed = camt.parse(
            _document(
                "<Ntry><Amt Ccy='EUR'>1000.00</Amt><CdtDbtInd>CRDT</CdtDbtInd></Ntry>"
            )
        )
        assert parsed.lines == []
        assert "aucune date" in parsed.refused[0]


class TestTheDirectionOfTheMoney:
    def test_a_credit_is_money_in_and_a_debit_is_money_out(self):
        parsed = camt.parse(
            _document(
                "<Ntry><Amt Ccy='EUR'>1000.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>"
                "<ValDt><Dt>2026-03-03</Dt></ValDt></Ntry>"
                "<Ntry><Amt Ccy='EUR'>400.00</Amt><CdtDbtInd>DBIT</CdtDbtInd>"
                "<ValDt><Dt>2026-03-04</Dt></ValDt></Ntry>"
            )
        )
        assert [line.direction for line in parsed.lines] == ["in", "out"]

    def test_an_unreadable_direction_is_refused_rather_than_assumed(self):
        """⚠️ DEFAULTING TO « IN » WOULD BE THE FLATTERING GUESS: the treasury would show
        money the fund never received, and it would balance on this side."""
        parsed = camt.parse(
            _document(
                "<Ntry><Amt Ccy='EUR'>1000.00</Amt><CdtDbtInd>XXXX</CdtDbtInd>"
                "<ValDt><Dt>2026-03-03</Dt></ValDt></Ntry>"
            )
        )
        assert parsed.lines == []
        assert "sens du mouvement" in parsed.refused[0]


class TestABatchedEntryIsSplit:
    def test_each_transfer_keeps_its_own_amount_and_reference(self):
        """🔴 SUMMING THEM WOULD MERGE SEVERAL INVESTORS INTO ONE LINE, and the matching
        would fail on all of them at once — or attribute the lot to whoever the first
        reference names."""
        parsed = camt.parse(
            _document(
                "<Ntry><Amt Ccy='EUR'>30000.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>"
                "<ValDt><Dt>2026-03-04</Dt></ValDt><NtryRef>LOT-1</NtryRef><NtryDtls>"
                "<TxDtls><Amt Ccy='EUR'>20000.00</Amt><Refs><EndToEndId>E2E-1</EndToEndId></Refs>"
                "<RmtInf><Ustrd>INV-AAA</Ustrd></RmtInf></TxDtls>"
                "<TxDtls><Amt Ccy='EUR'>10000.00</Amt><Refs><EndToEndId>E2E-2</EndToEndId></Refs>"
                "<RmtInf><Ustrd>INV-BBB</Ustrd></RmtInf></TxDtls>"
                "</NtryDtls></Ntry>"
            )
        )
        assert [line.amount for line in parsed.lines] == [
            Decimal("20000.00"),
            Decimal("10000.00"),
        ]
        assert [line.external_id for line in parsed.lines] == ["E2E-1", "E2E-2"]
        assert [line.label for line in parsed.lines] == ["INV-AAA", "INV-BBB"]

    def test_a_single_detail_takes_the_entry_amount_when_it_carries_none(self):
        parsed = camt.parse(
            _document(
                "<Ntry><Amt Ccy='EUR'>50000.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>"
                "<ValDt><Dt>2026-03-03</Dt></ValDt><NtryRef>REF-A</NtryRef><NtryDtls>"
                "<TxDtls><RmtInf><Ustrd>INV7K2M9QX</Ustrd></RmtInf>"
                "<RltdPties><Dbtr><Nm>ALPHANOR RAYMONDE</Nm></Dbtr></RltdPties>"
                "</TxDtls></NtryDtls></Ntry>"
            )
        )
        [line] = parsed.lines
        assert line.amount == Decimal("50000.00")
        assert line.external_id == "REF-A"
        assert line.counterparty_name == "ALPHANOR RAYMONDE"


class TestWhatMustNotBeCounted:
    def test_a_reversal_is_skipped_and_said(self):
        """⚠️ Counting it credits an investor with a payment their bank recalled."""
        parsed = camt.parse(
            _document(
                "<Ntry><Amt Ccy='EUR'>9999.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>"
                "<ValDt><Dt>2026-03-06</Dt></ValDt><RvslInd>true</RvslInd></Ntry>"
            )
        )
        assert parsed.lines == []
        assert "contre-passation" in parsed.refused[0]

    def test_a_refusal_names_its_position_so_somebody_can_look(self):
        """🔴 « 3 lines ignored » is unactionable. Each refusal carries where it was."""
        parsed = camt.parse(
            _document(
                "<Ntry><Amt Ccy='EUR'>1.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>"
                "<ValDt><Dt>2026-03-03</Dt></ValDt></Ntry>"
                "<Ntry><Amt Ccy='EUR'>2.00</Amt><CdtDbtInd>ZZZZ</CdtDbtInd>"
                "<ValDt><Dt>2026-03-03</Dt></ValDt></Ntry>"
            )
        )
        assert len(parsed.lines) == 1
        assert "écriture 2" in parsed.refused[0]


class TestTheFormatItselfMoves:
    def test_any_camt_053_minor_version_is_read(self):
        """⚠️ ISO 20022 ships a new minor version every few years and the tag names do not
        move. Listing the versions seen so far is a list that is wrong the day the bank
        upgrades, on a Monday morning, with a statement nobody can import."""
        for version in ("02", "04", "08"):
            parsed = camt.parse(
                _document(
                    "<Ntry><Amt Ccy='EUR'>1000.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>"
                    "<ValDt><Dt>2026-03-03</Dt></ValDt></Ntry>",
                    namespace=f"urn:iso:std:iso:20022:tech:xsd:camt.053.001.{version}",
                )
            )
            assert len(parsed.lines) == 1, version

    def test_a_file_that_is_not_a_statement_says_so(self):
        parsed = camt.parse("<Document><Something/></Document>")
        assert parsed.lines == []
        assert "CAMT.053" in parsed.refused[0]

    def test_a_broken_file_is_reported_not_raised(self):
        parsed = camt.parse("<Document><unclosed>")
        assert parsed.lines == []
        assert "XML" in parsed.refused[0]
