"""What the firm's Alice licence says about ACCESS and about BILLING, read in one place.

Decisions of the owner, 8 Nov 2026 (the same as Le Comptoir Immo's):

- a licence blocked for an unpaid invoice (or blocked by hand) SUSPENDS the firm: its team
  (the colleagues attached to it) loses access, the subscriber keeps « Mon abonnement »
  alone, to settle; the investors keep their space;
- a licence whose termination has run out CLOSES it: the subscriber is refused as well;
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
from datetime import UTC, date, datetime
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
#: Anyone of the firm's team once its termination has run out: refused.
LICENCE_ENDED = "licence_ended"
#: The subscriber of a suspended firm, on any route but « Mon abonnement »: 403.
SUBSCRIPTION_SUSPENDED = "subscription_suspended"

#: What the subscriber of a SUSPENDED firm may still reach: their subscription (read it,
#: pay, declare a transfer, download invoices and credit notes), their own session (who am
#: I, sign out, the second factor) and the terms the sign-in asks for. Everything else
#: answers 403 `subscription_suspended`, held HERE and not only by a screen.
SUSPENDED_SUBSCRIBER_PREFIXES: tuple[str, ...] = (
    "/api/v1/billing",
    "/api/v1/auth/",
    "/api/v1/terms",
)


def suspended_subscriber_may_reach(path: str) -> bool:
    return any(
        path == prefix.rstrip("/") or path.startswith(prefix)
        for prefix in SUSPENDED_SUBSCRIBER_PREFIXES
    )


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

    @property
    def suspended(self) -> bool:
        """Blocked, and not by a termination: the subscriber may still come in to settle."""
        return self.is_blocked and not self.terminated


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
    )


def _refused(sentence: str, code: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, sentence, headers={ERROR_CODE_HEADER: code}
    )


def subscriber_suspended_refusal() -> HTTPException:
    return HTTPException(
        status.HTTP_403_FORBIDDEN,
        pick(
            "Votre compte est suspendu pour impayé : réglez votre abonnement pour "
            "retrouver l'accès.",
            "Your account is suspended for an unpaid invoice: pay your subscription to "
            "get access back.",
        ),
        headers={ERROR_CODE_HEADER: SUBSCRIPTION_SUSPENDED},
    )


async def gate(user: User) -> bool:
    """Admit or refuse an account under its firm's licence; True for a SUSPENDED subscriber.

    🔴 THE TEAM IS EVERY MANAGER ACCOUNT, the subscriber and the colleagues attached to it
    (`firm_id`), all read on the firm's ONE licence (`firm_of`). Before 8 Nov 2026 nothing
    read it: a blocked firm went on working through its colleagues. The platform's admin
    and the investors are outside the team and keep their access.

    ⚠️ FAILS OPEN: no console configured, no licence filed (404) or an Alice that does not
    answer lets the account in, as before. A blocked firm is let in during an outage of
    Alice; a fund that cannot work because its billing service is down is the worse error.
    """
    if user.role != MANAGER:
        return False
    try:
        state = read(await alice_client.get_license(firm_of(user)))
    except Exception:  # noqa: BLE001 - see the docstring: the gate fails open
        return False
    if state is None or not state.is_blocked:
        return False
    if state.terminated:
        raise _refused(
            pick(
                "L'abonnement de votre société a pris fin : l'accès est fermé.",
                "Your firm's subscription has ended: access is closed.",
            ),
            LICENCE_ENDED,
        )
    if user.holds_the_licence:
        return True
    raise _refused(
        pick(
            "L'accès de votre société est suspendu pour impayé. Le titulaire de "
            "l'abonnement peut le rétablir en réglant depuis « Mon abonnement ».",
            "Your firm's access is suspended for an unpaid invoice. The subscription "
            "holder can restore it by paying from « My subscription ».",
        ),
        AGENCY_SUSPENDED,
    )
