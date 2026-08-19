"""The notice a fund sends, and the two things about it nobody would notice being wrong.

🔴 THE LANGUAGE IS THE READER'S, AND ONLY A TWO-LANGUAGE TEST SEES IT. A manager clicks and
an investor reads. Rendering the letter from the caller's `Accept-Language` - which is right
for every other sentence this product writes - sends a French demand to a British investor,
and the product looks perfectly healthy: the figures, the reference and the date are all
correct. So these guards always set the CALLER to one language and the INVESTOR to another,
and check that the letter followed the investor.

🔴 AND A REFUSED SEND MUST LEAVE `notified_on` ALONE. `LateCall.never_notified` is what tells
a fund « we never wrote to them » apart from « they are late ». A mailer that swallowed a
failure while the route marked the call as notified would erase that distinction, and the
fund would chase an investor for a letter that never left.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core import i18n, instruments, kyc
from app.core.landlord_kind_values import PERSON
from app.models.fund import Fund
from app.models.investor import Investor
from app.models.subscription import Subscription
from app.models.treasury import IN, BankMovement, CapitalCall, Contribution
from app.models.user import INVESTOR, User
from app.services import mailer, notice_service

CURRENCY = "EUR"
IBAN = "FR7630006000011111111111111"
CALLED_ON = date(2026, 1, 10)
DUE_ON = date(2026, 2, 10)
LATE_ON = date(2026, 3, 12)


async def _setup(
    db,
    *,
    investor_locale: str | None = None,
    account_locale: str | None = None,
    rate: float | None = None,
    paid: str = "0",
) -> CapitalCall:
    fund = Fund(id=uuid.uuid4(), name="Le Comptoir Un", currency=CURRENCY, iban=IBAN)
    db.add(fund)

    user = None
    if account_locale is not None:
        user = User(
            id=uuid.uuid4(),
            email="lecteur@investisseur.test",
            hashed_password="x",
            account_name="Lecteur",
            role=INVESTOR,
            locale=account_locale,
        )
        db.add(user)
        await db.flush()

    investor = Investor(
        id=uuid.uuid4(),
        kind=PERSON,
        last_name="Bernard",
        email="bernard@investisseur.test",
        kyc_status=kyc.ACCEPTED,
        locale=investor_locale,
        user_id=user.id if user else None,
    )
    db.add(investor)
    await db.flush()

    subscription = Subscription(
        id=uuid.uuid4(),
        fund_id=fund.id,
        investor_id=investor.id,
        instrument=instruments.EQUITY,
        amount=Decimal("50000"),
        currency=CURRENCY,
        signed_on=CALLED_ON,
    )
    db.add(subscription)
    await db.flush()

    call = CapitalCall(
        id=uuid.uuid4(),
        subscription_id=subscription.id,
        reference="LCI-2026-0001",
        amount=Decimal("10000"),
        currency=CURRENCY,
        called_on=CALLED_ON,
        due_on=DUE_ON,
        late_interest_rate=rate,
    )
    db.add(call)
    await db.flush()

    if Decimal(paid) > 0:
        movement = BankMovement(
            id=uuid.uuid4(),
            account_iban=IBAN,
            direction=IN,
            amount=Decimal(paid),
            currency=CURRENCY,
            value_date=DUE_ON,
        )
        db.add(movement)
        await db.flush()
        db.add(
            Contribution(
                id=uuid.uuid4(),
                bank_movement_id=movement.id,
                subscription_id=subscription.id,
                capital_call_id=call.id,
                amount=Decimal(paid),
                currency=CURRENCY,
            )
        )
        await db.flush()
    return call


async def test_the_letter_follows_the_investor_and_not_the_manager_who_clicked(db):
    """🔴 THE ONE A SINGLE-LANGUAGE TEST CANNOT SEE.

    The caller is reading French - which is what the middleware would have set from their
    browser - and the investor stated English. The letter has to be English.
    """
    call = await _setup(db, investor_locale="en")

    with i18n.use_lang(
        "fr"
    ):  # the manager's own language, as the middleware would set it
        prepared = await notice_service.prepare(db, call=call, as_of=CALLED_ON)

    assert prepared.language == "en"
    assert "Capital call" in prepared.notice.subject
    assert "Reference to quote" in prepared.notice.body
    assert "Référence" not in prepared.notice.body


async def test_the_caller_s_language_comes_back_afterwards(db):
    """⚠️ `use_lang` RESTORES, and the letter must not leave the caller in the investor's
    language: the very next refusal on the same request would come back in it."""
    call = await _setup(db, investor_locale="en")

    with i18n.use_lang("fr"):
        await notice_service.prepare(db, call=call, as_of=CALLED_ON)
        assert i18n.current_lang() == "fr"


async def test_their_own_account_outranks_what_the_fund_typed_for_them(db):
    """They set it themselves in the switcher. The fund's note is what to use when they
    never said anything, not a way to overrule them."""
    call = await _setup(db, investor_locale="fr", account_locale="en")

    prepared = await notice_service.prepare(db, call=call, as_of=CALLED_ON)

    assert prepared.language == "en"


async def test_an_investor_who_never_said_gets_the_default_and_not_a_guess(db):
    """⚠️ NOTHING IS DERIVED FROM THE COUNTRY. Belgium is French and Dutch, Switzerland
    French, German and Italian, Canada French and English. A guess from a country is wrong
    for a whole nation of investors at once, and it is wrong silently."""
    call = await _setup(db)

    prepared = await notice_service.prepare(db, call=call, as_of=CALLED_ON)

    assert prepared.language == i18n.DEFAULT


async def test_a_reminder_asks_for_what_is_still_missing_not_the_whole_call(db):
    """🔴 PARTIAL PAYMENT IS NORMAL. An investor who paid four fifths and receives a demand
    for the whole reads it as « they lost my transfer », and the next thing they do is stop
    trusting the fund's figures rather than pay the fifth."""
    call = await _setup(db, paid="8000")
    call.notified_on = CALLED_ON
    await db.flush()

    prepared = await notice_service.prepare(
        db, call=call, as_of=LATE_ON, kind=notice_service.REMINDER
    )

    assert "2000.00 EUR" in prepared.notice.body
    assert "10000.00 EUR" not in prepared.notice.body
    assert "8000.00 EUR" in prepared.notice.body  # what did arrive is acknowledged


