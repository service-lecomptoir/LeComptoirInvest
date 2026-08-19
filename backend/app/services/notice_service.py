"""Writing to an investor: in THEIR language, and recorded only when it actually went out.

🔴 THE LANGUAGE IS THE READER'S, AND THIS IS THE ONLY PLACE IN THE PRODUCT WHERE THAT IS
TRUE. Everywhere else the reader IS the caller, so the middleware's `Accept-Language` is
exactly right. Here a manager clicks and an investor reads. `i18n.use_lang` exists for this,
and until now it had no caller in production - a mechanism with no user is indistinguishable
from a rule nobody applies, which this repository has four of on record.

🔴 AND THE RECORD FOLLOWS THE LETTER, NOT THE CLICK. `notified_on` and `last_reminded_on` are
written ONLY after the relay accepted the message. A call marked as notified that nobody
received is worse than an unsent one: `LateCall.never_notified` is what tells a fund « we
never wrote to them » apart from « they are late », and a false mark turns the fund's own
omission into an accusation against the investor.

⚠️ PREVIEWING IS NOT SENDING. The two are separate functions because a manager reading the
letter before it goes out must not thereby have sent it, and a screen that marked on render
would silence the chasing list for anybody who merely looked.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import i18n, mailer, notices
from app.core.i18n import pick
from app.models.fund import Fund
from app.models.investor import Investor
from app.models.subscription import Subscription
from app.models.treasury import CapitalCall, Contribution
from app.models.user import User
from app.services import call_chasing_service

#: The two letters a fund sends about a call. Named rather than passed as a boolean: a
#: `is_reminder=True` at a call site reads as a formatting option, and these are two
#: different statements to somebody about their money.
FIRST_NOTICE = "first_notice"
REMINDER = "reminder"
KINDS: tuple[str, ...] = (FIRST_NOTICE, REMINDER)


@dataclass(frozen=True)
class PreparedNotice:
    """One letter, its recipient, and the language it was written in."""

    kind: str
    language: str
    to: str | None
    notice: notices.Notice
    #: Whether this installation could send it at all. Carried to the screen so a manager
    #: reads « sending is not set up » before clicking, not after.
    sending_is_configured: bool


async def language_of(db: AsyncSession, investor: Investor) -> str:
    """The language this investor is written to in.

    The order is a decision, not a convenience:

    1. **Their own account's locale**, when they have one. They set it themselves in the
       switcher, and their own choice outranks whatever the fund typed for them.
    2. **`Investor.locale`**, what the fund recorded. Most investors have no portal account.
    3. **The product default.** Not a guess - the language the letters were written in.

    ⚠️ `country_code` IS DELIBERATELY NOT IN THAT LIST. Belgium is French and Dutch,
    Switzerland French, German and Italian, Canada French and English. Deriving a language
    from a country is wrong for a whole nation of investors at once, and it is wrong
    silently: the letter goes out looking perfectly normal.
    """
    if investor.user_id is not None:
        chosen = (
            await db.execute(select(User.locale).where(User.id == investor.user_id))
        ).scalar_one_or_none()
        if chosen:
            return i18n.normalise(chosen)
    if investor.locale:
        return i18n.normalise(investor.locale)
    return i18n.DEFAULT


async def _facts(
    db: AsyncSession, call: CapitalCall, *, as_of: date
) -> tuple[notices.CallFacts, Investor]:
    """Everything the letter needs, gathered once.

    ⚠️ THE ACCOUNT COMES FROM THE CALL'S OWN VEHICLE. Naming the platform's first IBAN would
    tell an investor in fund B to pay fund A, and the transfer would succeed.
    """
    subscription = await db.get(Subscription, call.subscription_id)
    if subscription is None:  # pragma: no cover - RESTRICT on the foreign key
        raise ValueError(
            pick(
                "Cet appel ne porte plus de souscription.",
                "This call no longer carries a subscription.",
            )
        )
    investor = await db.get(Investor, subscription.investor_id)
    if investor is None:  # pragma: no cover - RESTRICT on the foreign key
        raise ValueError(
            pick(
                "Cet appel ne porte plus d'investisseur.",
                "This call no longer carries an investor.",
            )
        )

    fund = (
        await db.get(Fund, subscription.fund_id)
        if subscription.fund_id is not None
        else None
    )
    from app.config import get_settings

    settings = get_settings()
    iban = fund.iban if fund is not None and fund.iban else None
    if iban is None:
        platform = settings.fund_ibans
        iban = platform[0] if platform else None

    received = (
        await db.execute(
            select(func.coalesce(func.sum(Contribution.amount), 0)).where(
                Contribution.capital_call_id == call.id
            )
        )
    ).scalar_one()
    received = Decimal(received)

    late = call_chasing_service.late_interest_on(call, received=received, as_of=as_of)

    return (
        notices.CallFacts(
            investor_name=investor.display_name,
            fund_name=fund.name if fund is not None else settings.APP_NAME,
            reference=call.reference,
            amount=call.amount,
            currency=call.currency,
            due_on=call.due_on,
            iban=iban,
            late_interest_rate=call.late_interest_rate,
            received=received,
            outstanding=call.amount - received,
            late_interest=late,
            as_of=as_of,
        ),
        investor,
    )


async def prepare(
    db: AsyncSession, *, call: CapitalCall, as_of: date, kind: str | None = None
) -> PreparedNotice:
    """Write the letter without sending it, in the investor's language.

    `kind` omitted lets the CALL decide which letter it is: one that has never been notified
    gets the demand, one that has gets the reminder. Asking the caller to choose would let a
    screen send a reminder for a letter that was never sent - the fund's own omission dressed
    up as the investor's lateness.
    """
    facts, investor = await _facts(db, call, as_of=as_of)
    chosen = kind or (REMINDER if call.notified_on is not None else FIRST_NOTICE)
    if chosen not in KINDS:
        raise ValueError(
            pick(
                f"Type d'avis inconnu : {chosen!r}. Attendu : {', '.join(KINDS)}.",
                f"Unknown notice kind: {chosen!r}. Expected: {', '.join(KINDS)}.",
            )
        )
    if chosen == REMINDER and call.notified_on is None:
        raise ValueError(
            pick(
                f"L'appel {call.reference} n'a jamais été notifié : c'est le premier avis "
                f"qui manque, pas une relance.",
                f"Call {call.reference} has never been notified: what is missing is the "
                f"first notice, not a reminder.",
            )
        )

    language = await language_of(db, investor)
    # 🔴 THE ONE LINE THIS WHOLE MODULE EXISTS FOR. Everything built inside this block reads
    # the investor's language, whatever language the manager who clicked is using.
    with i18n.use_lang(language):
        letter = (
            notices.first_notice(facts)
            if chosen == FIRST_NOTICE
            else notices.reminder(facts)
        )

    return PreparedNotice(
        kind=chosen,
        language=language,
        to=investor.email,
        notice=letter,
        sending_is_configured=mailer.is_configured(),
    )


async def send(
    db: AsyncSession, *, call: CapitalCall, as_of: date, kind: str | None = None
) -> PreparedNotice:
    """Send the letter, then record that it went out. Never the other way round.

    🔴 A REMINDER STILL OBEYS THE FLOOR BETWEEN TWO. `call_chasing_service.due_for_reminder`
    holds the rule; bypassing it here would let a nightly job write to the same investor
    every morning until they pay, which is how a fund teaches its investors to filter its
    e-mails.

    🔴 AND `mailer.send` RAISES RATHER THAN RETURNING FALSE, so a relay that refused the
    message leaves `notified_on` untouched. The chasing list keeps showing the call as never
    notified, which is the truth.
    """
    prepared = await prepare(db, call=call, as_of=as_of, kind=kind)

    if prepared.kind == REMINDER:
        late = await _late_call_for(db, call, as_of=as_of)
        allowed, why = call_chasing_service.due_for_reminder(late, as_of=as_of)
        if not allowed:
            raise ValueError(why)

    await mailer.send(
        to=prepared.to or "",
        subject=prepared.notice.subject,
        body=prepared.notice.body,
    )

    if prepared.kind == FIRST_NOTICE:
        call.notified_on = as_of
    call.last_reminded_on = as_of
    await db.flush()
    return prepared


async def _late_call_for(
    db: AsyncSession, call: CapitalCall, *, as_of: date
) -> call_chasing_service.LateCall:
    """The chasing view of one call, so the reminder floor is read from ONE rule.

    ⚠️ REBUILDING THE FLOOR HERE WOULD BE A SECOND COPY OF IT, and the two would disagree the
    first time either changed. It is cheap: this runs once, on a click.
    """
    found = [
        late
        for late in await call_chasing_service.late_calls(db, as_of=as_of)
        if late.call_id == call.id
    ]
    if found:
        return found[0]
    # Not on the late list, and the two ways that happens deserve different sentences: a
    # manager told « not late » about a call they can see is overdue would go looking for a
    # bug, when the answer is that the investor paid.
    facts, _ = await _facts(db, call, as_of=as_of)
    when = as_of.isoformat()
    if facts.outstanding <= 0:
        raise ValueError(
            pick(
                f"L'appel {call.reference} est soldé : une relance dirait à cet "
                f"investisseur que son règlement n'a pas été vu.",
                f"Call {call.reference} is settled: a reminder would tell this investor "
                f"their payment was not seen.",
            )
        )
    raise ValueError(
        pick(
            f"L'appel {call.reference} n'est pas échu au {when} : il n'y a rien à relancer.",
            f"Call {call.reference} is not due on {when}: there is nothing to chase.",
        )
    )


__all__ = [
    "FIRST_NOTICE",
    "KINDS",
    "REMINDER",
    "PreparedNotice",
    "language_of",
    "prepare",
    "send",
]
