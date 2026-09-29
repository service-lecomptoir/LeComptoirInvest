"""The e-mail looks this product may wear: Alice's catalogue, kept here, and each account's choice.

🔴 THE CATALOGUE LIVES IN ALICE (the manager, 29 Sept 2026: everything common lives in Alice,
reachable by API). `GET /internal/email-themes?app=invest` returns the looks, their families
and the default the console set for this product (Alice > Communication > « Apparence par
défaut des e-mails »). Nothing about a look is written in this repository: a look added in
the console is offered here and dresses the letters without a deploy.

🔴 THE CONSOLE'S CONTRACT, AND THIS MODULE IS WHERE IT IS KEPT:

  * a console that cannot be reached leaves the LAST COPY in force, however old;
  * with no copy at all, the letter wears `email_envelope.BUILT_IN` (its name, a rule, the
    signature): never a naked mail, and never a refused send because of a catalogue;
  * a key the copy does not know renders with the catalogue's `default`.

⚠️ THE COPY IS REVALIDATED, NOT REFETCHED. The console tags its answer; after five minutes
this module asks again with `If-None-Match` and a 304 costs no body. A failed attempt is
retried after thirty seconds rather than five minutes, so a console back from an outage is
seen quickly without a letter per second asking it.

🔴 THE CHOICE BELONGS TO THE ACCOUNT THAT SENDS THE LETTERS: the management company, i.e.
the account row `firm_of(user)` points at (`users.email_theme`). NULL means « the product's
look », the console's default, and it follows that default when the console changes it.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email_envelope import BUILT_IN, Look
from app.core.i18n import pick
from app.models.user import User
from app.services import alice_client

logger = logging.getLogger(__name__)

#: The console's own `max-age`: a copy younger than this is used without asking.
_TTL_SECONDS = 300.0
#: After a failed attempt: short, so the console's return is noticed, and not zero, so an
#: outage does not cost every letter a five-second timeout.
_RETRY_SECONDS = 30.0


@dataclass(frozen=True)
class Catalogue:
    """The console's catalogue as this product keeps it: only entries it can render."""

    #: `{key, name, hint}`, in the console's order.
    families: tuple[dict[str, str], ...]
    #: `{key, name, description, family, layout, ink, accent, soft}`, in the console's order.
    themes: tuple[dict[str, str], ...]
    #: The look this product wears when nobody chose one. None when the console named a
    #: look it does not list, which leaves the built-in look.
    default: str | None

    def look(self, key: str | None) -> Look | None:
        for theme in self.themes:
            if theme["key"] == key:
                return Look.parse(theme)
        return None


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _parse(body: object) -> Catalogue | None:
    """The usable part of an answer, or None when there is nothing to render with.

    ⚠️ AN ENTRY THAT CANNOT BE RENDERED IS DROPPED, not the whole answer: one malformed look
    must not cost the others. An answer with no usable look at all is no catalogue, and the
    copy already kept stays in force.
    """
    if not isinstance(body, dict):
        return None
    themes = []
    for raw in body.get("themes") or []:
        look = Look.parse(raw)
        if look is None:
            continue
        themes.append(
            {
                "key": look.key,
                "name": _text(raw.get("name")) or look.key,
                "description": _text(raw.get("description")),
                "family": _text(raw.get("family")),
                "layout": look.layout,
                "ink": look.ink,
                "accent": look.accent,
                "soft": look.soft,
            }
        )
    if not themes:
        return None
    families = tuple(
        {
            "key": _text(raw.get("key")),
            "name": _text(raw.get("name")) or _text(raw.get("key")),
            "hint": _text(raw.get("hint")),
        }
        for raw in body.get("families") or []
        if isinstance(raw, dict) and _text(raw.get("key"))
    )
    keys = {theme["key"] for theme in themes}
    default = body.get("default")
    return Catalogue(
        families=families,
        themes=tuple(themes),
        default=default if default in keys else None,
    )


_cache: dict = {"copy": None, "etag": None, "checked": None, "ok": False}


async def catalogue() -> Catalogue | None:
    """The catalogue in force: fresh, revalidated, or the last copy. None if never had."""
    now = time.monotonic()
    copy: Catalogue | None = _cache["copy"]
    wait = _TTL_SECONDS if _cache["ok"] else _RETRY_SECONDS
    if _cache["checked"] is not None and now - _cache["checked"] < wait:
        return copy

    answer = await alice_client.email_themes(_cache["etag"] if copy else None)
    _cache["checked"] = now
    if answer is None:
        _cache["ok"] = False
        return copy
    status, body, etag = answer
    if status == 304 and copy is not None:
        _cache["ok"] = True
        return copy
    parsed = _parse(body) if status == 200 else None
    if parsed is None:
        logger.warning("Alice email-themes: unusable answer, keeping the last copy")
        _cache["ok"] = False
        return copy
    _cache.update(copy=parsed, etag=etag, ok=True)
    return parsed


def forget() -> None:
    """Drop the copy, so the next read asks the console as if for the first time."""
    _cache.update(copy=None, etag=None, checked=None, ok=False)


async def look_for(key: str | None) -> Look:
    """The look a letter wears for this choice: the one chosen, else the default, else ours."""
    kept = await catalogue()
    if kept is None:
        return BUILT_IN
    return kept.look(key) or kept.look(kept.default) or BUILT_IN


async def chosen_by(db: AsyncSession, firm_id: uuid.UUID | None) -> str | None:
    """The look the management company chose, or None for the product's own."""
    if firm_id is None:
        return None
    return (
        await db.execute(select(User.email_theme).where(User.id == firm_id))
    ).scalar_one_or_none()


async def look_for_firm(db: AsyncSession, firm_id: uuid.UUID | None) -> Look:
    """The look of a letter sent on behalf of this management company.

    A letter with no company behind it, or a company that chose nothing, wears the default.
    """
    return await look_for(await chosen_by(db, firm_id))


class UnknownLook(ValueError):
    """The key is not in the console's catalogue: nothing could render it."""


class CatalogueOutOfReach(RuntimeError):
    """The console does not answer and no copy of its catalogue is kept here."""


async def check_choice(key: str) -> str:
    """The key, once the catalogue in force lists it.

    ⚠️ THE LAST COPY IS ENOUGH. A console that is down must not stop a manager choosing a
    look this product already knows; only a key nobody can check is refused, and it says
    why rather than storing a choice that might render as nothing.
    """
    kept = await catalogue()
    if kept is None:
        raise CatalogueOutOfReach(
            pick(
                "La console ne répond pas et aucune copie de son catalogue n'est gardée "
                "ici : réessayez dans un instant.",
                "The console does not answer and no copy of its catalogue is kept here: "
                "try again in a moment.",
            )
        )
    if kept.look(key) is None:
        raise UnknownLook(
            pick(
                f"L'apparence « {key} » n'existe pas dans le catalogue de la console : "
                "choisissez-en une dans la liste.",
                f"The look « {key} » is not in the console's catalogue: pick one from the "
                "list.",
            )
        )
    return key


__all__ = [
    "Catalogue",
    "CatalogueOutOfReach",
    "UnknownLook",
    "catalogue",
    "check_choice",
    "chosen_by",
    "forget",
    "look_for",
    "look_for_firm",
]
