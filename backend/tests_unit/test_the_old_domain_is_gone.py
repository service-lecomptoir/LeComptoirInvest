"""The old platform domain is gone from the code and the docs.

On 3 October 2026 the platform moved from `lecomptoir.services` to
`lecomptoir-services.com`. The edge keeps serving the old name with a temporary
redirect, so a link still written with it works today and would break the day the old
domain is cancelled. This guard keeps a new one from being written.

The test is a LITERAL substring test, not a pattern: `.` is a wildcard in a regex, and
`lecomptoir.services` would then match `lecomptoir-services` too.

Allow-list, each entry with its reason:

* `@lecomptoir.services` (mailboxes such as contact@, noreply@): the mailboxes stay on
  the old name until they become settings held by Alice; the move concerns hosts, not
  addresses.
* this file: it has to name the old host to look for it.

Moving a host to the new name is the fix; a new allow-list entry needs a reason here.
"""

from __future__ import annotations

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
OLD_HOST = "lecomptoir" + ".services"

#: Mailbox addresses keep the old name for now (see the module docstring).
ALLOWED_PREFIXES = ("@" + OLD_HOST,)

#: Files that may name the old host as a whole, with the reason.
ALLOWED_FILES = {
    pathlib.Path(__file__).resolve(): "the guard itself names the host it looks for",
}

SKIPPED_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
}
SCANNED_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".yml",
    ".yaml",
    ".conf",
    ".html",
    ".svg",
    ".txt",
    ".example",
    ".toml",
    ".ini",
    ".cfg",
    ".sh",
    ".ps1",
    ".css",
}


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


def _old_host_lines(text: str):
    for number, line in enumerate(text.splitlines(), 1):
        for prefix in ALLOWED_PREFIXES:
            line = line.replace(prefix, "")
        if OLD_HOST in line:
            yield number, line.strip()


def test_no_new_use_of_the_old_domain():
    if not (ROOT / "backend").is_dir():  # a container image holds the backend alone
        return
    offenders = []
    for path in _scanned_files():
        if path in ALLOWED_FILES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for number, line in _old_host_lines(text):
            offenders.append(
                f"{path.relative_to(ROOT).as_posix()}:{number}  {line[:140]}"
            )
    assert offenders == [], (
        "The old domain is written again. Use the product host under "
        "lecomptoir-services.com (or add an allow-list entry here, with its reason).\n  "
        + "\n  ".join(offenders)
    )


def test_the_guard_tells_the_old_host_from_the_new_one():
    # The new host must never trip the literal test, and a mailbox must not either.
    assert list(_old_host_lines("https://immo.lecomptoir-services.com/login")) == []
    assert list(_old_host_lines("write to contact@" + OLD_HOST)) == []
    assert list(_old_host_lines("https://immo." + OLD_HOST)) != []
