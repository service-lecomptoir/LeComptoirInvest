"""Who the fund may do business with, and what that verdict actually stops.

« UNE BASE KYC POUR SAVOIR AVEC QUI FAIRE AFFAIRE » — the user's words, and they set the
shape. This is not a filing cabinet for identity documents. It is a DECISION, taken by a
named person on a date, that either lets money in or does not.

🔴 A VERDICT THAT BLOCKS NOTHING IS THEATRE, and it is the commonest way this goes wrong: a
tidy screen full of green ticks beside a fund that has already banked the money. The whole
point of `blocks_money` below is that the check is not advisory. If it can be bypassed by
recording the contribution first and reviewing later, it does not exist.

⚠️ ACCEPTANCE EXPIRES. An investor cleared three years ago on a passport that lapsed last
spring is not cleared; they are unreviewed, which is a different state from refused and
must not be silently treated as accepted. That is why `REVIEW` exists beside `PENDING`: one
has never been looked at, the other was and has gone stale. Collapsing them loses the fact
that somebody once said yes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

#: Never reviewed. The state every investor starts in.
PENDING = "a_verifier"
#: Reviewed and accepted. The only state that lets money in.
ACCEPTED = "accepte"
#: Reviewed and refused. Money stays out, and the reason is recorded.
REFUSED = "refuse"
#: Was accepted, and is no longer current — an expired document, a stale periodic review.
#: NOT the same as `PENDING`: somebody did say yes once, and that is worth knowing.
REVIEW = "a_revoir"

STATUSES: tuple[str, ...] = (PENDING, ACCEPTED, REFUSED, REVIEW)

#: Ordinary diligence.
RISK_STANDARD = "standard"
#: Enhanced diligence: politically exposed person, high-risk jurisdiction, opaque structure,
#: unexplained source of funds. Not a refusal — a heavier file and a shorter review cycle.
RISK_HIGH = "eleve"

RISK_LEVELS: tuple[str, ...] = (RISK_STANDARD, RISK_HIGH)

#: How long an acceptance stays current, by risk level. Beyond it the investor moves to
#: `REVIEW` on its own — an acceptance nobody revisits is an acceptance that ages into a
#: guess.
REVIEW_MONTHS: dict[str, int] = {RISK_STANDARD: 36, RISK_HIGH: 12}


def blocks_money(status: str | None) -> bool:
    """Must money from this investor be refused?

    THE ONE RULE, AND IT IS WRITTEN ONCE. Every place that records a contribution asks this
    function; none of them decides for itself. A second spelling of « is this investor
    cleared » is how one screen comes to accept what another refuses, and the screen that
    accepts is always the one with the money.

    ⚠️ AN UNKNOWN OR MISSING STATUS BLOCKS. Not because it is likely to be a problem, but
    because « nobody has looked » must never read as « nothing was found ». Defaulting the
    other way turns an investor nobody reviewed into an investor everybody assumed fine.
    """
    return status != ACCEPTED


def accepts_money(status: str | None) -> bool:
    """The affirmative form, for a screen that shows what CAN be done. One truth, two
    readings, and never two rules."""
    return not blocks_money(status)


def review_due_on(accepted_on: date | None, risk_level: str | None) -> date | None:
    """When this acceptance stops being current. None when nothing has been accepted.

    Derived rather than stored, deliberately: a stored due date drifts the day the review
    cycle changes, and every investor accepted before that day keeps the old one for ever.
    """
    if accepted_on is None:
        return None
    months = REVIEW_MONTHS.get(risk_level or RISK_STANDARD, REVIEW_MONTHS[RISK_STANDARD])
    year = accepted_on.year + (accepted_on.month - 1 + months) // 12
    month = (accepted_on.month - 1 + months) % 12 + 1
    # The 29th of February exists one year in four; clamp rather than raise.
    day = min(accepted_on.day, [31, 29 if year % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def is_stale(status: str | None, accepted_on: date | None, risk_level: str | None, today: date) -> bool:
    """True when an acceptance has aged past its review date.

    The caller moves the investor to `REVIEW`; this function does not mutate anything. A
    rule that changes state while answering a question is a rule nobody can ask twice.
    """
    if status != ACCEPTED:
        return False
    due = review_due_on(accepted_on, risk_level)
    return due is not None and today > due


@dataclass(frozen=True)
class Verdict:
    """A decision, with who took it and when. All three or none.

    An acceptance with no author and no date is not a decision, it is a value in a column —
    and the first question an auditor asks is who decided, not what was decided.
    """

    status: str
    decided_by: str
    decided_on: date
    #: Required for a refusal, and for a downgrade to `REVIEW`. « Refused » with no reason
    #: cannot be reconsidered, and the investor cannot be told anything useful either.
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"Unknown KYC status {self.status!r}.")
        if self.status in (REFUSED, REVIEW) and not (self.reason or "").strip():
            raise ValueError(
                f"A {self.status!r} verdict needs a reason: without one it can neither be "
                f"reconsidered nor explained to the investor."
            )
