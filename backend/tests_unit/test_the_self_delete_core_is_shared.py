"""The rules of « Supprimer mon compte » every product shares (`app/core/self_delete.py`).

🔴 THE SAME FILE IN EVERY PRODUCT, like `two_factor.py`: the fingerprint below fails until
every copy is changed together. Then the rules the terms of use fix (CGU of Alice, 9.3):
thirty days of grace, a reminder seven days before, a day missed caught up, one month for
the agency to answer, an address compared without case or spaces, a tombstone that keeps
nothing personal. One rule per test.
"""

from __future__ import annotations

import hashlib
import pathlib
from datetime import date

from app.core import self_delete

SHARED_CORE_SHA256 = "974ece397475c28d7d9645726947f7fb18654bc95a163b3b8fa57e2ff4683906"


def test_the_core_is_the_shared_one():
    path = (
        pathlib.Path(__file__).resolve().parents[1] / "app" / "core" / "self_delete.py"
    )
    content = path.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(content).hexdigest() == SHARED_CORE_SHA256


def test_the_subscriber_s_space_is_erased_thirty_days_on():
    assert self_delete.erase_on(date(2026, 11, 12)) == date(2026, 12, 12)


def test_the_erasure_runs_on_its_day_and_catches_up_a_day_missed():
    day = date(2026, 12, 12)
    assert not self_delete.is_due(date(2026, 12, 11), day)
    assert self_delete.is_due(day, day)
    assert self_delete.is_due(date(2026, 12, 15), day)


def test_the_reminder_leaves_seven_days_before_and_once():
    day = date(2026, 12, 12)
    assert not self_delete.reminder_due(date(2026, 12, 4), day, already_reminded=False)
    assert self_delete.reminder_due(date(2026, 12, 5), day, already_reminded=False)
    assert self_delete.reminder_due(date(2026, 12, 9), day, already_reminded=False)
    assert not self_delete.reminder_due(date(2026, 12, 9), day, already_reminded=True)
    assert not self_delete.reminder_due(day, day, already_reminded=False)


def test_the_agency_answers_within_one_month_the_month_s_last_day_when_shorter():
    assert self_delete.answer_by(date(2026, 11, 12)) == date(2026, 12, 12)
    assert self_delete.answer_by(date(2027, 1, 31)) == date(2027, 2, 28)
    assert self_delete.answer_by(date(2026, 12, 15)) == date(2027, 1, 15)


def test_the_address_typed_is_compared_without_case_or_spaces():
    assert self_delete.same_address("  Jeanne@Exemple.fr ", "jeanne@exemple.fr")
    assert not self_delete.same_address("autre@exemple.fr", "jeanne@exemple.fr")
    assert not self_delete.same_address("", "")


def test_a_tombstone_empties_every_nullable_column_it_does_not_keep():
    columns = [
        ("id", False),
        ("email", False),
        ("phone", True),
        ("role", True),
        ("x", True),
    ]
    assert self_delete.erased_values(columns, kept={"role"}) == {
        "phone": None,
        "x": None,
    }


def test_a_tombstone_address_receives_nothing_and_is_unique():
    a, b = self_delete.tombstone_email("1"), self_delete.tombstone_email("2")
    assert a != b and a.endswith("@account.invalid")


def test_an_ended_space_is_erased_the_day_after_its_export_days():
    assert self_delete.ended_erase_on(date(2027, 3, 2)) == date(2027, 3, 3)


def test_no_ended_space_is_erased_before_thirty_days_after_the_launch():
    assert self_delete.FIRST_ERASURE_DAY == date(2026, 12, 20)
    assert (
        self_delete.ended_erase_on(date(2026, 10, 30)) == self_delete.FIRST_ERASURE_DAY
    )
