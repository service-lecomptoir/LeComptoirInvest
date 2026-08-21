"""An investor, and the verdict that decides whether the fund takes their money.

THE REGISTER IS THE FOUNDATION. Nothing attaches to anything until an investor exists, and
it is the first thing an investor asks to see about themselves. Subscriptions, calls,
contributions and distributions all hang from here.

TWO FACTS SIT ON THIS RECORD AND ARE OFTEN CONFUSED:
  * WHAT the investor is — a natural person or a legal one. It decides the documents
    required, the tax treatment of what they receive, and how they sign.
  * WHETHER the fund may do business with them — the KYC verdict. It decides whether money
    is accepted at all.

An investor can be perfectly well identified and refused; another can be accepted and have
no subscription yet. Storing the two in one column, as « active », loses both.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core import kyc
from app.models.base import Base, TimestampMixin, uuid_pk


class Investor(Base, TimestampMixin):
    __tablename__ = "investors"

    id: Mapped[uuid.UUID] = uuid_pk()
    #: 🔴 THE MANAGEMENT COMPANY THAT OWNS THIS ROW.
    #:
    #: This product had no owner column at all: every manager of an installation saw the
    #: WHOLE register. That was not a defect of the code, it WAS the model, and it only
    #: became visible the day a second account recognised somebody else's projects on
    #: their screen.
    #:
    #: ⚠️ IT IS STAMPED AUTOMATICALLY by `core.firm_scope`, at flush: setting it at each
    #: call site would mean forgetting it once, and a row without a firm belongs to
    #: nobody. See migration 0010.
    firm_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )

    # ── What this investor IS ──────────────────────────────────────────────────
    #: 'personne' or 'societe'. THE SAME TWO WORDS AS THE REST OF THE HOUSE, deliberately:
    #: Le Comptoir Immo stores exactly these on its landlords, and an investor is very often
    #: a landlord too. A second vocabulary ('individual'/'company') would have to be
    #: translated at every point the two products meet, and would be translated wrongly once.
    kind: Mapped[str] = mapped_column(String(10), nullable=False)

    #: Natural person: given and family name. Legal person: leave empty.
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    #: Legal person: the registered name. Natural person: empty.
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: SIREN, company number, national identity number — whatever their country issues.
    #: Free-form on purpose: this fund does not decide the shape of a foreign register.
    national_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    #: Date of birth (natural person) or of incorporation (legal person). Required by every
    #: identification regime, and by nothing else here.
    born_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: ISO 3166-1 alpha-2. Feeds the risk assessment and the default currency, and it is a
    #: CODE, never the country written out: the sister product filled in the words on
    #: eighteen records out of eighteen and left every code-keyed rule reading « nowhere ».
    country_code: Mapped[str | None] = mapped_column(
        String(2), nullable=True, index=True
    )

    # ── Money out ──────────────────────────────────────────────────────────────
    #: Where distributions are paid. ENCRYPTED AT REST: an investor table is a list of
    #: names, addresses and IBANs, the single most useful file to steal in this product, and
    #: a backup or a mis-scoped dump exposes all of it if it is stored in clear.
    #:
    #: Never written directly — use the `iban` property, which keeps the fingerprint in step.
    iban_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: A salted, one-way fingerprint of the same IBAN, so reconciliation can ask « do we know
    #: this payer? » WITHOUT decrypting anything. Fernet output differs on every encryption
    #: of the same value, so an encrypted column cannot be searched — this one can, and is
    #: indexed for it. It reveals nothing on its own, and the salt is the deployment's own
    #: secret so a stolen table cannot be tested against a list of candidate IBANs.
    iban_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    bic: Mapped[str | None] = mapped_column(String(11), nullable=True)

    #: THE IBAN THE INVESTOR SENDS MONEY TO, when the bank issues one per counterparty.
    #:
    #: This is the single biggest reconciliation win available on a transfer-only rail: a
    #: transfer arriving on this account IS this investor's, with no label to decode and no
    #: reference to have been mistyped. Everything else in the import — matching a reference,
    #: comparing a payer name — is what has to be done when this is empty.
    virtual_iban: Mapped[str | None] = mapped_column(
        String(34), nullable=True, unique=True
    )
    #: The currency this investor is paid in. May differ from the fund's own: an investor
    #: subscribing in XOF is paid in XOF, and the treasury invariant holds per currency.
    payout_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    # ── The verdict ────────────────────────────────────────────────────────────
    #: One of `kyc.STATUSES`. STARTS AT `a_verifier`, and that default is the safe one:
    #: `kyc.blocks_money` refuses anything that is not `accepte`, so a record created and
    #: forgotten cannot fund anything.
    kyc_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=kyc.PENDING, server_default=kyc.PENDING
    )
    #: 'standard' or 'high'. Drives how long an acceptance stays current (36 months
    #: against 12) and how heavy the file has to be.
    kyc_risk_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=kyc.RISK_STANDARD,
        server_default=kyc.RISK_STANDARD,
    )
    #: WHO decided, and WHEN. An acceptance with no author is a value in a column, and the
    #: first question anyone reviewing the fund asks is who decided, not what was decided.
    kyc_decided_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    kyc_decided_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: Required for a refusal or a return to review: without it the decision can neither be
    #: reconsidered nor explained to the investor.
    kyc_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Politically exposed person. A fact recorded on its own rather than folded into the
    #: risk level, because the risk level can be raised for other causes and folding them
    #: together loses which one applied.
    #: 🔴 WHICH PROTECTIONS APPLY TO THIS INVESTOR, and it is not the same question as the
    #: KYC verdict. KYC says whether the fund may deal with them at all; this says how much
    #: they may commit before a warning is owed, and whether a reflection period runs.
    #:
    #: ⚠️ NO SERVER DEFAULT, and that is deliberate: an unrecorded category is read as
    #: PROTECTED by `eligibility.is_protected`, which is the safe direction. Writing
    #: « retail » into the column would make the same reading look like a decision somebody
    #: took, and the day the default is changed every silent row changes with it.
    category: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    #: What the investor declared they could afford to lose, as the warning threshold is
    #: computed on a share of it. NULL means undeclared, never zero and never unlimited:
    #: `eligibility.warning_threshold` refuses to produce a figure rather than guess one.
    loss_bearing_capacity: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )

    is_pep: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: Where the money comes from, in the investor's own words. Not a dropdown: the value of
    #: this field is that it can be inconsistent with the rest of the file.
    source_of_funds: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: THE ACCOUNT THAT SIGNS IN FOR THIS INVESTOR, when there is one. NULL is a normal,
    #: permanent state: a paper subscriber, an estate, a company whose signatory has not
    #: been given access. Their holdings, their statements and their money all exist without
    #: it — which is the whole reason the login is a separate row.
    #:
    #: ⚠️ Access is NOT the verdict. An investor may sign in, read their portfolio and see
    #: their statements while `kyc_status` refuses their money; and one whose access has
    #: been closed keeps every unit they hold. The two answer different questions, and
    #: `accepts_money` is the only one that gates a contribution.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    #: 🔴 THE LANGUAGE THE FUND WRITES TO THEM IN, and NULL means « they never said ».
    #:
    #: `User.locale` covers the investors who sign in, and most do not: `user_id` above is
    #: nullable, and a capital call notice goes to everybody. Nothing derives this from
    #: `country_code` - Belgium is French and Dutch, Switzerland French, German and Italian,
    #: Canada French and English. A guess from a country is wrong for a whole nation of
    #: investors at once, and it is wrong silently: the letter looks perfectly normal.
    locale: Mapped[str | None] = mapped_column(String(5), nullable=True)

    documents: Mapped[list["InvestorDocument"]] = relationship(
        "InvestorDocument", back_populates="investor", cascade="all, delete-orphan"
    )

    @property
    def iban(self) -> str | None:
        """The IBAN in clear, decrypted on read. None when unset or unreadable."""
        from app.core import crypto

        return crypto.decrypt(self.iban_encrypted)

    @iban.setter
    def iban(self, value: str | None) -> None:
        """Encrypt AND fingerprint in one move.

        The two are set together, always, because a fingerprint that lags behind the value
        is worse than no fingerprint: reconciliation would match an incoming transfer to the
        investor's OLD account and attribute somebody's money on the strength of it.
        """
        from app.core import crypto

        cleaned = "".join((value or "").split()).upper() or None
        self.iban_encrypted = crypto.encrypt(cleaned)
        self.iban_fingerprint = crypto.fingerprint(cleaned)

    @property
    def display_name(self) -> str:
        """The name to print. Company name first when there is one."""
        if (self.company_name or "").strip():
            return self.company_name.strip()
        parts = [(self.first_name or "").strip(), (self.last_name or "").strip()]
        return " ".join(p for p in parts if p)

    @property
    def accepts_money(self) -> bool:
        """May the fund take money from this investor?

        Reads `kyc.blocks_money` and does not re-implement it. The rule has one home, and
        every screen and endpoint asks that home — a second spelling is how one place comes
        to accept what another refuses, and the one that accepts is always the one holding
        the money.
        """
        return kyc.accepts_money(self.kyc_status)

    @property
    def kyc_review_due_on(self) -> date | None:
        """When this acceptance stops being current. Derived, never stored.

        A stored due date freezes the review cycle of the day it was written: change the
        cycle and every investor accepted before that day keeps the old one for ever.
        """
        return kyc.review_due_on(self.kyc_decided_on, self.kyc_risk_level)

    def __repr__(self) -> str:
        return f"<Investor {self.display_name} [{self.kyc_status}]>"


class InvestorDocument(Base, TimestampMixin):
    """A piece in the investor's file: identity, proof of address, articles, and so on.

    ⚠️ `expires_on` IS WHY THIS IS A TABLE AND NOT A FOLDER. A passport that lapsed last
    spring does not merely make the file untidy: it makes the acceptance that rested on it
    stale, and the investor moves to `a_revoir`. A document store that cannot say when a
    piece dies cannot support the verdict that rests on it.
    """

    __tablename__ = "investor_documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    investor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("investors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: What the piece IS ('piece_identite', 'justificatif_domicile', 'statuts', 'kbis'…).
    #: Free-form: the documents a foreign investor can produce are not this fund's to
    #: enumerate in advance.
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: When the piece was issued, and when it stops being valid. The second one drives the
    #: staleness of the whole file.
    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    #: Who filed it. An unattributed document proves nothing about who checked it.
    collected_by: Mapped[str | None] = mapped_column(String(150), nullable=True)

    investor: Mapped["Investor"] = relationship("Investor", back_populates="documents")

    def is_expired(self, today: date) -> bool:
        """Undated pieces never expire, because nobody said they would.

        Deliberately NOT « an undated document is suspect »: inventing an expiry for a
        piece whose date nobody recorded would move investors to review on a fact that was
        never established.
        """
        return self.expires_on is not None and today > self.expires_on

    def __repr__(self) -> str:
        return f"<InvestorDocument {self.kind} exp={self.expires_on}>"
