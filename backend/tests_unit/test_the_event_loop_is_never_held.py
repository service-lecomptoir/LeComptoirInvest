"""No `async def` of the product holds the event loop on the network, the clock or the disk
of the trust store.

🔴 WHY. Production runs two workers (`Dockerfile`, `--workers 2`), and a sign-up asks the
console, which calls this product back (`GET /internal/managers`) before it answers. A
blocking call in an `async def` stops its worker for the length of the call: a sibling
product with one worker answered « not recorded » after 15 s to sign-ups the console went on
to file (Le Comptoir RH, 29 Sept 2026). Here, every `httpx.AsyncClient()` built without
`verify` re-read the CA bundle synchronously in the loop: 3.5 s per call to the console on a
loaded machine (customer recipe, 30 Sept 2026).

⚠️ THIS GUARD READS THE SOURCE, and only the body of each `async def` itself: a plain `def`
nested inside is run elsewhere (a thread, a callback) and is not the loop's business.
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.services import alice_client

APP = Path(__file__).resolve().parents[1] / "app"

#: Calls that hold the thread until the network (or the clock) answers.
BLOCKING = {
    "urlopen",
    "urllib.request.urlopen",
    "time.sleep",
    "requests.get",
    "requests.post",
    "requests.put",
    "requests.patch",
    "requests.delete",
    "requests.request",
    "httpx.get",
    "httpx.post",
    "httpx.put",
    "httpx.patch",
    "httpx.delete",
    "httpx.request",
    "httpx.Client",
    "smtplib.SMTP",
    "smtplib.SMTP_SSL",
    "ssl.create_default_context",
}


def _name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_name(node.value)}.{node.attr}"
    return ""


def _own_calls(function: ast.AsyncFunctionDef):
    """The calls of `function`'s own body, nested plain functions and lambdas left out."""
    pending = list(function.body)
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.FunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        if isinstance(node, ast.Call):
            yield node
        pending.extend(ast.iter_child_nodes(node))


def _trees():
    for path in sorted(APP.rglob("*.py")):
        yield path, ast.parse(path.read_text(encoding="utf-8"))


def test_no_async_function_makes_a_blocking_call():
    offenders = []
    for path, tree in _trees():
        for function in ast.walk(tree):
            if not isinstance(function, ast.AsyncFunctionDef):
                continue
            for call in _own_calls(function):
                if _name(call.func) in BLOCKING:
                    where = path.relative_to(APP.parent)
                    offenders.append(
                        f"{where}:{call.lineno} {function.name} -> {_name(call.func)}"
                    )
    assert not offenders, (
        "A blocking call in an async function stalls its worker; await an asynchronous "
        "client (httpx.AsyncClient, aiosmtplib) instead:\n" + "\n".join(offenders)
    )


def test_the_guard_sees_what_it_forbids():
    """⚠️ A guard that stops seeing proves nothing: it must catch the call of the 29 Sept,
    and leave a nested plain function alone."""
    caught = ast.parse(
        "async def route():\n"
        "    with urllib.request.urlopen(request, timeout=15) as answer:\n"
        "        pass\n"
        "    def later():\n"
        "        time.sleep(1)\n"
    ).body[0]
    assert [_name(c.func) for c in _own_calls(caught) if _name(c.func) in BLOCKING] == [
        "urllib.request.urlopen"
    ]


def test_the_trust_store_is_read_once():
    assert alice_client._tls() is alice_client._tls()


def test_every_http_client_is_handed_the_shared_trust_store():
    seen, bare = 0, []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _name(node.func) == "httpx.AsyncClient":
                seen += 1
                if not any(k.arg == "verify" for k in node.keywords):
                    bare.append(f"{path.relative_to(APP.parent)}:{node.lineno}")
    # The guard must see what it guards: the calls to the console build clients.
    assert seen >= 4
    assert bare == [], f"httpx.AsyncClient without verify=_tls(): {bare}"
