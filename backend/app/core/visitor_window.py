"""How many times one VISITOR may knock on a public door within a minute.

🔴 THE VISITOR, NOT THE GATEWAY. Behind the edge proxy the socket's peer is the proxy
itself: a window counted on it makes every visitor on the internet share ONE window, and
the first robot locks everybody out (measured on Le Comptoir RH, 28 Sept 2026). The caller
is read from the last hop of `X-Forwarded-For`, the one the proxy wrote (`audit`).

⚠️ ONE IMPLEMENTATION FOR EVERY PUBLIC DOOR of this product (the lookups, the sign-up):
two copies of a sliding window are two places where the next fix lands once.

⚠️ PER PROCESS, AND NOTHING STARTED IN THE LIFESPAN: each of the two workers keeps its own
window, so the effective ceiling is at most twice the figure. Harmless for a throttle
whose only job is to stop a robot.
"""

from __future__ import annotations

import time
from collections import deque

from fastapi import Request

from app.core import audit

_WINDOW_SECONDS = 60.0
#: Beyond this many callers held, the idle ones are forgotten: the table of a public route
#: must not grow with every address that ever called it.
_MAX_TRACKED = 4096


class VisitorWindow:
    """A sliding one-minute window per visitor, admitting at most `per_minute` calls."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._seen: dict[str, deque[float]] = {}

    def clear(self) -> None:
        self._seen.clear()

    def admit(self, request: Request) -> bool:
        """True and counted when the visitor is under the ceiling, False otherwise."""
        who = audit.client_address(request)
        now = time.monotonic()
        if len(self._seen) > _MAX_TRACKED:
            for idle in [
                key
                for key, window in self._seen.items()
                if not window or now - window[-1] > _WINDOW_SECONDS
            ]:
                del self._seen[idle]
        window = self._seen.setdefault(who, deque())
        while window and now - window[0] > _WINDOW_SECONDS:
            window.popleft()
        if len(window) >= self.per_minute:
            return False
        window.append(now)
        return True
