"""No e-mail address is written in the code of the application or in its locales.

🔴 THE OWNER'S RULE (5 Oct 2026): « Il ne doit pas avoir d'adresse email en dur ».
On 2 Nov 2026 he found the platform's address still printed on the public pages of Immo:
« Comment est-ce possible, on avait fait le nécessaire ».
The rule was kept by memory, product by product; this guard reads the source instead, in
each of the ten products. The platform's address is the one the console of Alice holds
(Communication screen, `contact_email`); a sender comes from the environment or Alice.

What it reads: the application's code and texts (`backend/app`, `frontend/src`,
`frontend/public`, `frontend/index.html`) and the `.env.example` files, tests excepted.

What it lets through, by RULE rather than by name: the domains reserved or made for
examples (`example.com`, `exemple.fr`, `ejemplo.com`, `exemplo.com.br`, `*.test`,
`*.example`, `*.invalid`, `localhost`), which a placeholder or a fictitious sample uses
and which no mailbox answers.

The exceptions below are named one by one, each with its reason. A new one must say why
the address cannot come from Alice or from the environment.
"""

from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]

ROOTS = (
    (
        REPO / "backend" / "app",
        (".py", ".json", ".j2", ".jinja", ".html", ".txt", ".md"),
    ),
    (
        REPO / "frontend" / "src",
        (".ts", ".tsx", ".js", ".jsx", ".json", ".css", ".html"),
    ),
    (REPO / "frontend" / "public", (".html", ".json", ".txt", ".webmanifest")),
)
SINGLE_FILES = (
    REPO / "frontend" / "index.html",
    REPO / ".env.example",
    REPO / "backend" / ".env.example",
)
_SKIPPED = {"__pycache__", "node_modules", ".venv", "dist", "build", ".git"}

#: An address as a mailbox would be written. The domain ends with letters, so a
#: decorator (`@router.get`), a package (`@tanstack/react-query`) or an f-string
#: (`{local}@{domain}`) is not one.
ADDRESS = re.compile(
    r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})\b"
)

#: The end of a FILE name, not of a domain (`logo@2x.png`).
_FILE_ENDINGS = {
    "png",
    "jpg",
    "jpeg",
    "svg",
    "webp",
    "gif",
    "ico",
    "js",
    "ts",
    "tsx",
    "css",
}

#: Domains made for examples: nobody receives mail there.
_EXAMPLE_DOMAIN = re.compile(
    r"^(?:[a-z0-9-]+\.)*(?:example|exemple|ejemplo|exemplo)\.[a-z.]+$"
    r"|\.(?:test|example|invalid|localhost)$|^localhost$"
)

#: (file relative to the repository, address): why it may stay.
EXCEPTIONS: dict[tuple[str, str], str] = {}


def _is_test(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return (
        ".test." in name
        or ".spec." in name
        or name.startswith("test_")
        or "/__tests__/" in rel
        or "/fixtures/" in rel
    )


def _files():
    for root, suffixes in ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix in suffixes and not any(p in _SKIPPED for p in path.parts):
                yield path
    for path in SINGLE_FILES:
        if path.exists():
            yield path


def _written_addresses() -> dict[tuple[str, str], int]:
    found: dict[tuple[str, str], int] = {}
    for path in _files():
        rel = path.relative_to(REPO).as_posix()
        if _is_test(rel):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            for match in ADDRESS.finditer(line):
                domain = match.group(1).lower()
                if domain.rsplit(".", 1)[-1] in _FILE_ENDINGS:
                    continue
                if _EXAMPLE_DOMAIN.search(domain):
                    continue
                found.setdefault((rel, match.group(0)), number)
    return found


def test_no_email_address_is_written_in_the_code():
    written = {
        key: line for key, line in _written_addresses().items() if key not in EXCEPTIONS
    }
    assert not written, (
        "E-mail addresses written in the code. The platform's address is Alice's "
        "(the console's contact_email); a sender comes from the environment or from "
        "Alice; a placeholder uses an example domain:\n"
        + "\n".join(
            f"  {rel}:{line}  {address}" for (rel, address), line in written.items()
        )
    )


def test_every_exception_still_names_an_address_that_is_there():
    """An exception whose address left its file is removed, or it would excuse the next
    one written there."""
    written = _written_addresses()
    stale = [key for key in EXCEPTIONS if key not in written]
    assert not stale, f"Exceptions that no longer match anything: {stale}"


def test_the_guard_sees_an_address_and_lets_an_example_through():
    """The rule itself, so that a broken pattern cannot pass the two tests above."""
    seen = [m.group(0) for m in ADDRESS.finditer("write to someone@outlook.com today")]
    assert seen == ["someone@outlook.com"]
    assert not list(ADDRESS.finditer("@router.get('/x')  {local}@{domain}"))
    assert _EXAMPLE_DOMAIN.search("exemple.fr")
    assert _EXAMPLE_DOMAIN.search("example.com")
    assert _EXAMPLE_DOMAIN.search("exemplo.com.br")
    assert not _EXAMPLE_DOMAIN.search("outlook.com")
    assert not _EXAMPLE_DOMAIN.search("lecomptoir-services.com")
