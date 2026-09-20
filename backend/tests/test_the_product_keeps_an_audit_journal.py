"""The product keeps an audit journal, and the supervision can read it.

The manager, 20 Sept 2026: « à ajouter, toujours ajouter », for every new product. This
product holds other people's money and went to production with no journal and no
`/internal/audit`: Portail360 had nothing to show for it.

Two things are this product's own. A bank line ARRIVES by import, so its creation is not
somebody's act while what is done to it afterwards is; and an account number is never
copied in clear into a journal.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.api.v1 import internal_admin
from app.core import audit, audit_rules
from app.models import Base
from app.models.audit_log import AuditLog
from app.models.project import ACTIVE, Project
from app.models.treasury import IN, BankMovement

IBAN = "FR7630006000011234567890189"


async def _lines(db, table: str) -> list[AuditLog]:
    return list(
        (
            await db.execute(
                select(AuditLog)
                .where(AuditLog.entity_type == table)
                .order_by(AuditLog.created_at)
            )
        )
        .scalars()
        .all()
    )


def test_every_table_has_said_whether_it_is_audited():
    undecided = [t for t in Base.metadata.tables if not audit_rules.has_chosen(t)]
    assert undecided == [], f"file them in AUDITED or NEVER_AUDITED: {undecided}"


def test_an_account_number_is_masked_and_a_compliance_note_is_withheld():
    for column in (
        "iban_encrypted",
        "iban_fingerprint",
        "account_iban",
        "counterparty_iban",
    ):
        assert audit_rules.masked(column, IBAN) == audit_rules.MASK, column
    assert (
        audit_rules.masked("identity_document_number", "12AB34567") == audit_rules.MASK
    )
    assert audit_rules.masked("hashed_password", "x") == audit_rules.MASK
    assert (
        audit_rules.masked("kyc_reason", "PEP, vigilance renforcée")
        == audit_rules.WITHHELD
    )
    assert audit_rules.masked("last_name", "Diallo") == "Diallo"


async def test_a_change_is_written_with_its_author_and_its_old_value(db):
    token = audit.set_actor(ip="203.0.113.9")
    try:
        audit.identify(user_id=uuid.uuid4(), user_email="gerant@fonds.fr")
        project = Project(name="Résidence du Port", currency="EUR", status=ACTIVE)
        db.add(project)
        await db.flush()
        project.name = "Résidence du Vieux-Port"
        await db.flush()
    finally:
        audit.reset_actor(token)

    lines = await _lines(db, "projects")
    assert [x.action for x in lines] == [audit_rules.CREATE, audit_rules.UPDATE]
    assert lines[0].entity_id == str(project.id), "a created row has its id by then"
    assert lines[1].user_email == "gerant@fonds.fr"
    assert lines[1].ip_address == "203.0.113.9"
    assert lines[1].details["changes"]["name"] == {
        "old": "Résidence du Port",
        "new": "Résidence du Vieux-Port",
    }


async def test_a_bank_line_enters_the_journal_when_somebody_handles_it_not_when_it_arrives(
    db,
):
    movement = BankMovement(
        account_iban=IBAN,
        direction=IN,
        amount=Decimal("50000"),
        currency="EUR",
        value_date=date(2026, 3, 1),
    )
    db.add(movement)
    await db.flush()
    assert await _lines(db, "bank_movements") == [], "an import is the bank's act"

    movement.label = "Souscription Diallo"
    await db.flush()
    (line,) = await _lines(db, "bank_movements")
    assert line.action == audit_rules.UPDATE
    assert IBAN not in str(line.details)


async def test_the_supervision_reads_the_journal_in_the_house_s_shape(db):
    db.add(Project(name="Tour Sud", currency="EUR", status=ACTIVE))
    await db.flush()
    rows = await internal_admin.audit_journal(
        limit=100,
        skip=0,
        action=None,
        user_email=None,
        entity_type="projects",
        _=None,
        db=db,
    )
    assert len(rows) >= 1
    assert set(rows[0]) == {
        "id",
        "created_at",
        "user_id",
        "user_email",
        "action",
        "entity_type",
        "entity_id",
        "details",
        "ip_address",
    }


def test_an_actor_put_back_does_not_stamp_the_next_request():
    token = audit.set_actor(user_email="premier@fonds.fr", ip="10.0.0.1")
    audit.reset_actor(token)
    assert audit.current_actor() == {}
    audit.reset_actor(token)  # a second reset must not raise, nor bring the actor back
    assert audit.current_actor() == {}
