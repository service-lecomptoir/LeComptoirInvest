"""An account may ask a second factor: a TOTP code after the password.

The owner, 2 Nov 2026: offered to every account, recommended to whoever runs the fund (a
discreet banner), never an obligation in the product. With it on, the password alone opens
nothing but the second step of the sign-in, and a password link (which proves the mailbox,
not the phone) never opens a session on its own.

Every request goes through the REAL doors (`deps.current_user`, the routes the screens
call), so what is proved is what a browser gets.
"""

from __future__ import annotations

import contextlib
import hashlib
import pathlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select

from app.api.v1 import two_factor as two_factor_routes
from app.config import get_settings
from app.core import two_factor
from app.core.security import create_two_factor_pending_token, hash_password
from app.database import get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.two_factor import UserTwoFactor
from app.models.user import INVESTOR, MANAGER, User
from app.services import mailer, password_link_service

#: 🔴 THE SAME FILE IN EVERY PRODUCT (`docs/TWO_FACTOR.md` of Le Comptoir Alice lists the
#: copies): a copy changed here fails until all are changed.
SHARED_CORE_SHA256 = "1c4ace9b3cb1ff735d3e3cde99da5d0e2e08c4034b1bce4f642e54ae96301637"

KEY = "cle-interne-de-test"
PASSWORD = "mot-de-passe-du-gerant"


def _clear_windows() -> None:
    two_factor_routes._second_step_window.clear()
    two_factor_routes._settings_window.clear()


@pytest.fixture
async def client(db):
    settings = get_settings()
    previous = settings.ALICE_INTERNAL_KEY
    settings.ALICE_INTERNAL_KEY = KEY
    _clear_windows()

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://invest.test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    settings.ALICE_INTERNAL_KEY = previous
    _clear_windows()


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch) -> dict:
    """⚠️ THE TIME STEP IS HELD STILL: a sign-in here costs a bcrypt or two, and a code
    computed just before a thirty-second boundary would be read just after it. The window
    and the refusal of a replay are the core's, tested on the steps around it."""
    held = {"step": two_factor.current_step()}
    monkeypatch.setattr(two_factor, "current_step", lambda now=None: held["step"])
    return held


@pytest.fixture
def outbox(monkeypatch) -> list[dict]:
    sent: list[dict] = []

    async def _send(**letter):
        sent.append(letter)

    monkeypatch.setattr(mailer, "send", _send)
    return sent


def _code(secret: str, offset: int = 0) -> str:
    return two_factor.code_at(secret, two_factor.current_step() + offset)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _account(db, role: str = MANAGER) -> User:
    user = User(
        email=f"gerant-{uuid.uuid4().hex[:6]}@example.org",
        hashed_password=hash_password(PASSWORD),
        account_name="Gestion Rivoli",
        role=role,
        locale="fr",
        is_active=True,
        last_login_at=datetime.now(UTC),
    )
    db.add(user)
    await db.flush()
    return user


async def _login(client, user: User):
    return await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
    )


async def _enrol(client, user: User) -> tuple[str, str, list[str]]:
    """Signs in, sets up the factor, activates it: (secret, session token, backup codes)."""
    answer = await _login(client, user)
    assert answer.status_code == 200, answer.text
    token = answer.json()["access_token"]
    shown = await client.post("/api/v1/auth/two-factor/setup", headers=_bearer(token))
    assert shown.status_code == 200, shown.text
    secret = shown.json()["secret"]
    assert shown.json()["qr_code"].startswith("data:image/svg+xml")
    assert shown.json()["otpauth_uri"].startswith(
        "otpauth://totp/Le%20Comptoir%20Invest%3A"
    )
    # The code of the step before: the next sign-in's code is then strictly later.
    on = await client.post(
        "/api/v1/auth/two-factor/activate",
        headers=_bearer(token),
        json={"code": _code(secret, -1)},
    )
    assert on.status_code == 200, on.text
    return secret, token, on.json()["backup_codes"]


async def _second_step(client, user: User, **proof):
    first = await _login(client, user)
    assert first.status_code == 200, first.text
    assert first.json()["two_factor_required"] is True, first.text
    return await client.post(
        "/api/v1/auth/login/two-factor",
        json={"two_factor_token": first.json()["two_factor_token"], **proof},
    )


