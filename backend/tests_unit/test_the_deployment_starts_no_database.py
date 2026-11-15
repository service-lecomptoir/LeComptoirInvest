"""The deployment composes start no database: it lives on the database server.

The owner, 14 Nov 2026: the twelve bases live on one PostgreSQL 16, on the database server,
reached through the WireGuard tunnel at its service address 10.66.0.10, and the old
containers were retired. A database service left in a compose the CI copies to the VPS
(both files are, and checked by fingerprint) would come back EMPTY at the first `up`
without `--no-deps`, next to the real base: a product pointed at it by mistake would look
as if it had lost its data.

Read from the compose files: a functional test cannot see what a deployment starts.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSES = [
    path
    for path in (
        ROOT / "docker" / "docker-compose.deploy.yml",
        ROOT / "docker" / "docker-compose.prod.yml",
    )
    if path.exists()
]


def test_there_are_composes_to_read():
    assert COMPOSES, "the deployment composes moved: this guard reads nothing"


def test_no_service_runs_a_database_image():
    for path in COMPOSES:
        text = path.read_text(encoding="utf-8")
        images = re.findall(r"^\s+image:\s*\"?([^\s\"]+)", text, flags=re.MULTILINE)
        assert not [i for i in images if "postgres" in i], (
            f"{path.name} starts a database: it lives on the database server (10.66.0.10)"
        )


def test_no_volume_holds_database_files():
    for path in COMPOSES:
        text = path.read_text(encoding="utf-8")
        assert "/var/lib/postgresql" not in text, f"{path.name} mounts database files"
        assert not re.search(
            r"^  [a-z0-9_]*(pgdata|postgres_data):", text, flags=re.MULTILINE
        ), f"{path.name} still declares the volume of the old database"