async def test_a_reminder_is_refused_on_a_call_that_was_never_notified(db):
    """The fund is late, not the investor. Chasing somebody for a letter never sent is the
    defect `never_notified` exists to make visible; writing the letter would hide it."""
    call = await _setup(db)

    with pytest.raises(ValueError) as caught:
        await notice_service.prepare(
            db, call=call, as_of=LATE_ON, kind=notice_service.REMINDER
        )

    assert "premier avis" in str(caught.value)


async def test_a_settled_call_never_produces_a_reminder(db):
    """A reminder for a paid call tells an investor their payment was not seen, which is the
    one message that makes them stop paying on the reference."""
    call = await _setup(db, paid="10000")
    call.notified_on = CALLED_ON
    await db.flush()

    with pytest.raises(ValueError):
        await notice_service.prepare(
            db, call=call, as_of=LATE_ON, kind=notice_service.REMINDER
        )


async def test_the_rate_stated_is_the_one_the_call_carries(db):
    """⚠️ NOT A CURRENT SETTING. `late_interest_rate` is stored per call so that changing a
    fund-wide parameter cannot rewrite what an investor was told when they received the
    demand, retroactively and for every call already out."""
    call = await _setup(db, rate=0.05)

    prepared = await notice_service.prepare(db, call=call, as_of=CALLED_ON)

    assert "5.00 %" in prepared.notice.body


async def test_no_rate_means_the_letter_says_nothing_about_interest(db):
    """NULL is a decision the call records, not an omission. A letter that threatened
    interest anyway would announce a charge the fund cannot make."""
    call = await _setup(db, rate=None)

    prepared = await notice_service.prepare(db, call=call, as_of=CALLED_ON)

    assert "%" not in prepared.notice.body


async def test_the_reference_is_in_the_letter_and_so_is_the_vehicles_own_account(db):
    """🔴 THE REFERENCE IS THE WHOLE MECHANISM. With no payment provider, it is the only
    thing tying a transfer to a call. And the account is the CALL'S OWN VEHICLE'S: naming
    the platform's first IBAN would tell an investor in fund B to pay fund A, and the
    transfer would succeed."""
    call = await _setup(db)

    prepared = await notice_service.prepare(db, call=call, as_of=CALLED_ON)

    assert "LCI-2026-0001" in prepared.notice.body
    assert IBAN in prepared.notice.body
    assert prepared.notice.qr_payload and "LCI-2026-0001" in prepared.notice.qr_payload


async def test_a_send_that_the_relay_refuses_records_nothing(db, monkeypatch):
    """🔴 THE GUARD THIS WHOLE DESIGN EXISTS FOR.

    With no SMTP configured the mailer raises, and `notified_on` has to stay None. A call
    marked as notified that nobody received turns the fund's own omission into an accusation
    against the investor, and the chasing list stops showing the one row that needs acting on.
    """
    call = await _setup(db)

    async def _not_configured() -> bool:
        return False

    monkeypatch.setattr(mailer, "is_configured", _not_configured)

    with pytest.raises(mailer.MailNotSent):
        await notice_service.send(db, call=call, as_of=CALLED_ON)

    assert call.notified_on is None
    assert call.last_reminded_on is None


async def test_a_send_that_goes_out_records_that_it_did(db, monkeypatch):
    """And the other half: once the relay took it, the call stops being « never notified »."""
    call = await _setup(db)
    sent: list[dict] = []

    async def _accept(*, to, subject, body):
        sent.append({"to": to, "subject": subject, "body": body})

    async def _configured() -> bool:
        return True

    monkeypatch.setattr(mailer, "is_configured", _configured)
    monkeypatch.setattr(mailer, "send", _accept)

    prepared = await notice_service.send(db, call=call, as_of=CALLED_ON)

    assert prepared.kind == notice_service.FIRST_NOTICE
    assert call.notified_on == CALLED_ON
    assert sent and sent[0]["to"] == "bernard@investisseur.test"


async def test_an_investor_with_no_address_is_refused_before_anything_is_recorded(db):
    """An address is not optional for a letter. Refusing here beats marking a notice as
    sent into the void, which is the same false record by another route."""
    call = await _setup(db)
    investor_id = (await notice_service._facts(db, call, as_of=CALLED_ON))[1].id
    investor = await db.get(Investor, investor_id)
    investor.email = None
    await db.flush()

    with pytest.raises(mailer.MailNotSent):
        await notice_service.send(db, call=call, as_of=CALLED_ON)

    assert call.notified_on is None
