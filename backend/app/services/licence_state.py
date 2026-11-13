"""What the firm's Alice licence says about ACCESS and about BILLING, read in one place.

Decisions of the owner, 8 Nov 2026 (the same as Le Comptoir Immo's):

- a licence blocked for an unpaid invoice (or blocked by hand) SUSPENDS the firm: its team
  (the colleagues attached to it) loses access, the subscriber keeps « Mon abonnement »
  alone, to settle; the investors keep their space;
- a licence whose termination has run out CLOSES it: the team is refused, and the
  subscriber keeps « Mon abonnement » alone, exactly as in a suspension (the owner, 9 Nov
  2026, « oui fais le »): his invoices and credit notes, what is still due, and subscribing
  again;
- nothing is written into `users.is_active`: the licence is read on every request.

The contract Alice serves on `/internal/license/{id}` (her side, 8 Nov 2026), every key read
as OPTIONAL: an absent key means « nothing to say », never « false ».

    billing_starts_on    ISO date or null
    has_payment_method   bool
    payment_failed_on    ISO date or null
    suspension_on        ISO date or null

🔴 TERMINATED IS READ OFF `access_until`. Alice writes it in one place only, a termination,
and derives `is_blocked` from it once passed. A licence blocked with no `access_until`, or
one still ahead, is a SUSPENSION.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status

from app.core.firm_scope import firm_of
from app.core.i18n import pick
from app.models.user import MANAGER, User
from app.services import alice_client

#: The response header carrying a refusal's machine code, read by the screen to tell a
#: closed firm from an expired session. The same header and codes as Le Comptoir Immo.
ERROR_CODE_HEADER = "X-Error-Code"

#: A colleague of a firm suspended for an unpaid invoice: refused, with the reason.
AGENCY_SUSPENDED = "agency_suspended"
#: The firm's licence once its termination has run out: the team refused (401), the
#: subscriber held to « Mon abonnement » (403 anywhere else).
LICENCE_ENDED = "licence_ended"
#: The subscriber of a suspended firm, on any route but « Mon abonnement »: 403.
SUBSCRIPTION_SUSPENDED = "subscription_suspended"
#: The subscriber of an ended licence WRITING during the thirty days to export (the owner,
#: 13 Nov 2026): 403 with this word, and the screen says it where the form is, keeping what
#: was typed, instead of sending them to « Mon abonnement ».
SUBSCRIPTION_READ_ONLY = "subscription_read_only"

#: 🔴 THE DAYS THE SUBSCRIBER KEEPS TO EXPORT THEIR DATA ONCE THE SUBSCRIPTION HAS ENDED
#: (terms of sale, article 7.4: « trente (30) jours pour exporter ses données » from the
#: end of the subscription; the owner, 12 Nov 2026). Until then the subscriber of an ended
#: licence was held to « Mon abonnement » the very day it took effect: now every READ stays
#: open for thirty days after `access_until` (the register, the exports, the documents),
#: writes closed, then « Mon abonnement » alone as before.
EXPORT_DAYS = 30

#: Alice's `erasure_status` under which a space has an erasure day (13 Nov 2026).
ERASURE_DUE = frozenset({"scheduled", "postponed"})

#: What the subscriber HELD to « Mon abonnement » may still reach, whether the firm is
#: suspended or its licence has ended (ONE rule, the owner, 9 Nov 2026): their subscription
#: (read it, pay, declare a transfer, download invoices and credit notes, subscribe again),
#: their own session (who am I, sign out, the second factor) and the terms the sign-in asks
#: for. Everything else answers 403 with the reason's code, held HERE and not only by a
#: screen.
HELD_SUBSCRIBER_PREFIXES: tuple[str, ...] = (
    "/api/v1/billing",
    "/api/v1/auth/",
    "/api/v1/terms",
)


def held_subscriber_may_reach(path: str) -> bool:
    return any(
        path == prefix.rstrip("/") or path.startswith(prefix)
        for prefix in HELD_SUBSCRIBER_PREFIXES
    )


def _first_erasure_instant() -> datetime:
    """The last second, platform time, of the eve of the first day any space may be erased:
    the same shape as an end written by Alice (the last second of a day)."""
    from app.core import self_delete
    from app.core.fund_time import PLATFORM_ZONE

    day = self_delete.FIRST_ERASURE_DAY
    start = datetime(day.year, day.month, day.day, tzinfo=PLATFORM_ZONE)
    return (start - timedelta(seconds=1)).astimezone(UTC)


def platform_day(instant: datetime) -> date:
    """The platform's day of an instant (Paris): the day a banner or a refusal names."""
    from app.core.fund_time import PLATFORM_ZONE

    return instant.astimezone(PLATFORM_ZONE).date()


