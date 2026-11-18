"""A secret is compared through `security.same_secret`, never by `compare_digest` on `str`.

🔴 LOOP OF 17 NOV 2026, MEASURED: `hmac.compare_digest` RAISES `TypeError` on two strings
as soon as one holds a character outside ASCII. An internal key `X-Internal-Key: é` or a
link signed `sig=é` answered an error 500 instead of a refusal, in nine products at once:
the fix had been written at one place and the comparison copied to the others.

This guard reads every call of `compare_digest` under `app/`. It accepts:
  * the one inside `security.same_secret`, which compares bytes;
  * a call whose two operands are both `.encode(...)`, i.e. bytes;
  * the shared core `two_factor.py`, identical in every product and pinned by its own
    fingerprint: it lets only ASCII digits reach its comparison.
"""

from __future__ import annotations

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
SHARED_CORES = {"core/two_factor.py"}


def _is_bytes(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "encode"
    )


def _calls():
    """(file, innermost function, call) for every call of `compare_digest`."""
    found = []

    def visit(node: ast.AST, rel: str, function: str) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function = node.name
        if isinstance(node, ast.Call):
            called = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if called == "compare_digest":
                found.append((rel, function, node))
        for child in ast.iter_child_nodes(node):
            visit(child, rel, function)

    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(APP).as_posix()
        visit(ast.parse(path.read_text(encoding="utf-8")), rel, "")
    return found


def test_no_secret_is_compared_as_a_string():
    loose = set()
    for rel, function, node in _calls():
        if rel in SHARED_CORES:
            continue
        if rel == "core/security.py" and function == "same_secret":
            continue
        if len(node.args) == 2 and all(_is_bytes(a) for a in node.args):
            continue
        loose.add(f"app/{rel}:{node.lineno}")
    assert not loose, (
        "compare_digest on values that may be str: use app.core.security.same_secret "
        f"(it compares bytes, a non-ASCII value is a refusal, not a 500): {sorted(loose)}"
    )


def test_the_guard_still_sees_the_helper():
    assert any(
        rel == "core/security.py" and function == "same_secret"
        for rel, function, _ in _calls()
    ), "the guard no longer reads security.same_secret"
