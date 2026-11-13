"""Every container of the deployment composes limits the size of its logs.

The owner, 13 Nov 2026: Docker's json-file log of a container is rotated at 20 MB with five
files kept (100 MB at most), service by service in the compose, through one `x-logging`
anchor per file, never in daemon.json (changing it restarts Docker and every container). The
age of the logs is bounded by Portail360's daily purge, which reads the rotations too. A
service added without the limit would write its log until the disk is full.

Read from the compose files: a functional test cannot see what a container is started with.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSES = [
    path
    for name in (
        "docker-compose.deploy.yml",
        "docker-compose.prod.yml",
        "docker-compose.portail360.yml",
    )
    for path in (ROOT / "docker" / name,)
    if path.exists()
]
ANCHOR = """x-logging: &default-logging
  driver: json-file
  options:
    max-size: "20m"
    max-file: "5"
"""


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_there_are_composes_to_read():
    assert COMPOSES, "the deployment composes moved: this guard reads nothing"


def test_each_compose_declares_the_limit_once():
    for path in COMPOSES:
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        assert text.count(ANCHOR) == 1, (
            f"{path.name}: the x-logging anchor (20m x 5) is missing"
        )


def test_every_service_carries_the_limit():
    for path in COMPOSES:
        lines = _lines(path)
        for i, line in enumerate(lines):
            if line.startswith("    container_name:"):
                assert lines[i + 1].strip() == "logging: *default-logging", (
                    f"{path.name}: {line.strip()} writes its log without a size limit"
                )
