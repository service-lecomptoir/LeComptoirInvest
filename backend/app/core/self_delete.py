"""Deleting one's own account: the rules every product of Le Comptoir shares.

🔴 ONE PATTERN, WRITTEN ONCE (the owner, 12 Nov 2026: « un vrai bouton Supprimer mon compte
dans chaque application »). This file is meant to be the same, byte for byte, in every
product that has accounts, like `two_factor.py`. It holds the rules and the arithmetic only:
no model, no route, no role, no letter. Each product writes its own glue around it (which
roles are the subscriber, whom to tell, what its cascade deletes), and a test of each product
checks the fingerprint of this file, so that a copy changed in one product fails until all
are changed.

What the terms of use promise (CGU of Alice, article 9.3), and what this file fixes:

- a person invited by a client (tenant, landlord, team member...) deletes their account
  AT ONCE: sessions cut on every device, login, password, second factor and backup codes,
  preferences erased. The data the client holds on them stays with the client, who is told
  and answers within ONE MONTH (GDPR art. 12.3 and 17): `answer_by`;
- the subscriber who deletes their own account ends their subscription, and the deletion
  takes effect after a grace period of THIRTY DAYS (`erase_on`), during which they may
  cancel it and export their data; a reminder leaves SEVEN days before (`reminder_due`);
- the account row itself may have to stay, for the history that names it (who wrote a
  message, who entered a payment): it is then a TOMBSTONE carrying no personal data
  (`erased_values`, `tombstone_email`, `unusable_password`);
- the same erasure runs once a subscription has ENDED and its thirty days to export have
  run out (terms of sale 7.4): `ended_erase_on`, never before `FIRST_ERASURE_DAY`.
"""

from __future__ import annotations

import hmac
import secrets
import unicodedata
from calendar import monthrange
from collections.abc import Iterable
from datetime import date, timedelta

#: The subscriber's grace period, in days (CGU 9.3, 3).
GRACE_DAYS = 30
#: The reminder leaves this many days before the erasure.
REMINDER_DAYS_BEFORE = 7
#: The client answers the request for erasure within this many months (GDPR art. 12.3).
ANSWER_MONTHS = 1
#: A tombstone's address: a reserved domain (RFC 2606), where no mail is ever delivered.
TOMBSTONE_DOMAIN = "account.invalid"

#: The columns a tombstone keeps whatever the product: its identity as a row and its dates.
ALWAYS_KEPT = frozenset({"id", "created_at", "updated_at"})

# ── The same erasure, once a subscription has ended (the owner, 13 Nov 2026) ───────────
# Terms of sale 7.4 and data processing agreement 11: thirty days to export once the
# subscription has ended, then the data are erased. The purge is the subscriber's purge
# above; only the trigger differs. Alice computes the day and serves it; a product erases
# only on the later of Alice's day and `ended_erase_on`, its own reading of the same end.

#: 🔴 THE DAY THIS ERASURE WENT INTO PRODUCTION, written in the code: no space is erased
#: less than `LAUNCH_NOTICE_DAYS` after it, and a space whose thirty days had already run
#: out is erased on `FIRST_ERASURE_DAY`, after the notice. Alice holds the same day
#: (`license_erasure.ERASURE_LAUNCH_DAY`).
ERASURE_LAUNCH_DAY = date(2026, 11, 20)
LAUNCH_NOTICE_DAYS = 30
FIRST_ERASURE_DAY = ERASURE_LAUNCH_DAY + timedelta(days=LAUNCH_NOTICE_DAYS)


# ── The calendar of a deletion ──────────────────────────────────────────────────────────


def erase_on(requested_day: date) -> date:
    """The day the subscriber's space is erased: the day asked plus the grace period."""
    return requested_day + timedelta(days=GRACE_DAYS)


def reminder_day(erase_day: date) -> date:
    """The day the reminder leaves."""
    return erase_day - timedelta(days=REMINDER_DAYS_BEFORE)


def is_due(today: date, erase_day: date) -> bool:
    """Whether the erasure must run now. A day missed is caught up: `>=`, never `==`."""
    return today >= erase_day


def reminder_due(today: date, erase_day: date, *, already_reminded: bool) -> bool:
    """Whether the reminder must leave now: once, from its day until the erasure."""
    return not already_reminded and reminder_day(erase_day) <= today < erase_day


def ended_erase_on(last_export_day: date) -> date:
    """The day an ended subscription's space is erased: the day after the last day of its
    thirty days to export (the platform's day), never before `FIRST_ERASURE_DAY`."""
    return max(last_export_day + timedelta(days=1), FIRST_ERASURE_DAY)


def days_left(today: date, erase_day: date) -> int:
    """Days until the erasure, never below zero."""
    return max((erase_day - today).days, 0)


def answer_by(received_on: date) -> date:
    """The day the client must have answered a request for erasure received on
    `received_on`: the same day `ANSWER_MONTHS` later, the month's last day when it is
    shorter (received on 31 January, answered by 28 or 29 February)."""
    month_index = received_on.month - 1 + ANSWER_MONTHS
    year = received_on.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(received_on.day, monthrange(year, month)[1]))


# ── The confirmation ────────────────────────────────────────────────────────────────────


def _normalized_address(address: str | None) -> str:
    return unicodedata.normalize("NFKC", (address or "").strip()).casefold()


def same_address(typed: str | None, actual: str | None) -> bool:
    """Whether the address typed in the confirmation is the account's: spaces and case
    aside, compared in constant time. An empty one never matches."""
    left, right = _normalized_address(typed), _normalized_address(actual)
    if not left or not right:
        return False
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


# ── The tombstone ───────────────────────────────────────────────────────────────────────


def tombstone_email(account_id: object) -> str:
    """The address a tombstone carries: unique (the account's id), never deliverable."""
    return f"deleted-{account_id}@{TOMBSTONE_DOMAIN}"


def unusable_password() -> str:
    """A secret nobody knows, to hash in place of the password: the row keeps a valid hash
    (the column is required) that no one can ever type."""
    return secrets.token_urlsafe(48)


def erased_values(columns: Iterable[tuple[str, bool]], kept: Iterable[str] = ()) -> dict:
    """The values that empty an account row: None for every NULLABLE column outside `kept`
    and `ALWAYS_KEPT`. `columns` are (attribute, nullable) pairs read from the product's
    model, so a column added later is erased by default, never forgotten. The required
    columns (address, password, name, active flag) are the product's to set."""
    keep = ALWAYS_KEPT | frozenset(kept)
    return {name: None for name, nullable in columns if nullable and name not in keep}
