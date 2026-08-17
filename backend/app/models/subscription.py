"""What an investor has committed, what they asked to commit, and how a loan becomes equity.

🔴 A REQUEST IS NOT AN ENGAGEMENT, and the portal is the reason this has to be said in the
schema rather than in a screen. « Investir en ligne » means an investor fills in a form. If
that form wrote a `Subscription`, anyone with a login could create a binding commitment of
the fund — and an investor whose KYC verdict is `a_verifier` could do it before anybody had
looked at who they are.

So the portal writes a `SubscriptionRequest`: an intent, dated, from a named investor. The
fund then accepts it, and only that acceptance produces a `Subscription`. The two rows both
survive: what was asked, and what was agreed, are different facts and one of them is the
one that binds.

It is the same distinction the fund makes four times over on the money side — engagement,
call, contribution, distribution — and for the same reason: each step reads like the next
one until the day they differ.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core import instruments
from app.models.base import Base, TimestampMixin, uuid_pk

#: Waiting for the fund to decide.
REQUEST_PENDING = "en_attente"
#: Accepted: a `Subscription` was created from it.
REQUEST_ACCEPTED = "acceptee"
#: Refused, with a reason.
REQUEST_REFUSED = "refusee"
#: Withdrawn by the investor before the fund decided.
REQUEST_WITHDRAWN = "retiree"

REQUEST_STATUSES: tuple[str, ...] = (
    REQUEST_PENDING,
    REQUEST_ACCEPTED,
    REQUEST_REFUSED,
    REQUEST_WITHDRAWN,
)


class SubscriptionRequest(Base, TimestampMixin):
    """An investor's intent, expressed from the portal. Binds nobody until accepted."""

    __tablename__ = "subscription_requests"

    id: Mapped[uuid.UUID] = uuid_pk()
    investor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("investors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: `instruments.EQUITY` or `instruments.LOAN`.
    instrument: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    #: ⚠️ CARRIED ON EVERY AMOUNT, never assumed from the fund. An investor subscribing in
    #: XOF is committing XOF, and the treasury invariant holds per currency: an amount whose
    #: currency lives somewhere else is an amount that will one day be added to another.
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    requested_on: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=REQUEST_PENDING, server_default=REQUEST_PENDING
    )
    decided_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    decided_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: Required to refuse. An investor told « non » with no reason cannot correct anything.
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: The engagement this request produced, once accepted. NULL while pending, and NULL for
    #: ever if refused — which is exactly what makes the two rows worth keeping apart.
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )

    #: WHICH VERSION OF THE INFORMATION DOCUMENT THE INVESTOR HAD IN FRONT OF THEM. Recorded
    #: at the moment of the request, not looked up later: the document changes, and « what
    #: they were shown » is only answerable if it was written down then.
    information_document_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    def __repr__(self) -> str:
        return f"<SubscriptionRequest {self.amount} {self.currency} [{self.status}]>"


class Subscription(Base, TimestampMixin):
    """What the investor has COMMITTED, and under which instrument.

    ⚠️ THIS IS THE PROMISE, NEVER THE CASH. `amount` is what was engaged; what actually
    arrived is the sum of the contributions attached to it. Reading this column as money the
    fund holds is the first of the four confusions, and the one that has funds calling
    capital they have already spent.
    """

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = uuid_pk()
    investor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("investors.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    #: `instruments.EQUITY` or `instruments.LOAN`. Decides everything else about this row —
    #: the terms it carries, when it is served, whether it can convert.
    instrument: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    signed_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: When the engagement stops — the loan's maturity, or the fund's own term.
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    #: `LoanTerms` or `EquityTerms`, as JSON. Two shapes in one column DELIBERATELY: they are
    #: alternatives, never both, and two nullable column sets would let a row carry an
    #: interest rate AND a carried interest — a state no contract describes.
    #: `instruments.terms_kind` says which shape belongs to which instrument.
    terms: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    #: Set when this subscription was closed by a CONVERSION rather than by repayment. The
    #: row is never deleted: it is the history of what the investor held until that date,
    #: and a converted loan that vanished would make every past statement unexplainable.
    converted_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    investor: Mapped["object"] = relationship("Investor", lazy="select")

    @property
    def is_open(self) -> bool:
        """Still running? A converted subscription is closed, whatever its end date."""
        return self.converted_on is None

    @property
    def distribution_rank(self) -> int:
        """Where this holding sits in a voluntary distribution. Lower is served first."""
        return instruments.distribution_rank(self.instrument)

    @property
    def liquidation_rank(self) -> int:
        """Where it sits in a wind-down. NOT the same question, and not ours to choose."""
        return instruments.liquidation_rank(self.instrument)

    def __repr__(self) -> str:
        return f"<Subscription {self.amount} {self.currency} {self.instrument}>"


class SubscriptionConversion(Base, TimestampMixin):
    """A loan becoming a subscription. An EVENT, never an edit.

    🔴 THE SUBSCRIPTION IS NOT MUTATED, AND THAT IS THE WHOLE POINT. Changing `instrument`
    on the existing row would rewrite history: every statement ever sent said the investor
    held a loan, every past distribution was ranked as debt, and the row would now claim it
    had always been equity. A conversion closes one holding and opens another, on a date,
    and both survive.

    ⚠️ THE MONEY ALREADY CONTRIBUTED DOES NOT MOVE. What converts is the instrument
    governing the FUTURE — the rank, the terms, what is owed from here. Contributions stay
    attached to the loan they were paid into, because that is where they were paid.

    ⚠️ AND ACCRUED INTEREST IS A REAL AMOUNT. On a bullet loan it is every coupon since the
    drawdown. `LoanTerms.interest_converts` says whether it becomes equity too or is paid in
    cash; leaving it implicit is how a lender silently loses a year of interest at conversion.
    """

    __tablename__ = "subscription_conversions"

    id: Mapped[uuid.UUID] = uuid_pk()
    #: The loan that is closing.
    from_subscription_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    #: The subscription that opens. Created by the conversion, never before it.
    to_subscription_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    converted_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: The capital that carried over.
    principal_converted: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    #: The interest accrued to the conversion date, and whether it converted or was paid.
    interest_converted: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    interest_paid_in_cash: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    #: The terms agreed for the conversion — price per unit, ratio, discount. Free-form
    #: because a convertible's terms are negotiated, not enumerated.
    conversion_terms: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(150), nullable=True)

    def __repr__(self) -> str:
        return f"<SubscriptionConversion {self.principal_converted} {self.currency} on {self.converted_on}>"