async def _actions(db, user: User) -> list[str]:
    rows = await db.execute(
        select(AuditLog.action)
        .where(AuditLog.entity_id == str(user.id))
        .order_by(AuditLog.created_at)
    )
    return [a for a in rows.scalars().all() if a.startswith("two_factor.")]


def test_the_two_factor_core_is_the_shared_one():
    path = (
        pathlib.Path(__file__).resolve().parents[1] / "app" / "core" / "two_factor.py"
    )
    content = path.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(content).hexdigest() == SHARED_CORE_SHA256


def test_the_codes_are_those_of_rfc_6238():
    key = b"12345678901234567890"
    assert two_factor.hotp(key, 59 // 30, 8) == "94287082"
    assert two_factor.hotp(key, 1111111109 // 30, 8) == "07081804"
    assert two_factor.hotp(key, 20000000000 // 30, 8) == "65353130"


async def test_without_it_the_password_signs_in_and_the_manager_is_invited(client, db):
    manager = await _account(db)
    answer = await _login(client, manager)
    assert answer.json()["access_token"]
    assert answer.json()["two_factor_required"] is False
    status = await client.get(
        "/api/v1/auth/two-factor", headers=_bearer(answer.json()["access_token"])
    )
    assert status.json() == {
        "enabled": False,
        "enabled_at": None,
        "backup_codes_remaining": 0,
        "recommended": True,
        "required": False,
    }


async def test_an_investor_may_switch_it_on_and_is_not_invited(client, db):
    investor = await _account(db, role=INVESTOR)
    answer = await _login(client, investor)
    session = _bearer(answer.json()["access_token"])
    status = (await client.get("/api/v1/auth/two-factor", headers=session)).json()
    assert status["recommended"] is False and status["enabled"] is False
    await _enrol(client, investor)
    assert (await _login(client, investor)).json()["two_factor_required"] is True


async def test_set_up_then_sign_in_with_the_code(client, db):
    manager = await _account(db)
    secret, _, codes = await _enrol(client, manager)
    assert len(codes) == 10 and len(set(codes)) == 10
    row = await db.scalar(
        select(UserTwoFactor).where(UserTwoFactor.user_id == manager.id)
    )
    await db.refresh(row)
    assert secret not in row.secret_encrypted, "the secret is stored encrypted"
    assert not set(codes) & set(row.backup_codes_hashed), "kept as fingerprints"

    first = await _login(client, manager)
    body = first.json()
    assert body["two_factor_required"] is True
    assert body["access_token"] is None and body["role"] is None
    # 🔴 The intermediate token opens nothing else.
    pending = _bearer(body["two_factor_token"])
    assert (await client.get("/api/v1/auth/me", headers=pending)).status_code == 401
    assert (
        await client.get("/api/v1/auth/two-factor", headers=pending)
    ).status_code == 401
    assert (await client.get("/api/v1/projects", headers=pending)).status_code == 401

    second = await client.post(
        "/api/v1/auth/login/two-factor",
        json={"two_factor_token": body["two_factor_token"], "code": _code(secret)},
    )
    assert second.status_code == 200, second.text
    assert second.json()["role"] == "manager"
    session = _bearer(second.json()["access_token"])
    assert (await client.get("/api/v1/auth/me", headers=session)).status_code == 200
    status = (await client.get("/api/v1/auth/two-factor", headers=session)).json()
    assert status["enabled"] is True and status["backup_codes_remaining"] == 10
    assert await _actions(db, manager) == ["two_factor.enabled"]
    # Set up twice: refused, the factor stays as it is.
    again = await client.post("/api/v1/auth/two-factor/setup", headers=session)
    assert again.status_code == 409


async def test_a_wrong_or_replayed_code_is_refused_and_journaled(client, db):
    manager = await _account(db)
    secret, session, _ = await _enrol(client, manager)
    good = _code(secret)
    wrong = "000000" if good != "000000" else "111111"
    refused = await _second_step(client, manager, code=wrong)
    assert refused.status_code == 401
    assert refused.json()["detail"] == "Code incorrect ou déjà utilisé."
    assert (await _second_step(client, manager, code=good)).status_code == 200
    again = await _second_step(client, manager, code=good)
    assert again.status_code == 401, "a code works once"
    older = await _second_step(client, manager, code=_code(secret, -1))
    assert older.status_code == 401, "an older one"
    # The next step's code works: the window is one period on each side.
    later = await _second_step(client, manager, code=_code(secret, 1))
    assert later.status_code == 200
    assert (await _actions(db, manager)).count("two_factor.failed") == 3
    # An intermediate token that is not one is « expired », never a 500.
    forged = await client.post(
        "/api/v1/auth/login/two-factor",
        json={"two_factor_token": "x", "code": good},
    )
    assert forged.status_code == 401
    assert "reconnectez-vous" in forged.json()["detail"]
    # A session token, or a password link, is no intermediate token either.
    for other in (session, password_link_service.issue(manager, "reset")):
        refused = await client.post(
            "/api/v1/auth/login/two-factor",
            json={"two_factor_token": other, "code": _code(secret, 1)},
        )
        assert refused.status_code == 401
        assert "reconnectez-vous" in refused.json()["detail"]


async def test_a_backup_code_signs_in_once(client, db):
    manager = await _account(db)
    _, _, codes = await _enrol(client, manager)
    used = await _second_step(client, manager, backup_code=codes[0].upper())
    assert used.status_code == 200, used.text
    twice = await _second_step(client, manager, backup_code=codes[0])
    assert twice.status_code == 401
    row = await db.scalar(
        select(UserTwoFactor).where(UserTwoFactor.user_id == manager.id)
    )
    await db.refresh(row)
    assert len(row.backup_codes_hashed) == 9
    assert "two_factor.backup_code_used" in await _actions(db, manager)


async def test_removing_it_asks_the_password_and_a_code(client, db):
    manager = await _account(db)
    secret, token, _ = await _enrol(client, manager)
    url = "/api/v1/auth/two-factor/disable"
    auth = _bearer(token)
    bad_password = await client.post(
        url, headers=auth, json={"password": "faux", "code": _code(secret)}
    )
    assert bad_password.status_code == 400
    no_code = await client.post(
        url, headers=auth, json={"password": PASSWORD, "code": "000000"}
    )
    assert no_code.status_code == 400
    done = await client.post(
        url, headers=auth, json={"password": PASSWORD, "code": _code(secret)}
    )
    assert done.status_code == 204, done.text
    assert (await _login(client, manager)).json()["access_token"]
    assert (await _actions(db, manager))[-1] == "two_factor.disabled"


async def test_new_backup_codes_replace_the_old_ones(client, db):
    manager = await _account(db)
    secret, token, old = await _enrol(client, manager)
    auth = _bearer(token)
    url = "/api/v1/auth/two-factor/backup-codes"
    refused = await client.post(
        url, headers=auth, json={"password": "faux", "code": _code(secret)}
    )
    assert refused.status_code == 400
    fresh = await client.post(
        url, headers=auth, json={"password": PASSWORD, "backup_code": old[1]}
    )
    assert fresh.status_code == 200, fresh.text
    new = fresh.json()["backup_codes"]
    assert len(new) == 10 and not set(new) & set(old)
    stale = await _second_step(client, manager, backup_code=old[2])
    assert stale.status_code == 401, "the old codes stop working"
    assert (await _second_step(client, manager, backup_code=new[0])).status_code == 200
    assert "two_factor.backup_codes_regenerated" in await _actions(db, manager)


async def test_a_password_link_sets_the_password_then_asks_the_code(client, db):
    manager = await _account(db)
    secret, _, _ = await _enrol(client, manager)
    link = password_link_service.issue(manager, "reset")
    answer = await client.post(
        f"/api/v1/auth/password-link/{link}",
        json={"new_password": "un-autre-mot-de-passe"},
    )
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["access_token"] is None and body["two_factor_required"] is True
    second = await client.post(
        "/api/v1/auth/login/two-factor",
        json={"two_factor_token": body["two_factor_token"], "code": _code(secret)},
    )
    assert second.status_code == 200 and second.json()["access_token"]


async def test_the_door_opens_to_a_session_token_only(client, db):
    """🔴 A password link presented as a bearer opened the account until 3 Nov 2026: it is
    signed with the same key and carries the account's id (measured: `/auth/me` answered
    200, and the fund's projects were listed)."""
    manager = await _account(db)
    session = _bearer((await _login(client, manager)).json()["access_token"])
    for purpose in ("reset", "welcome"):
        link = password_link_service.issue(manager, purpose)
        assert (
            await client.get("/api/v1/auth/me", headers=_bearer(link))
        ).status_code == 401
        assert (
            await client.get("/api/v1/projects", headers=_bearer(link))
        ).status_code == 401
    # The intermediate token, even forged for an account with no factor on.
    pending = create_two_factor_pending_token(str(manager.id))
    assert (
        await client.get("/api/v1/auth/me", headers=_bearer(pending))
    ).status_code == 401
    # A token issued before the field existed (no `type`) lives out its own expiry.
    legacy = jwt.encode(
        {
            "sub": str(manager.id),
            "role": manager.role,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "sid": uuid.uuid4().hex,
        },
        get_settings().SECRET_KEY,
        algorithm="HS256",
    )
    assert (
        await client.get("/api/v1/auth/me", headers=_bearer(legacy))
    ).status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=session)).status_code == 200


async def test_the_console_s_sign_in_link_is_a_session_of_its_own(client, db):
    """Covered, not protected: the console's administrator asked for it after passing
    Alice's mandatory second factor, behind the internal key, on the Docker network only.
    The token it hands is a session (`type = access`), which the door reads."""
    manager = await _account(db)
    await _enrol(client, manager)
    answer = await client.post(
        f"/internal/managers/{manager.id}/login-link",
        headers={"X-Internal-Key": KEY},
    )
    assert answer.status_code == 200, answer.text
    token = answer.json()["token"]
    assert jwt.get_unverified_claims(token)["type"] == "access"
    assert (
        await client.get("/api/v1/auth/me", headers=_bearer(token))
    ).status_code == 200
    # Without the key, nobody gets one.
    refused = await client.post(f"/internal/managers/{manager.id}/login-link")
    assert refused.status_code == 401


def test_no_route_removes_somebody_else_s_factor():
    """🔴 No screen of the product administers another account (the console holds them
    all): the way out of a lost phone is `scripts/reset_two_factor.py` on the server, never
    a route (it would be the one door a stolen password needs)."""
    paths = {getattr(route, "path", "") for route in app.routes}
    assert not [p for p in paths if "two-factor" in p and "reset" in p]
    assert not [p for p in paths if p.startswith("/internal") and "two-factor" in p]


async def test_the_server_s_command_resets_it_and_tells_the_person(
    client, db, outbox, monkeypatch
):
    from scripts import reset_two_factor

    manager = await _account(db)
    await _enrol(client, manager)

    @contextlib.asynccontextmanager
    async def _session():
        yield db

    monkeypatch.setattr(reset_two_factor, "AsyncSessionLocal", _session)
    outbox.clear()
    assert await reset_two_factor.reset(manager.email.upper(), assume_yes=True) == 0
    assert (
        await db.scalar(
            select(UserTwoFactor).where(UserTwoFactor.user_id == manager.id)
        )
    ) is None
    line = await db.scalar(
        select(AuditLog).where(
            AuditLog.entity_id == str(manager.id),
            AuditLog.action == "two_factor.reset",
        )
    )
    assert line.details["by"].startswith("script:")
    assert line.user_email.startswith("script:"), "journaled under the command's name"
    assert [m["to"] for m in outbox] == [manager.email]
    assert "retirée" in outbox[0]["subject"]
    assert "Le Comptoir Invest" in outbox[0]["body"]
    # Nothing left to remove; and the password signs in again on its own.
    assert await reset_two_factor.reset(manager.email, assume_yes=True) == 0
    assert len(outbox) == 1
    assert (await _login(client, manager)).json()["access_token"]
    assert await reset_two_factor.reset("personne@example.org", assume_yes=True) == 1


async def test_the_second_step_is_rate_limited(client):
    statuses = []
    for _ in range(two_factor_routes.SECOND_STEP_PER_MINUTE + 1):
        answer = await client.post(
            "/api/v1/auth/login/two-factor",
            json={"two_factor_token": "expired", "code": "123456"},
        )
        statuses.append(answer.status_code)
    assert statuses[:-1] == [401] * two_factor_routes.SECOND_STEP_PER_MINUTE
    assert statuses[-1] == 429
    assert "Trop de tentatives" in answer.json()["detail"]
