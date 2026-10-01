"""What enters the audit journal, and what must NEVER be written into it.

🔴 THE JOURNAL IS A PROMISE, NOT A CONVENIENCE. It answers « who approved this investor »,
« who changed that call », « who attributed this payment ». A table missing from the list
below does not appear in it -- no error, no trace -- and nobody finds out before the day
that very answer is needed. The guard `test_every_table_has_said_whether_it_is_audited`
makes a new table choose.

⚠️ SECRETS ARE MASKED BY THEIR NAME, not by a list of columns. A `stripe_secret_key` added
tomorrow is masked with nobody thinking about it; a list of exact names would have let
the next one through. The price is a `token_count` masked for nothing, which costs
nothing, against a key copied in clear into a journal the supervision reads.

⚠️ STANDARD LIBRARY ONLY: the rules are read by the listeners, by the route and by the
tests, and must import none of them.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

CREATE = "db.create"
UPDATE = "db.update"
DELETE = "db.delete"
ACTIONS = (CREATE, UPDATE, DELETE)

#: What a person does, and is answerable for. In a product that holds other people's money
#: that is nearly everything.
AUDITED = (
    "revoked_sessions",
    "users",
    "funds",
    "investors",
    "investor_documents",
    "projects",
    "project_valuations",
    "deployments",
    "project_returns",
    "subscription_requests",
    "subscriptions",
    "subscription_conversions",
    "capital_calls",
    "contributions",
    "distributions",
    "bank_movements",
)

#: 🔴 A BANK LINE ARRIVES BY IMPORT, AND IS THEN HANDLED BY SOMEBODY. A statement brings
#: hundreds of movements at once: their creation is the bank's act, already dated and
#: referenced by the bank, and journalling it would bury everything else. What a person
#: does NEXT -- attributing a movement to an investor, changing its category, deleting it
#: -- is exactly what this journal is for. So: changes and deletions, never creations.
IMPORTED = ("bank_movements",)

#: The journal does not audit itself.
NEVER_AUDITED = ("audit_logs",)

SENSITIVE = (
    "password",
    "hash",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "webhook",
    # 🔴 THE NUMBERS THAT MOVE MONEY OR NAME A PERSON. `iban` catches the investor's
    # encrypted account AND its fingerprint, the fund's own account and a counterparty's;
    # a journal is not where an account number is copied in clear, and the supervision
    # that reads it needs none of them to answer « who changed this ».
    "iban",
    "bic",
    "document_number",
    "national_id",
)
MASK = "***"

#: 🔴 WHAT A FILE SAYS ABOUT A PERSON IS NOT COPIED INTO A JOURNAL. The reason behind a KYC
#: decision, where somebody's money comes from, why a third party paid for them: written
#: by a compliance officer, for the file. The supervision learns THAT the text changed, by
#: whom and when, and never what it says.
PRIVATE = ("kyc_reason", "source_of_funds", "third_party_reason")
WITHHELD = "<private>"

#: Columns that move on their own. A change made of these alone is not an event: a stamp
#: rewritten by every save would fill the journal with lines saying nothing.
NOISE = ("updated_at", "last_used_at")

#: A long text is cut: the journal says THAT it changed and shows where it starts.
MAX_TEXT = 300


def is_audited(table: str) -> bool:
    return table in AUDITED


def has_chosen(table: str) -> bool:
    """Has this table been filed on one side or the other?"""
    return table in AUDITED or table in NEVER_AUDITED


def is_sensitive(column: str) -> bool:
    lowered = (column or "").lower()
    return any(fragment in lowered for fragment in SENSITIVE)


def jsonable(value):
    """A value as a JSON column can carry it."""
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes | bytearray | memoryview):
        return f"<{len(value)} bytes>"
    if isinstance(value, str):
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + "…"
    if isinstance(value, dict):
        return {"<keys>": sorted(str(k) for k in value)[:40]}
    if isinstance(value, list | tuple | set):
        return f"<{len(value)} items>"
    return str(value)[:MAX_TEXT]


def masked(column: str, value):
    if value is None:
        return None
    if is_sensitive(column):
        return MASK
    if column in PRIVATE:
        return WITHHELD if value != "" else ""
    return jsonable(value)