def _day(value: Any) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _instant(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # Alice writes naive UTC.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _invoice_due(value: Any) -> dict | None:
    """The invoice still to pay, as Alice names it (`invoice_due`), or None.

    The oldest invoice still owed (billed period, credit notes deducted), with no transfer
    declared and no Stripe debit on its way (the owner, 9 Nov 2026: after the billing start,
    a subscriber paying by transfer, or with no means of payment, had nothing on screen
    between the invoice e-mail and the suspension). Relayed as she sends it; a malformed
    answer is none, so the banner never draws half a sentence.
    """
    if not isinstance(value, dict):
        return None
    number, year, month = (
        value.get("number"),
        value.get("period_year"),
        value.get("period_month"),
    )
    left, currency, overdue = (
        value.get("left_ttc"),
        value.get("currency"),
        value.get("overdue"),
    )
    due_on = _day(value.get("due_on"))
    if not (
        isinstance(number, str) and number and isinstance(currency, str) and currency
    ):
        return None
    if isinstance(year, bool) or isinstance(month, bool):
        return None
    if not (isinstance(year, int) and isinstance(month, int) and 1 <= month <= 12):
        return None
    if isinstance(left, bool) or not isinstance(left, int | float) or due_on is None:
        return None
    if not isinstance(overdue, bool):
        return None
    return {
        "number": number,
        "period_year": year,
        "period_month": month,
        "left_ttc": float(left),
        "currency": currency.upper(),
        "due_on": due_on.isoformat(),
        "overdue": overdue,
    }


@dataclass(frozen=True)
class LicenceState:
    is_blocked: bool
    #: Blocked because a termination ran out: the firm left.
    terminated: bool
    billing_starts_on: date | None
    #: None when Alice did not say.
    has_payment_method: bool | None
    payment_failed_on: date | None
    suspension_on: date | None
    #: The invoice the holder's banner asks to pay (`_invoice_due`), or None.
    invoice_due: dict | None = None
    #: When the paid access ended or ends (`access_until`), as an aware instant.
    ends_at: datetime | None = None
    #: Alice's erasure of the space once the export days have run out (the owner, 13 Nov
    #: 2026): where the licence stands (`erasure_status`), and the day, only when she
    #: schedules one. This product erases on the later of her day and `own_erase_on`.
    erasure_status: str | None = None
    alice_erase_on: date | None = None
    #: Alice's word on a demonstration licence; None when she did not say.
    is_demo: bool | None = None

    @property
    def suspended(self) -> bool:
        """Blocked, and not by a termination: the subscriber may still come in to settle."""
        return self.is_blocked and not self.terminated

    @property
    def export_until(self) -> datetime | None:
        """The end of the thirty days to export, once a termination has run out.

        When Alice schedules the erasure, never before the start of the first day any space
        may be erased (`self_delete.FIRST_ERASURE_DAY`): a subscriber whose thirty days had
        run out when the erasure went into production gets its notice, with the export, and
        reads until then. A postponement by the console opens nothing more."""
        if not self.terminated or self.ends_at is None:
            return None
        until = self.ends_at + timedelta(days=EXPORT_DAYS)
        if self.erasure_status in ERASURE_DUE:
            return max(until, _first_erasure_instant())
        return until

    @property
    def own_erase_on(self) -> date | None:
        """The day this product reads for the erasure, from `access_until` alone: the day
        after the last platform day of the thirty days (`self_delete.ended_erase_on`)."""
        if not self.terminated or self.ends_at is None:
            return None
        from app.core import self_delete

        return self_delete.ended_erase_on(
            platform_day(self.ends_at + timedelta(days=EXPORT_DAYS))
        )

    @property
    def erase_on(self) -> date | None:
        """The day the space is erased: Alice's day and this product's own reading agree on
        the end, and the later of the two days is kept. None when either is missing."""
        if self.erasure_status not in ERASURE_DUE or self.alice_erase_on is None:
            return None
        own = self.own_erase_on
        return None if own is None else max(own, self.alice_erase_on)

    def exports_open(self, now: datetime | None = None) -> bool:
        """Does the subscriber of an ENDED licence still read and export their data?"""
        until = self.export_until
        return until is not None and (now or datetime.now(UTC)) < until


def read(lic: dict | None, *, now: datetime | None = None) -> LicenceState | None:
    """The licence Alice answered, as a state; None when there is none (404, outage)."""
    if not isinstance(lic, dict):
        return None
    now = now or datetime.now(UTC)
    ends = _instant(lic.get("access_until"))
    is_blocked = bool(lic.get("is_blocked"))
    method = lic.get("has_payment_method")
    return LicenceState(
        is_blocked=is_blocked,
        terminated=is_blocked and ends is not None and ends <= now,
        billing_starts_on=_day(lic.get("billing_starts_on")),
        has_payment_method=method if isinstance(method, bool) else None,
        payment_failed_on=_day(lic.get("payment_failed_on")),
        suspension_on=_day(lic.get("suspension_on")),
        invoice_due=_invoice_due(lic.get("invoice_due")),
        ends_at=ends,
        erasure_status=status
        if isinstance(status := lic.get("erasure_status"), str)
        else None,
        alice_erase_on=_day(lic.get("erase_on")),
        is_demo=demo if isinstance(demo := lic.get("is_demo"), bool) else None,
    )


def _refused(sentence: str, code: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, sentence, headers={ERROR_CODE_HEADER: code}
    )


def held_subscriber_refusal(
    reason: str, export_until: datetime | None = None
) -> HTTPException:
    """403 for the held subscriber anywhere but « Mon abonnement », with the reason's code
    (`subscription_suspended` or `licence_ended`): the screen sends him back there and says
    why.

    🔴 A WRITE DURING THE THIRTY DAYS TO EXPORT IS SAID WHERE IT WAS TRIED (the owner, 13
    Nov 2026): `subscription_read_only`, the last day in the reader's language, JJ/MM/AAAA;
    the screen keeps the form open with what was typed and links to « Mon abonnement »,
    never a redirect. After the thirty days, the confinement is unchanged."""
    if reason == SUBSCRIPTION_READ_ONLY and export_until is not None:
        last_day = platform_day(export_until).strftime("%d/%m/%Y")
        return HTTPException(
            status.HTTP_403_FORBIDDEN,
            pick(
                f"Abonnement terminé : lecture et export seulement jusqu'au {last_day}.",
                f"Subscription ended: reading and export only until {last_day}.",
            ),
            headers={ERROR_CODE_HEADER: SUBSCRIPTION_READ_ONLY},
        )
    sentence = (
        pick(
            "Votre abonnement a pris fin : réabonnez-vous depuis « Mon abonnement » pour "
            "retrouver l'accès.",
            "Your subscription has ended: subscribe again from « My subscription » to get "
            "access back.",
        )
        if reason == LICENCE_ENDED
        else pick(
            "Votre compte est suspendu pour impayé : réglez votre abonnement pour "
            "retrouver l'accès.",
            "Your account is suspended for an unpaid invoice: pay your subscription to "
            "get access back.",
        )
    )
    return HTTPException(
        status.HTTP_403_FORBIDDEN, sentence, headers={ERROR_CODE_HEADER: reason}
    )


async def gate(user: User, *, reading: bool = False) -> str | None:
    """Admit or refuse an account under its firm's licence.

    Answers the reason the account is HELD to « Mon abonnement » (`SUBSCRIPTION_SUSPENDED`
    or `LICENCE_ENDED`) for the subscriber of a blocked firm, None for an account let in
    freely; raises 401 for the team of a blocked firm.

    🔴 THE TEAM IS EVERY MANAGER ACCOUNT, the subscriber and the colleagues attached to it
    (`firm_id`), all read on the firm's ONE licence (`firm_of`). Before 8 Nov 2026 nothing
    read it: a blocked firm went on working through its colleagues. The platform's admin
    and the investors are outside the team and keep their access.

    🔴 THIRTY DAYS TO READ AND EXPORT ONCE IT ENDED (terms of sale, 7.4; the owner, 12 Nov
    2026): `reading` (a GET or a HEAD) of the subscriber is let in freely for `EXPORT_DAYS`
    after `access_until`, writes stay held (`SUBSCRIPTION_READ_ONLY`, said where they were
    tried, 13 Nov 2026), then « Mon abonnement » alone.

    ⚠️ FAILS OPEN: no console configured, no licence filed (404) or an Alice that does not
    answer lets the account in, as before. A blocked firm is let in during an outage of
    Alice; a fund that cannot work because its billing service is down is the worse error.
    """
    if user.role != MANAGER:
        return None
    try:
        state = read(await alice_client.get_license(firm_of(user)))
    except Exception:  # noqa: BLE001 - see the docstring: the gate fails open
        return None
    if state is None or not state.is_blocked:
        return None
    if user.holds_the_licence:
        # 🔴 THE SUBSCRIBER COMES IN, SUSPENDED OR ENDED (the owner, 9 Nov 2026): before,
        # an ended licence refused him at every door, « Mon abonnement » included, and left
        # him no way to read his invoices, settle what was due or subscribe again.
        if state.exports_open():
            if reading:
                return None
            # A write during the thirty days: refused where it was tried, with the last
            # day (`held_subscriber_refusal`), « Mon abonnement » still open to it.
            user.licence_export_until = state.export_until
            return SUBSCRIPTION_READ_ONLY
        return LICENCE_ENDED if state.terminated else SUBSCRIPTION_SUSPENDED
    if state.terminated:
        raise _refused(
            pick(
                "L'abonnement de votre société a pris fin : l'accès est fermé.",
                "Your firm's subscription has ended: access is closed.",
            ),
            LICENCE_ENDED,
        )
    raise _refused(
        pick(
            "L'accès de votre société est suspendu pour impayé. Le titulaire de "
            "l'abonnement peut le rétablir en réglant depuis « Mon abonnement ».",
            "Your firm's access is suspended for an unpaid invoice. The subscription "
            "holder can restore it by paying from « My subscription ».",
        ),
        AGENCY_SUSPENDED,
    )
