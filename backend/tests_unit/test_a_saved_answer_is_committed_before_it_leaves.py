"""A write is committed before its answer leaves, so the next read sees it.

FastAPI runs the code after the `yield` of a dependency whose scope is « request » (the
default) once the response is SENT. `get_db` commits there: in the customer recipe of
30 Sept 2026, 13 reads out of 15 made right after creating a fund did not see it, and a
commit failing after the 201 would have been a success the database never kept. Every route
therefore takes its session through the one alias `app.database.SESSION`, declared with
`scope="function"`; this guard reads the source for any other way in.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.database import SESSION, get_db

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _session_dependencies(tree: ast.AST):
    """Every `Depends(get_db ...)` written in a tree."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Depends"
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "get_db"
        ):
            yield node


def _uses_of_the_alias(tree: ast.AST) -> int:
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "SESSION"
    )


def test_the_alias_commits_in_the_function_scope():
    assert SESSION.dependency is get_db
    assert SESSION.scope == "function"


def test_no_route_takes_its_session_any_other_way():
    uses, elsewhere = 0, []
    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        uses += _uses_of_the_alias(tree)
        for call in _session_dependencies(tree):
            if path.name != "database.py":
                elsewhere.append(f"{path.relative_to(APP_DIR)}:{call.lineno}")
    # The guard must see what it guards: the routes do take a session.
    assert uses > 50
    assert elsewhere == [], f"Depends(get_db) outside the SESSION alias: {elsewhere}"


def test_the_guard_sees_a_session_declared_by_hand():
    tree = ast.parse("async def route(db=Depends(get_db)): ...")
    assert len(list(_session_dependencies(tree))) == 1


def _order(dependency) -> list[str]:
    """What happened first on a toy app: the teardown (« committed ») or the answer."""
    journal: list[str] = []

    async def session():
        yield "db"
        journal.append("committed")

    app = FastAPI()

    @app.post("/save")
    async def save(db=dependency(session)):
        return {}

    async def recording(scope, receive, send):
        async def spy(message):
            if message["type"] == "http.response.body" and not message.get("more_body"):
                journal.append("answered")
            await send(message)

        await app(scope, receive, spy)

    with TestClient(recording) as client:
        assert client.post("/save").status_code == 200
    return journal


@pytest.mark.parametrize(
    ("dependency", "expected"),
    [
        (lambda gen: Depends(gen, scope="function"), ["committed", "answered"]),
        # The default, kept here so the day FastAPI changes it this test says so.
        (lambda gen: Depends(gen), ["answered", "committed"]),
    ],
)
def test_only_the_function_scope_commits_before_the_answer(dependency, expected):
    assert _order(dependency) == expected


def test_a_commit_that_fails_is_never_answered_as_a_success():
    """The alias itself, with a session whose commit fails: the answer is a 500, not 201."""

    class RefusingSession:
        async def commit(self):
            raise RuntimeError("the database refused the commit")

    async def refusing():
        yield RefusingSession()
        await RefusingSession().commit()

    app = FastAPI()

    @app.post("/save", status_code=201)
    async def save(db=SESSION):
        return {}

    app.dependency_overrides[get_db] = refusing
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.post("/save").status_code == 500
