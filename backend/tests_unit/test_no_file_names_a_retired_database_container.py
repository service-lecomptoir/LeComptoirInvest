"""No file names a database container that no longer exists.

The owner, 14 Nov 2026: the twelve bases live on one PostgreSQL 16, in the container
`bases_postgres` of the database server (service address 10.66.0.10, through the WireGuard
tunnel), and the old containers of the application server were retired. On 17 Nov 2026 the
key-rotation script of this repository still took its safety backup with a `docker exec` into
the old container of this product's base: run by the owner, it would have stopped on « pg_dump
a echoue » before rotating anything, and the measurement scripts of the sister products read
the same dead names. A script handed to the owner that aims at a container that is gone fails
the day it is needed.

A base is reached today the way the nightly backup and the measurements do it: on the database
server, `ssh lecomptoir-db "docker exec -i bases_postgres psql -U lecomptoir_admin -d <base>"`,
or through the tunnel with a throw-away `postgres:16-alpine` client.

The names are built from the products, never written whole here: this file is read too.
"""

from __future__ import annotations

import os
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]

PRODUCTS = (
    "immo", "alice", "sejour", "market", "portail360", "si", "rh", "invest", "pdf", "compta",
    "syndic", "btp",
)  # fmt: skip
#: The retired containers (`<product>_db`, the two names Immo's base carried) and the volumes
#: of the old bases (`<anything>_pgdata`).
RETIRED = re.compile(
    r"\b(?:(?:" + "|".join(PRODUCTS) + r")_" + "db"
    r"|(?:immo|locataire)_" + "postgres"
    r"|[a-z0-9]+_" + "pgdata"
    r")\b"
)

SKIPPED_DIRS = {
    ".git", "node_modules", "dist", "build", "coverage", "__pycache__", ".venv", "venv",
    ".pytest_cache", ".ruff_cache", ".mypy_cache",
}  # fmt: skip
SCANNED_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".yml", ".yaml", ".conf", ".html",
    ".txt", ".example", ".toml", ".ini", ".cfg", ".sh", ".ps1", ".sql", ".css",
}  # fmt: skip


def _scanned_files():
    # os.walk prunes the skipped directories: rglob would descend into node_modules first.
    for folder, subfolders, names in os.walk(ROOT):
        subfolders[:] = sorted(d for d in subfolders if d not in SKIPPED_DIRS)
        for name in sorted(names):
            path = pathlib.Path(folder) / name
            # A real .env holds production values and is not tracked; only the example counts.
            if name.startswith(".env") and name != ".env.example":
                continue
            if path.suffix in SCANNED_SUFFIXES or name == ".env.example":
                yield path


def _retired_lines(text: str):
    for number, line in enumerate(text.splitlines(), 1):
        if RETIRED.search(line):
            yield number, line.strip()


def test_no_file_names_a_retired_database_container():
    if not (ROOT / "backend").is_dir():  # a container image holds the backend alone
        return
    scanned = 0
    offenders = []
    for path in _scanned_files():
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="ignore")
        for number, line in _retired_lines(text):
            offenders.append(
                f"{path.relative_to(ROOT).as_posix()}:{number}  {line[:140]}"
            )
    assert scanned > 50, f"the guard read {scanned} file(s): it sees nothing"
    assert offenders == [], (
        "A file names a database container retired on 14 Nov 2026. The base lives in "
        "bases_postgres on the database server (ssh lecomptoir-db, or 10.66.0.10 through the "
        "tunnel):\n  " + "\n  ".join(offenders)
    )


def test_the_guard_tells_a_retired_container_from_what_is_alive():
    assert list(_retired_lines("docker exec " + "invest" + "_db pg_dump")) != []
    assert list(_retired_lines("DB=" + "rh" + "_db ;;")) != []
    assert list(_retired_lines("PROD_CONTAINER = 'immo" + "_postgres'")) != []
    assert list(_retired_lines("volumes: [sejour" + "_pgdata]")) != []
    # Alive, or not a container at all.
    assert (
        list(_retired_lines("docker exec -i bases_postgres psql -U lecomptoir_admin"))
        == []
    )
    assert list(_retired_lines("from app.database import get_db")) == []
    assert list(_retired_lines("Depends(get_db, scope='function')")) == []
    assert list(_retired_lines("invest_backend, rh_api, lecomptoirinvest")) == []


def test_the_key_rotation_backs_the_base_up_on_the_database_server():
    script = (ROOT / "docs" / "rotation_cle_donnees.ps1").read_text(encoding="utf-8")
    assert "bases_postgres" in script and "lecomptoir-db" in script, (
        "the key rotation no longer takes its backup in bases_postgres on the database server"
    )
    assert re.search(r"invest\s*=\s*\"lecomptoirinvest\"", script), (
        "the key rotation no longer names this product's base (lecomptoirinvest)"
    )
