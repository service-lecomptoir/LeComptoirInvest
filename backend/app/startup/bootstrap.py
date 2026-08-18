"""The very first account, and nothing after it.

🔴 A SEED BOOTSTRAPS, IT DOES NOT MAINTAIN. This repository paid for that sentence three
times in one week: an account deleted in Alice reappeared at every deployment, because the
seed asked « does this e-mail exist? » and answered « no » — the row had been deleted — so
it created it again. And it rewrote the password on every boot, quietly undoing whatever
the holder had chosen.

The condition here is the only one that is true: **CAN ANYBODY ADMINISTER THIS FUND?** If
somebody can, this module does nothing at all, whatever their e-mail is. A deleted account
stays deleted; a renamed one stays renamed; a password chosen by its holder is never
touched.

⚠️ WHY IT EXISTS AT ALL, given that `models/user.py` says a manager comes from Alice and is
never minted here. Alice does not drive this product yet: it has no `/internal` contract,
so there is no other way for the first person to sign in. This is the escape hatch, it is
named as one, and it disappears the day Alice provisions the fund's managers — at which
point the guard below already makes it inert, because somebody will be able to administer.

⚠️ AND IT REFUSES TO INVENT A PASSWORD. A generated one has to be printed in a log to be
usable, and a credential in a log is a credential everybody with log access holds. No
`BOOTSTRAP_MANAGER_PASSWORD`, no bootstrap, and the reason is said out loud at startup.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import FUND_WIDE_ROLES, MANAGER, User

logger = logging.getLogger(__name__)


def bootstrap_is_needed(*, somebody_can_administer: bool) -> bool:
    """The whole rule, as a pure function so a test can hold it still.

    Not « does this e-mail exist » — that question makes a deleted account come back — but
    « is there anybody at all who can run this fund ». One is a fact about a row, the other
    is a fact about the system, and only the second is what a bootstrap is for.
    """
    return not somebody_can_administer


async def ensure_first_manager(db: AsyncSession, *, email: str, password: str) -> bool:
    """Create the first fund-wide account if there is none. Returns True if it created one.

    ⚠️ NEVER TOUCHES AN EXISTING ROW. Not the password, not the role, not the name. The
    only write this function is allowed to make is an INSERT, and only into an empty field.
    """
    somebody = (
        await db.execute(select(User.id).where(User.role.in_(FUND_WIDE_ROLES)).limit(1))
    ).scalar_one_or_none()

    if not bootstrap_is_needed(somebody_can_administer=somebody is not None):
        return False

    db.add(
        User(
            email=email.strip().lower(),
            hashed_password=hash_password(password),
            account_name="Gestion du fonds",
            role=MANAGER,
            # The credential was handed over by whoever set the variable, so it is not the
            # holder's yet. They replace it at first sign-in.
            must_change_password=True,
        )
    )
    await db.commit()
    logger.warning(
        "Aucun compte ne pouvait administrer le fonds : compte d'amorçage créé pour %s. "
        "Il doit changer son mot de passe à la première connexion.",
        email,
    )
    return True
