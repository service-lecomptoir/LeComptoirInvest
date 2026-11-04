"""Remove the second factor of an account whose holder lost their phone, from the server.

    docker exec -it invest_backend python -m scripts.reset_two_factor <login e-mail>
    docker exec -it invest_backend python -m scripts.reset_two_factor <login e-mail> --yes

🔴 NO SCREEN OF THIS PRODUCT ADMINISTERS ANOTHER ACCOUNT (3 Nov 2026). The managers (the
subscriber and the colleagues of its management company) and the platform's administrator
are created, blocked and reset by the console (Alice) through `/internal`; no screen of the
fund opens, blocks or resets a colleague's or an investor's login. Their way out is this
command, never a route: a route that removes the factor would be the one door a stolen
password needs, and a shell on the server is a factor of its own. The same answer as the
console of Alice for its own administrators, and as the sibling products for the accounts
no screen of theirs administers.

What it does, and nothing more:
- it names the account and asks for a confirmation (unless `--yes`);
- it removes the secret, the backup codes and the activation;
- it writes `two_factor.reset` in the audit journal (`by` = the server account running it);
- it e-mails the person that their second factor was removed, in the look their management
  company chose (a refused send is printed, the reset stands).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import socket
import sys

from sqlalchemy import func, select

import app.models  # noqa: F401 - the journal's listeners and the whole schema
from app.core import audit
from app.database import AsyncSessionLocal
from app.models.user import User
from app.services import two_factor_service


def _operator() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 - no login name inside some containers
        user = "server"
    return f"script:{user}@{socket.gethostname()}"


async def reset(email: str, *, assume_yes: bool) -> int:
    operator = _operator()
    token = audit.set_actor(user_email=operator)
    try:
        async with AsyncSessionLocal() as db:
            user = await db.scalar(
                select(User).where(func.lower(User.email) == email.strip().lower())
            )
            if user is None:
                print(f"No account with the address {email}.")
                return 1
            name = user.account_name or user.email
            if not await two_factor_service.is_enabled(db, user):
                print(f"{name} ({user.email}) has no two-factor authentication on.")
                return 0
            print(f"Account: {name} ({user.email}), role {user.role}")
            if not assume_yes:
                answer = input("Remove its two-factor authentication? Type YES: ")
                if answer.strip() != "YES":
                    print("Nothing was changed.")
                    return 1
            await two_factor_service.reset_by(db, user, operator)
            await db.commit()
            print("Two-factor authentication removed (journal: two_factor.reset).")
            sent = await two_factor_service.notify_reset(db, user)
        print("E-mail sent to the person." if sent else "E-mail NOT sent.")
        return 0
    finally:
        audit.reset_actor(token)


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("email", help="the account's login e-mail")
    parser.add_argument(
        "--yes", action="store_true", help="do not ask for a confirmation"
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(reset(args.email, assume_yes=args.yes)))


if __name__ == "__main__":
    main()
