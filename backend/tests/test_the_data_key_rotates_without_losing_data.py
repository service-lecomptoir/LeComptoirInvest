"""The data key rotates and no IBAN is lost: the re-encryption pass, against the database.

🔴 WHAT THE OWNER RUNS IN PRODUCTION IS WHAT IS MEASURED HERE. A new key is put first in
`DATA_ENCRYPTION_KEYS`, the old one kept second; `app.services.reencrypt` moves every stored
value onto the new key and recomputes the fingerprints; the old key is then dropped and the
new one ALONE must read everything. Each promise the procedure relies on is one test:

  * the rotation, across two firms (the pass must not be narrowed by the firm scope);
  * the preview writes nothing;
  * a value no key opens stops the pass before its first write;
  * a second run re-encrypts nothing;
  * making the derived key explicit loses nothing, and frees the data from `SECRET_KEY`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, text

from app.config import get_settings
from app.core import audit_rules, crypto, firm_scope, kyc
from app.core.landlord_kind_values import PERSON
from app.models.audit_log import AuditLog
from app.models.investor import Investor
from app.services import reencrypt

OTHER_FIRM = uuid.UUID("22222222-2222-2222-2222-222222222222")
IBANS = ("FR7630006000011234567890189", "DE89370400440532013000")


@pytest.fixture
def ring(monkeypatch):
    settings = get_settings()

    def use(data_keys: str = "", secret: str | None = None) -> None:
        monkeypatch.setattr(settings, "DATA_ENCRYPTION_KEYS", data_keys)
        if secret is not None:
            monkeypatch.setattr(settings, "SECRET_KEY", secret)
        crypto.reset()

    yield use
    crypto.reset()


async def _investor(db, iban: str, firm: uuid.UUID | None = None) -> Investor:
    investor = Investor(
        id=uuid.uuid4(), kind=PERSON, last_name="Martin", kyc_status=kyc.ACCEPTED
    )
    investor.iban = iban
    if firm is None:
        db.add(investor)
        await db.flush()
    else:
        with firm_scope.use_firm(firm):
            db.add(investor)
            await db.flush()
    return investor


async def _stored(db) -> dict[str, tuple[str, str]]:
    rows = (
        await db.execute(
            text(
                "SELECT id::text AS id, iban_encrypted, iban_fingerprint FROM investors "
                "WHERE iban_encrypted IS NOT NULL"
            )
        )
    ).all()
    return {r.id: (r.iban_encrypted, r.iban_fingerprint) for r in rows}


async def _runs(db) -> int:
    return len(
        (
            await db.execute(
                select(AuditLog).where(AuditLog.action == reencrypt.REENCRYPT)
            )
        )
        .scalars()
        .all()
    )


async def test_rotate_reencrypt_and_the_new_key_alone_reads_everything(db, ring):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    ring(old)
    mine = await _investor(db, IBANS[0])
    theirs = await _investor(db, IBANS[1], firm=OTHER_FIRM)
    # A journal line written before the journal masked these columns: a ciphertext copy.
    journal_id = uuid.uuid4()
    db.add(
        AuditLog(
            id=journal_id,
            created_at=datetime.now(UTC),
            action="db.update",
            entity_type="investors",
            entity_id=str(mine.id),
            details={
                "changes": {"iban_encrypted": {"old": None, "new": mine.iban_encrypted}}
            },
        )
    )
    await db.flush()

    ring(f"{new},{old}")
    preview = await reencrypt.measure(db)
    assert [(f.values, f.to_reencrypt, f.stale_derived) for f in preview.fields] == [
        (2, 2, 2)
    ]
    assert preview.journal_copies == 1

    out = await reencrypt.reencrypt(
        db, batch=1
    )  # one row per batch: the loop is walked
    assert out.proved, out.failures
    assert (out.reencrypted, out.rederived, out.journal_masked) == (2, 2, 1)
    assert out.after.settled

    ring(new)  # the old key is dropped
    stored = await _stored(db)
    assert {crypto.decrypt(token) for token, _ in stored.values()} == set(IBANS)
    assert stored[str(theirs.id)][1] == crypto.fingerprint(IBANS[1])
    line = await db.get(AuditLog, journal_id)
    await db.refresh(line)
    assert line.details["changes"]["iban_encrypted"] == {
        "old": None,
        "new": audit_rules.MASK,
    }
    assert await _runs(db) == 1


async def test_the_preview_writes_nothing(db, ring):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    ring(old)
    await _investor(db, IBANS[0])
    before = await _stored(db)

    ring(f"{new},{old}")
    state = await reencrypt.measure(db)
    assert state.fields[0].to_reencrypt == 1
    assert await _stored(db) == before
    assert await _runs(db) == 0


async def test_a_value_no_key_opens_stops_the_pass_before_any_write(db, ring):
    old, new, lost = (Fernet.generate_key().decode() for _ in range(3))
    ring(lost)
    await _investor(db, IBANS[1])
    ring(old)
    await _investor(db, IBANS[0])
    before = await _stored(db)

    ring(f"{new},{old}")
    with pytest.raises(reencrypt.Unreadable):
        await reencrypt.reencrypt(db)
    assert await _stored(db) == before, "nothing may be written around a lost value"
    assert await _runs(db) == 0


async def test_a_second_run_reencrypts_nothing(db, ring):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    ring(old)
    await _investor(db, IBANS[0])
    ring(f"{new},{old}")
    first = await reencrypt.reencrypt(db)
    assert first.reencrypted == 1
    after_first = await _stored(db)

    second = await reencrypt.reencrypt(db)
    assert second.proved, second.failures
    assert (second.reencrypted, second.rederived) == (0, 0)
    assert await _stored(db) == after_first


async def test_making_the_derived_key_explicit_loses_nothing(db, ring):
    ring("")  # today's production: the key derived from SECRET_KEY
    investor = await _investor(db, IBANS[0])
    token_before = investor.iban_encrypted

    ring(crypto.legacy_key())  # the first step of the procedure
    out = await reencrypt.reencrypt(db)
    assert out.proved, out.failures
    assert out.reencrypted == 0, "the values already sit on that very key"
    assert out.rederived == 1, "the fingerprint leaves the session secret"
    assert (await _stored(db))[str(investor.id)][0] == token_before

    ring(crypto.keyring()[0], secret="a-rotated-session-secret")
    assert crypto.decrypt(token_before) == IBANS[0]
