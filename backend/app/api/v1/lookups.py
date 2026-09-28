"""The common lookups, relayed to the console: countries, company numbers, addresses.

🔴 NOTHING IS ANSWERED HERE (the manager, 28 Sept 2026: everything common lives in Alice,
reachable by API). A screen asks this server -- the gateway's security
policy is `connect-src 'self'`, so a browser call to a register would be blocked, silently
-- and this server asks Alice's `/internal/lookups/*` through `alice_client`, with the
OUTBOUND key. Same paths and same fail-soft answers as Le Comptoir RH, the reference.

⚠️ FAIL-SOFT, AND SAID. When the console does not answer, an address is typed by hand
and a company number reads « unreachable », never « not found ».

⚠️ UNAUTHENTICATED ON PURPOSE: a sign-up form asks before any account exists. Hence the
limiter, which is PER PROCESS and starts nothing in the lifespan: each of the two workers
keeps its own window, so the effective ceiling is at most twice the figure. Harmless for a
throttle whose only job is to stop a robot from draining the console's registers through
this door.
"""

from __future__ import annotations

import time
from collections import deque

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core import audit
from app.core.i18n import pick
from app.services import alice_client

router = APIRouter(prefix="/public/lookups", tags=["public"])

#: France, when the console cannot give its list: a form must still open.
_FRANCE_ONLY = [{"code": "FR", "name": "France", "number_label": "SIREN / SIRET"}]

#: A form types letter after letter: generous, but a robot is still stopped.
LOOKUPS_PER_MINUTE = 60
_WINDOW_SECONDS = 60.0
#: Beyond this many addresses held, the idle ones are forgotten: the table of a public
#: route must not grow with every address that ever called it.
_MAX_TRACKED = 4096
_recent: dict[str, deque[float]] = {}


def _limited(request: Request) -> None:
    # The edge proxy's hop, not the socket: behind it every caller shares one peer, and a
    # per-socket window would throttle the whole internet as one visitor.
    who = audit.client_address(request)
    now = time.monotonic()
    if len(_recent) > _MAX_TRACKED:
        for idle in [
            k for k, w in _recent.items() if not w or now - w[-1] > _WINDOW_SECONDS
        ]:
            del _recent[idle]
    window = _recent.setdefault(who, deque())
    while window and now - window[0] > _WINDOW_SECONDS:
        window.popleft()
    if len(window) >= LOOKUPS_PER_MINUTE:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            pick(
                "Trop de recherches : patientez un instant.",
                "Too many searches: please wait a moment.",
            ),
        )
    window.append(now)


@router.get("/countries", dependencies=[Depends(_limited)])
async def countries() -> list[dict]:
    return await alice_client.lookup("countries", {}, _FRANCE_ONLY)


@router.get("/company", dependencies=[Depends(_limited)])
async def company(number: str = Query(..., max_length=40)) -> dict:
    return await alice_client.lookup(
        "company", {"number": number}, {"status": "unreachable"}
    )


@router.get("/address", dependencies=[Depends(_limited)])
async def address(
    q: str = Query(..., max_length=200), country: str = Query("FR", max_length=60)
) -> list[dict]:
    return await alice_client.lookup("address", {"q": q, "country": country}, [])


@router.get("/town", dependencies=[Depends(_limited)])
async def town(
    q: str = Query(..., max_length=120), country: str = Query("FR", max_length=60)
) -> list[dict]:
    return await alice_client.lookup("town", {"q": q, "country": country}, [])
