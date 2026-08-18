"""The money: what was asked, what the bank says arrived, and what was paid back.

BANK TRANSFER, AND ONLY BANK TRANSFER (user, 18 August 2026). The fund learns that money
exists from its BANK STATEMENT, and the whole difficulty is attribution: a transfer carries
an amount, a date, a label and the name of whoever ordered it, and none of those is an
investor identifier.

⛔ ONLINE PAYMENT WAS MODELLED AND THEN REMOVED, deliberately. The reasoning is kept
because it is the expensive part, and because the question comes back:

  * a TRANSFER IS IRREVOCABLE once executed. A card payment is charged back; a SEPA direct
    debit is revoked by a consumer within eight weeks, with no reason given. On sums the
    fund may already have deployed into a project, that window is a risk nothing
    compensates: the units would be issued against money that can still go home;
  * the FEES are wrong at this scale. 1.4 % to 2.9 % on a card is 1 400 to 2 900 euros lost
    on a single 100 000 euro subscription, and card ceilings do not reach these amounts;
  * and a provider does not pay the payments, it pays a BATCH: several investors at once,
    net of commission, on a later date. The statement line would never equal any one
    subscription, so a contribution could not be anchored on it without being short by the
    fees and wrong about who paid what.

WHAT ONLINE PAYMENT WOULD REALLY HAVE BOUGHT is not the payment but the RECONCILIATION, and
all of it is obtainable on this rail: a virtual IBAN per investor removes label matching
entirely, a pre-filled transfer (EPC QR code, or payment initiation) removes the mistyped
reference, and a statement import removes the keying. None of them changes how money travels.

🔴 A MOVEMENT IS NOT A CONTRIBUTION, and this is the same distinction the portal forced
between a request and an engagement. `BankMovement` is what the bank says. `Contribution` is
what the fund DECIDED it means. Money can sit unattributed for weeks — a wrong reference, a
payment from a spouse's account, a company paying for its director — and an outil that only
stored « contributions » would have to either invent an attribution or lose the money.

⚠️ AND A THIRD-PARTY PAYMENT IS A FINDING, NOT A DETAIL. Money arriving from someone other
than the investor is exactly what identification rules exist to catch. It must be visible as
such, never silently attributed because the amount happened to match.

⚠️ ON LARGE AMOUNTS, PARTIAL IS THE NORM. A commitment is called in tranches, one transfer
may cover several calls, and one call may be met by several transfers. So the link between a
movement and a subscription carries an AMOUNT, and neither side is one-to-one.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, uuid_pk

#: Money the fund received.
IN = "in"
#: Money the fund sent.
OUT = "out"


class BankMovement(Base, TimestampMixin):
    """A line of the bank statement, recorded as the bank stated it.

    NOTHING HERE IS INTERPRETED. The label is the bank's label, the payer name is the one
    on the transfer, the amount is what moved. Interpretation lives in `Contribution` and
    `Distribution`, and keeping the two apart is what lets an attribution be corrected
    without rewriting what the bank said — which is the one thing in this table that is
    not the fund's to change.
    """

    __tablename__ = "bank_movements"
    __table_args__ = (
        #: One statement line, once. Re-importing a statement is normal — an operator
        #: reruns yesterday's file — and duplicating a 200 000 € transfer would make the
        #: treasury invariant fail in the direction that looks like good news.
        Index(
            "uq_bank_movement_external",
            "account_iban",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    #: The fund's own account this line belongs to. A fund holding several currencies holds
    #: several accounts, and the treasury invariant is per currency.
    account_iban: Mapped[str] = mapped_column(String(34), nullable=False, index=True)
    #: The bank's own identifier for the line, when the statement carries one (CAMT.053
    #: `EndToEndId`, or an entry reference). NULL for a movement keyed in by hand.
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)

    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    #: When the bank booked it. NOT when it was imported, and not when it was attributed.
    value_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    #: The transfer's label, verbatim. This is where the investor's reference should be,
    #: and where it very often is not.
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Who ordered the transfer, as the bank names them. ⚠️ Compared against the investor:
    #: a mismatch is a third-party payment and has to be looked at, not explained away.
    counterparty_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    counterparty_iban: Mapped[str | None] = mapped_column(String(34), nullable=True)

    def __repr__(self) -> str:
        return f"<BankMovement {self.direction} {self.amount} {self.currency} {self.value_date}>"


class CapitalCall(Base, TimestampMixin):
    """What the fund ASKED an investor to pay, and by when.

    ⚠️ A CALL IS NOT MONEY. It is a demand, and the second of the four amounts this fund
    must never conflate. A screen that adds up calls and presents the total as available
    cash is the reason funds call capital they have already spent.

    THE REFERENCE IS THE WHOLE MECHANISM. With no payment provider, the only thing tying a
    transfer to a call is the text the investor copies into the label. It has to be unique,
    short enough to be typed without error, and printed on the call notice — and the
    uniqueness has to be enforced by the DATABASE, because a duplicate reference silently
    attributes one investor's money to another.
    """

    __tablename__ = "capital_calls"
    __table_args__ = (Index("uq_capital_call_reference", "reference", unique=True),)

    id: Mapped[uuid.UUID] = uuid_pk()
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    #: What the investor writes in the transfer label.
    reference: Mapped[str] = mapped_column(String(35), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    called_on: Mapped[date] = mapped_column(Date, nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    #: When the call notice was actually sent, and by what means. A call nobody received is
    #: not a late investor, it is an unsent letter, and the two must not look alike.
    notified_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    def __repr__(self) -> str:
        return f"<CapitalCall {self.reference} {self.amount} {self.currency} due {self.due_on}>"


class Contribution(Base, TimestampMixin):
    """Money RECEIVED and attributed: this part of that transfer, against this subscription.

    🔴 NEVER KEYED IN ALONE. A contribution exists only as the attribution of a bank
    movement, and `bank_movement_id` is not nullable for that reason. A contribution with no
    movement behind it is a figure somebody typed, and on a fund it is indistinguishable
    from money that arrived — until the account is reconciled and it is far too late to ask
    who wrote it.

    ⚠️ PARTIAL BOTH WAYS. `amount` is the share of the movement attributed here, so one
    transfer can be split across several subscriptions and one call can be met by several
    transfers. Neither side is one-to-one, and forcing either would make an operator round
    a real amount to fit the model.
    """

    __tablename__ = "contributions"

    id: Mapped[uuid.UUID] = uuid_pk()
    bank_movement_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("bank_movements.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    #: The call this settles, when it settles one. NULL for money paid ahead of any call.
    capital_call_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("capital_calls.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, index=True)

    #: ⚠️ THE MONEY CAME FROM SOMEBODY ELSE. Set when the payer on the transfer is not the
    #: investor: a spouse, a company paying for its director, a notary. Recorded as a fact
    #: rather than blocked, because it is often perfectly legitimate — and never inferred
    #: away, because it is precisely what identification rules exist to surface.
    third_party_payer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    third_party_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Who attributed it, and when. An attribution is a decision: on a transfer whose label
    #: is wrong, somebody chose which investor it belonged to.
    attributed_by: Mapped[str | None] = mapped_column(String(150), nullable=True)

    bank_movement: Mapped["BankMovement"] = relationship("BankMovement", lazy="select")

    def __repr__(self) -> str:
        return f"<Contribution {self.amount} {self.currency}>"


class Distribution(Base, TimestampMixin):
    """Money PAID BACK to an investor, split between capital and income.

    🔴 THE SPLIT IS THE POINT, AND IT IS NOT PRESENTATION. Returning capital is not a
    return: the investor gets their own money back, and it is not taxed as income. Interest,
    a preferred return, a share of gain — those are. A distribution stored as one figure
    produces a tax statement that is wrong for every investor who receives one, and wrong in
    a way none of them can detect from the amount.

    THE TOTAL IS DERIVED, never stored beside its parts: a stored total is a third number
    that can disagree with the two it sums.
    """

    __tablename__ = "distributions"

    id: Mapped[uuid.UUID] = uuid_pk()
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    #: The outgoing transfer, once it has left. NULL while the distribution is decided but
    #: not yet paid — a state that exists and must not look like a payment.
    bank_movement_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("bank_movements.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    #: The investor's own money coming back. Reduces what the fund still owes them.
    capital_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    #: What they earned: interest on a loan, preferred return or gain on a subscription.
    income_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, index=True)

    decided_on: Mapped[date] = mapped_column(Date, nullable=False)
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    #: Tax withheld at source, where the investor's country or the fund's requires it. Held
    #: apart from `income_amount`: what the investor EARNED and what they RECEIVED differ by
    #: exactly this, and their statement needs both.
    withholding_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )

    @property
    def gross_amount(self) -> Decimal:
        """What was distributed before withholding. Derived, never stored."""
        return (self.capital_amount or Decimal("0")) + (
            self.income_amount or Decimal("0")
        )

    @property
    def net_paid(self) -> Decimal:
        """What actually reached the investor's account."""
        return self.gross_amount - (self.withholding_amount or Decimal("0"))

    def __repr__(self) -> str:
        return f"<Distribution cap={self.capital_amount} inc={self.income_amount} {self.currency}>"
