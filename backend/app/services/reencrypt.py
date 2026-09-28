"""Re-encrypt every encrypted value with the current data key, then PROVE it.

    python -m app.services.reencrypt --apercu      what would change; writes nothing
    python -m app.services.reencrypt               re-encrypts, proves, leaves a journal line
    python -m app.services.reencrypt --verifier    exit 0 only if everything is on the
                                                   current key alone (before dropping keys)

🔴 WHY IT EXISTS. The data key used to be derived from `SECRET_KEY` and there was no way to
change it without losing every encrypted value. The keyring (`core/crypto.py`) reads with
every key and writes with the first; this pass is what moves the stored values from the old
keys to the first one, so the old ones can then be dropped. The owner's procedure is
`docs/rotation_cle_donnees.ps1`.

🔴 NOTHING IS WRITTEN UNLESS EVERY VALUE IS READABLE. The pass measures first; a single value
no key of the ring opens stops it before the first write, loudly, with the row ids (never
the value). Re-encrypting around a hole would report success over a lost number.

⚠️ ONE TRANSACTION PER BATCH, AND A COMPARE-AND-SWAP ON EACH ROW. The application keeps
running while the pass works: a value the application rewrites meanwhile is already on the
current key, and the `WHERE column = old` keeps the pass from overwriting it with the older
value it read. Two passes at once are therefore harmless, only wasteful.

⚠️ THE PROOF IS A SECOND MEASUREMENT, not the pass's own counters: every value opens with the
current key ALONE, the counts before and after are equal, and each value decrypts to exactly
what it held before (compared by a hash kept in memory, never printed). A fingerprint derived
from a value is recomputed and checked with it.

⚠️ COPIES IN THE AUDIT JOURNAL ARE MASKED, NOT RE-ENCRYPTED. A journal line that kept a
ciphertext keeps a secret under a key that is being retired, in the one table the
supervision reads across every firm. The journal rules mask these columns by name today;
older lines that predate the rule are brought into line here.

⚠️ NEVER PRINTS A CLEAR VALUE OR A KEY. Counts, row ids, and the short key id of
`crypto.key_id` — nothing that opens anything.

⚠️ RAW SQL THROUGH THE SESSION, deliberately. The ORM path would put every row through the
tenant scope (a job belongs to no tenant, so it would see nothing and prove nothing) and
through the journal's listeners (one line per row); the pass writes ONE line about itself
instead, like the retention's `retention.purge`.

⚠️ WRITTEN IDENTICALLY IN LE COMPTOIR INVEST AND LE COMPTOIR RH. Only the block that lists
the encrypted columns, and where the owner's language comes from, differ: a fix made here
is copied there.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import bindparam, func, insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit_rules, crypto
from app.core.i18n import pick
from app.models.audit_log import AuditLog


@dataclass(frozen=True)
class EncryptedField:
    """One encrypted column, and the column derived from its clear value, if any."""

    table: str
    column: str
    #: A column computed from the CLEAR value with the data key (a matching fingerprint):
    #: it follows the key, so it is recomputed with the ciphertext.
    derived: str | None = None
    derive: Callable[[str], str | None] | None = None

    @property
    def name(self) -> str:
        return f"{self.table}.{self.column}"


# ── What this product encrypts: the block that differs between the products ──────

#: 🔴 EVERY ENCRYPTED COLUMN OF THIS PRODUCT. A column encrypted with `crypto.encrypt` and
#: missing here is a column the rotation leaves on the old key — and the day that key is
#: dropped, its values read as absent. `test_every_encrypted_column_is_known_to_the_pass`
#: compares this list to the columns the models declare.
FIELDS: tuple[EncryptedField, ...] = (
    EncryptedField(
        "investors",
        "iban_encrypted",
        derived="iban_fingerprint",
        derive=crypto.fingerprint,
    ),
)

# ─────────────────────────────────────────────────────────────────────────────

#: The action of the line the pass writes about itself.
REENCRYPT = "encryption.reencrypt"

#: Who the line says did it: the pass, run by hand from the server.
ACTOR = "reencrypt (manual)"

DEFAULT_BATCH = 200


class Unreadable(RuntimeError):
    """At least one stored value opens with no key of the ring.

    `midway` is False when it was found by the first measurement, before any write — the
    normal case. True only if such a value appeared WHILE the pass ran: the batches already
    committed are sound (every key is still in the ring), the current one was not written.
    """

    def __init__(self, where: str, *, midway: bool = False) -> None:
        super().__init__(where)
        self.midway = midway


@dataclass
class FieldState:
    name: str
    values: int = 0
    on_current_key: int = 0
    unreadable: list[str] = field(default_factory=list)
    stale_derived: int = 0
    has_derived: bool = False

    @property
    def to_reencrypt(self) -> int:
        return self.values - self.on_current_key - len(self.unreadable)


@dataclass
class State:
    """One measurement of the stored values. `digests` never leaves this process."""

    fields: list[FieldState]
    journal_copies: int
    digests: dict[tuple[str, str], str] = field(default_factory=dict, repr=False)

    @property
    def unreadable(self) -> int:
        return sum(len(f.unreadable) for f in self.fields)

    @property
    def settled(self) -> bool:
        """Everything on the current key alone, derived columns in step, journal clean."""
        return (
            self.unreadable == 0
            and all(f.to_reencrypt == 0 and f.stale_derived == 0 for f in self.fields)
            and self.journal_copies == 0
        )


@dataclass
class Outcome:
    before: State
    after: State
    reencrypted: int = 0
    rederived: int = 0
    journal_masked: int = 0
    changed_meanwhile: int = 0
    seconds: float = 0.0
    failures: list[str] = field(default_factory=list)

    @property
    def proved(self) -> bool:
        return not self.failures


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _rows(db: AsyncSession, f: EncryptedField, after: str | None, limit: int):
    derived = f", {f.derived}" if f.derived else ""
    where = " AND id > CAST(:after AS uuid)" if after is not None else ""
    return (
        await db.execute(
            text(
                f"SELECT id::text AS id, {f.column} AS token{derived} FROM {f.table} "
                f"WHERE {f.column} IS NOT NULL{where} ORDER BY id LIMIT :limit"
            ),
            {"after": after, "limit": limit} if after is not None else {"limit": limit},
        )
    ).all()


def _journal_keys() -> list[str]:
    keys: list[str] = []
    for f in FIELDS:
        keys.append(f.column)
        if f.derived:
            keys.append(f.derived)
    return keys


def _as_dict(details) -> dict:
    """A JSONB value as a fresh dict, whether the driver decoded it or not. A deep copy:
    the line is rewritten from it, never the row the driver handed over."""
    if isinstance(details, str):
        return json.loads(details)
    return json.loads(json.dumps(details))


def _masked_details(details: dict, keys: list[str]) -> dict | None:
    """The line with every copy of an encrypted column masked, or None when it holds none."""
    changed = False
    snapshot = details.get("snapshot")
    if isinstance(snapshot, dict):
        for key in keys:
            if snapshot.get(key) not in (None, audit_rules.MASK):
                snapshot[key] = audit_rules.MASK
                changed = True
    changes = details.get("changes")
    if isinstance(changes, dict):
        for key in keys:
            change = changes.get(key)
            if isinstance(change, dict):
                for side in ("old", "new"):
                    if change.get(side) not in (None, audit_rules.MASK):
                        change[side] = audit_rules.MASK
                        changed = True
    return details if changed else None


async def _journal_lines(db: AsyncSession, after: str | None, limit: int):
    """Journal lines about an encrypted table that name one of its encrypted columns."""
    keys = _journal_keys()
    tables = sorted({f.table for f in FIELDS})
    where = " AND id > CAST(:after AS uuid)" if after is not None else ""
    statement = text(
        "SELECT id::text AS id, details FROM audit_logs "
        "WHERE entity_type IN :tables AND details IS NOT NULL "
        "AND (jsonb_exists_any(COALESCE(details->'snapshot', '{}'::jsonb), :keys) "
        "OR jsonb_exists_any(COALESCE(details->'changes', '{}'::jsonb), :keys))"
        f"{where} ORDER BY id LIMIT :limit"
    ).bindparams(bindparam("tables", expanding=True))
    params: dict = {"tables": tables, "keys": keys, "limit": limit}
    if after is not None:
        params["after"] = after
    return (await db.execute(statement, params)).all()


async def measure(db: AsyncSession, *, batch: int = DEFAULT_BATCH) -> State:
    """Read every stored value and say where it stands. Writes nothing."""
    states: list[FieldState] = []
    digests: dict[tuple[str, str], str] = {}
    for f in FIELDS:
        state = FieldState(f.name, has_derived=bool(f.derived))
        after: str | None = None
        while True:
            rows = await _rows(db, f, after, batch)
            if not rows:
                break
            for row in rows:
                state.values += 1
                clear = crypto.decrypt(row.token)
                if clear is None:
                    state.unreadable.append(row.id)
                    continue
                digests[(f.name, row.id)] = _digest(clear)
                if crypto.is_current(row.token):
                    state.on_current_key += 1
                if (
                    f.derived
                    and f.derive
                    and getattr(row, f.derived) != f.derive(clear)
                ):
                    state.stale_derived += 1
            after = rows[-1].id
        states.append(state)

    keys = _journal_keys()
    copies = 0
    after = None
    while True:
        lines = await _journal_lines(db, after, batch)
        if not lines:
            break
        copies += sum(
            1
            for line in lines
            if _masked_details(_as_dict(line.details), keys) is not None
        )
        after = lines[-1].id
    return State(states, copies, digests)


async def _reencrypt_field(
    db: AsyncSession, f: EncryptedField, batch: int, out: Outcome
):
    after: str | None = None
    while True:
        rows = await _rows(db, f, after, batch)
        if not rows:
            break
        for row in rows:
            clear = crypto.decrypt(row.token)
            if clear is None:
                # Measured readable a moment ago: somebody wrote an unreadable value since.
                # This batch is never committed; the batches before it are sound.
                raise Unreadable(f"{f.name} {row.id}", midway=True)
            token = (
                row.token if crypto.is_current(row.token) else crypto.rotate(row.token)
            )
            values: dict = {"id": row.id, "old": row.token, "new": token}
            sets = [f"{f.column} = :new"]
            derived_changed = False
            if f.derived and f.derive:
                derived = f.derive(clear)
                derived_changed = getattr(row, f.derived) != derived
                values["derived"] = derived
                sets.append(f"{f.derived} = :derived")
            if token == row.token and not derived_changed:
                continue
            result = await db.execute(
                text(
                    f"UPDATE {f.table} SET {', '.join(sets)} "
                    f"WHERE id = CAST(:id AS uuid) AND {f.column} = :old"
                ),
                values,
            )
            if not result.rowcount:
                out.changed_meanwhile += 1
                continue
            if token != row.token:
                out.reencrypted += 1
            if derived_changed:
                out.rederived += 1
        await db.commit()
        after = rows[-1].id


async def _mask_journal(db: AsyncSession, batch: int, out: Outcome) -> None:
    keys = _journal_keys()
    after: str | None = None
    while True:
        lines = await _journal_lines(db, after, batch)
        if not lines:
            break
        for line in lines:
            masked = _masked_details(_as_dict(line.details), keys)
            if masked is None:
                continue
            await db.execute(
                text(
                    "UPDATE audit_logs SET details = CAST(CAST(:details AS text) AS jsonb) "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"id": line.id, "details": json.dumps(masked)},
            )
            out.journal_masked += 1
        await db.commit()
        after = lines[-1].id


def _prove(before: State, after: State) -> list[str]:
    """What the second measurement must show. Each failure is a sentence for the owner."""
    failures: list[str] = []
    if after.unreadable:
        failures.append(
            pick(
                f"{after.unreadable} valeur(s) illisible(s) après le passage.",
                f"{after.unreadable} unreadable value(s) after the pass.",
            )
        )
    for f_before, f_after in zip(before.fields, after.fields, strict=True):
        if f_before.values != f_after.values:
            failures.append(
                pick(
                    f"{f_after.name} : {f_before.values} valeur(s) avant, "
                    f"{f_after.values} après.",
                    f"{f_after.name}: {f_before.values} value(s) before, "
                    f"{f_after.values} after.",
                )
            )
        if f_after.to_reencrypt:
            failures.append(
                pick(
                    f"{f_after.name} : {f_after.to_reencrypt} valeur(s) encore sur une "
                    "ancienne clé.",
                    f"{f_after.name}: {f_after.to_reencrypt} value(s) still on an old key.",
                )
            )
        if f_after.stale_derived:
            failures.append(
                pick(
                    f"{f_after.name} : {f_after.stale_derived} empreinte(s) pas à jour.",
                    f"{f_after.name}: {f_after.stale_derived} fingerprint(s) out of step.",
                )
            )
    if before.digests != after.digests:
        failures.append(
            pick(
                "Au moins une valeur ne se déchiffre plus à l'identique (ou a été "
                "modifiée pendant le passage) : relancer le passage, puis comparer.",
                "At least one value no longer decrypts to what it held (or was edited "
                "during the pass): run the pass again, then compare.",
            )
        )
    if after.journal_copies:
        failures.append(
            pick(
                f"{after.journal_copies} ligne(s) du journal gardent une copie chiffrée.",
                f"{after.journal_copies} journal line(s) still keep an encrypted copy.",
            )
        )
    return failures


async def reencrypt(db: AsyncSession, *, batch: int = DEFAULT_BATCH) -> Outcome:
    """Measure, re-encrypt, mask the journal copies, measure again, and record the run.

    Raises `Unreadable` BEFORE ANY WRITE when a value opens with no key of the ring.
    """
    started = time.monotonic()
    before = await measure(db, batch=batch)
    if before.unreadable:
        raise Unreadable(
            "; ".join(f"{f.name} {', '.join(f.unreadable[:20])}" for f in before.fields)
        )
    out = Outcome(before=before, after=before)
    for f in FIELDS:
        await _reencrypt_field(db, f, batch, out)
    await _mask_journal(db, batch, out)
    out.after = await measure(db, batch=batch)
    out.failures = _prove(before, out.after)
    out.seconds = round(time.monotonic() - started, 3)

    # ⚠️ A DIRECT INSERT, as the retention's: the line is about the data, written by nobody.
    await db.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            created_at=func.now(),
            user_id=None,
            user_email=ACTOR,
            action=REENCRYPT,
            entity_type=",".join(sorted({f.table for f in FIELDS})),
            entity_id=None,
            details={
                "values": sum(f.values for f in before.fields),
                "reencrypted": out.reencrypted,
                "rederived": out.rederived,
                "journal_masked": out.journal_masked,
                "changed_meanwhile": out.changed_meanwhile,
                "keys_in_ring": len(crypto.keyring()),
                "current_key": crypto.key_id(crypto.keyring()[0]),
                "proved": out.proved,
                "duration_ms": int(out.seconds * 1000),
            },
            ip_address=None,
        )
    )
    await db.commit()
    return out


# ── The command ───────────────────────────────────────────────────────────────


def _print_state(state: State) -> None:
    ring = crypto.keyring()
    print(
        pick(
            f"Trousseau : {len(ring)} clé(s), clé courante {crypto.key_id(ring[0])}"
            f"{'' if crypto.is_explicit() else ' (dérivée de SECRET_KEY)'}.",
            f"Keyring: {len(ring)} key(s), current key {crypto.key_id(ring[0])}"
            f"{'' if crypto.is_explicit() else ' (derived from SECRET_KEY)'}.",
        )
    )
    for f in state.fields:
        print(
            pick(
                f"  {f.name} : {f.values} valeur(s), {f.on_current_key} déjà sur la clé "
                f"courante, {f.to_reencrypt} à rechiffrer, {len(f.unreadable)} illisible(s)"
                + (
                    f", {f.stale_derived} empreinte(s) à recalculer"
                    if f.has_derived
                    else ""
                )
                + ".",
                f"  {f.name}: {f.values} value(s), {f.on_current_key} already on the "
                f"current key, {f.to_reencrypt} to re-encrypt, {len(f.unreadable)} "
                "unreadable"
                + (
                    f", {f.stale_derived} fingerprint(s) to recompute"
                    if f.has_derived
                    else ""
                )
                + ".",
            )
        )
        if f.unreadable:
            print(
                pick(
                    f"    illisibles (id) : {', '.join(f.unreadable[:20])}",
                    f"    unreadable (id): {', '.join(f.unreadable[:20])}",
                )
            )
    print(
        pick(
            f"  journal d'audit : {state.journal_copies} ligne(s) gardant une copie à masquer.",
            f"  audit journal: {state.journal_copies} line(s) keeping a copy to mask.",
        )
    )


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.services.reencrypt")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apercu", action="store_true")
    mode.add_argument("--verifier", action="store_true")
    parser.add_argument("--taille-lot", type=int, default=DEFAULT_BATCH)
    args = parser.parse_args(argv)
    batch = max(1, args.taille_lot)

    from pydantic import ValidationError
    from sqlalchemy.exc import SQLAlchemyError

    try:
        from app.database import AsyncSessionLocal, engine
    except ValidationError as exc:
        # The settings refused to load. Their own sentence only: the error also carries
        # the values it was given, a database password among them.
        reason = exc.errors()[0].get("msg", "") if exc.errors() else ""
        print(
            pick(
                f"ECHEC de configuration : {reason}", f"Configuration FAILED: {reason}"
            )
        )
        return 2

    # ⚠️ NEVER ECHO, whatever `DEBUG` says: a SQL log of this pass prints every ciphertext
    # it reads and writes, which is exactly the copy the pass exists to retire.
    engine.sync_engine.echo = False
    try:
        async with AsyncSessionLocal() as db:
            if args.apercu or args.verifier:
                state = await measure(db, batch=batch)
                _print_state(state)
                if state.unreadable:
                    print(
                        pick(
                            "ECHEC : des valeurs ne s'ouvrent avec aucune clé du trousseau.",
                            "FAILED: some values open with no key of the keyring.",
                        )
                    )
                    return 1
                if args.verifier:
                    if not state.settled:
                        print(
                            pick(
                                "NON : tout n'est pas encore sur la clé courante seule.",
                                "NO: not everything is on the current key alone yet.",
                            )
                        )
                        return 3
                    print(
                        pick(
                            "OK : tout s'ouvre avec la clé courante seule.",
                            "OK: everything opens with the current key alone.",
                        )
                    )
                return 0

            try:
                out = await reencrypt(db, batch=batch)
            except Unreadable as exc:
                if exc.midway:
                    print(
                        pick(
                            f"ECHEC : une valeur illisible est apparue pendant le passage "
                            f"({exc}). Les lots déjà écrits sont justes et toutes les clés "
                            "restent dans le trousseau.",
                            f"FAILED: an unreadable value appeared during the pass ({exc}). "
                            "The batches already written are sound and every key is still "
                            "in the ring.",
                        )
                    )
                else:
                    print(
                        pick(
                            f"ECHEC, rien n'a été écrit : valeur(s) illisible(s) ({exc}).",
                            f"FAILED, nothing was written: unreadable value(s) ({exc}).",
                        )
                    )
                return 1
            print(pick("Avant :", "Before:"))
            _print_state(out.before)
            print(
                pick(
                    f"Rechiffrées : {out.reencrypted} ; empreintes recalculées : "
                    f"{out.rederived} ; copies masquées dans le journal : "
                    f"{out.journal_masked} ; modifiées pendant le passage : "
                    f"{out.changed_meanwhile} ; durée : {out.seconds} s.",
                    f"Re-encrypted: {out.reencrypted}; fingerprints recomputed: "
                    f"{out.rederived}; journal copies masked: {out.journal_masked}; "
                    f"edited during the pass: {out.changed_meanwhile}; took {out.seconds} s.",
                )
            )
            print(pick("Après :", "After:"))
            _print_state(out.after)
            if not out.proved:
                for failure in out.failures:
                    print(pick(f"PREUVE KO : {failure}", f"PROOF FAILED: {failure}"))
                return 1
            print(
                pick(
                    "PREUVE OK : chaque valeur s'ouvre avec la clé courante seule, les "
                    "comptes avant et après sont égaux, aucune valeur perdue ni modifiée.",
                    "PROOF OK: every value opens with the current key alone, counts before "
                    "and after are equal, no value lost or altered.",
                )
            )
            return 0
    except SQLAlchemyError as exc:
        # The driver's own sentence, never the statement: its parameters are ciphertexts.
        reason = str(getattr(exc, "orig", None) or type(exc).__name__).splitlines()[0]
        print(
            pick(
                f"ECHEC de la base : {reason[:200]}", f"Database FAILED: {reason[:200]}"
            )
        )
        return 2
    except RuntimeError as exc:
        # A malformed keyring or a missing secret: said, never shown.
        print(pick(f"ECHEC de configuration : {exc}", f"Configuration FAILED: {exc}"))
        return 2
    finally:
        await engine.dispose()


if __name__ == "__main__":  # pragma: no cover - the manual door
    sys.exit(asyncio.run(_main(sys.argv[1:])))
