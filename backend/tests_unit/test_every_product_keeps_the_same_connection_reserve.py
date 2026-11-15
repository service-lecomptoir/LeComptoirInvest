"""Every product keeps the same connection reserve, and checks a connection before use.

The owner, 14 Nov 2026 (« un besoin, un code »): the twelve products share one PostgreSQL on
the database server, which accepts 600 connections. The reserves differed (10 + 20 here,
5 + 10 there, the library's defaults elsewhere) and only their sum said whether the server
would hold. 5 kept open and 10 more at a peak per worker process, read from the
environment, is 315 for the twelve at their worst. And the base is reached through a
WireGuard tunnel: a connection is checked before use (`pool_pre_ping`), or a cut of the
tunnel leaves dead connections in the pool for the next requests to stumble on.
"""

from __future__ import annotations

from app.config import Settings, get_settings


def _pool():
    from app.database import engine

    return getattr(engine, "sync_engine", engine).pool


def test_the_reserve_is_five_kept_and_ten_at_a_peak():
    assert Settings.model_fields["DB_POOL_SIZE"].default == 5
    assert Settings.model_fields["DB_MAX_OVERFLOW"].default == 10


def test_the_engine_keeps_the_reserve_of_the_settings():
    pool = _pool()
    assert pool.size() == get_settings().DB_POOL_SIZE
    assert pool._max_overflow == get_settings().DB_MAX_OVERFLOW


def test_every_connection_is_checked_before_use():
    assert _pool()._pre_ping is True
