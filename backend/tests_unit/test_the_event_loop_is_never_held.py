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

🔴 AND BCRYPT, AND `/health` (recipe of Le Comptoir BTP, 30 Sept 2026, d51a081). A password
hash is a quarter of a second of CPU by design, a second on a loaded machine: the sign-in,
the password change, the password link and the account Alice opens ran it in an `async
def`, and they now hand it to `run_in_threadpool`. `/health` opened a connection of its own
on every call (asyncpg authenticates it with four thousand HMACs in Python, on the loop):
polled every 100 ms, BTP stood still 30 s. It now reads a verdict shared and reused five
seconds, one probe at a time (`app/main.py`, `_database_error`).

⚠️ IT FOLLOWS THE PRODUCT'S OWN HELPERS since then: `verify_password` is a plain function
that calls bcrypt, and an `async def` calling it blocks just the same. A memoised helper
(the trust store) blocks once, at start-up, and is left out.
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
    # A password hash, by the product's one context (`core/security.py`): a quarter of a
    # second of CPU by design, a second on the recipe's machine.
    "_pwd.hash",
    "_pwd.verify",
}


def _name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_name(node.value)}.{node.attr}"
    return ""


def _own_calls(function: ast.FunctionDef | ast.AsyncFunctionDef):
    """The calls of `function`'s own body, nested functions and lambdas left out."""
    pending = list(function.body)
    while pending:
        node = pending.pop()
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
        ):
            continue
        if isinstance(node, ast.Call):
            yield node
        pending.extend(ast.iter_child_nodes(node))


def _last(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def _tree_map() -> dict[str, ast.Module]:
    return {
        path.relative_to(APP.parent).as_posix(): ast.parse(
            path.read_text(encoding="utf-8")
        )
        for path in sorted(APP.rglob("*.py"))
    }


#: A memoised helper blocks ONCE, and the product builds it at start-up (the trust store,
#: read in the warm-up thread): its callers are not held.
_MEMOISED = {"cache", "lru_cache", "functools.cache", "functools.lru_cache"}


def _memoised(function: ast.FunctionDef) -> bool:
    return any(
        _name(d.func if isinstance(d, ast.Call) else d) in _MEMOISED
        for d in function.decorator_list
    )


def _blocking_helpers(trees: dict[str, ast.Module]) -> set[str]:
    """The product's plain functions that block, directly or through another."""
    plain = [
        n
        for tree in trees.values()
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and not _memoised(n)
    ]
    blocking: set[str] = set()
    changed = True
    while changed:
        changed = False
        for function in plain:
            if function.name in blocking:
                continue
            for call in _own_calls(function):
                called = _name(call.func)
                if called in BLOCKING or _last(called) in blocking:
                    blocking.add(function.name)
                    changed = True
                    break
    return blocking


def offenders(trees: dict[str, ast.Module]) -> list[str]:
    """Every `async def` calling a blocking primitive, or a plain function of the product
    that ends up in one. An awaited call is a coroutine of the product, whatever plain
    helper shares its name elsewhere; handing a helper to `run_in_threadpool` passes it,
    it does not call it."""
    helpers = _blocking_helpers(trees)
    found = []
    for where, tree in trees.items():
        for function in ast.walk(tree):
            # The lifespan runs once, before the first request: nobody is waiting on it.
            if (
                not isinstance(function, ast.AsyncFunctionDef)
                or function.name == "lifespan"
            ):
                continue
            awaited = {
                id(n.value) for n in ast.walk(function) if isinstance(n, ast.Await)
            }
            for call in sorted(_own_calls(function), key=lambda c: c.lineno):
                called = _name(call.func)
                if called in BLOCKING or (
                    _last(called) in helpers and id(call) not in awaited
                ):
                    found.append(f"{where}:{call.lineno} {function.name} -> {called}")
    return found


#: What opens a database connection: a health route never does it on each call.
DATABASE_OPENERS = {
    "engine.connect",
    "engine.begin",
    "create_async_engine",
    "create_engine",
    "asyncpg.connect",
    "SessionLocal",
    "AsyncSessionLocal",
}

#: The paths a supervision polls.
HEALTH_PATHS = {"/health", "/healthz", "/ready", "/readyz", "/live", "/livez"}


def _health_routes(tree: ast.Module):
    for function in ast.walk(tree):
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
            isinstance(d, ast.Call)
            and d.args
            and isinstance(d.args[0], ast.Constant)
            and d.args[0].value in HEALTH_PATHS
            for d in function.decorator_list
        ):
            yield function


def health_offenders(trees: dict[str, ast.Module]) -> list[str]:
    """A health route that opens the database, directly or through a function of the
    product that does (the probe it may run goes through a verdict shared and reused a
    few seconds, one probe at a time)."""
    openers = {
        function.name
        for tree in trees.values()
        for function in ast.walk(tree)
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_name(c.func) in DATABASE_OPENERS for c in _own_calls(function))
    }
    found = []
    for where, tree in trees.items():
        for route in _health_routes(tree):
            for call in sorted(_own_calls(route), key=lambda c: c.lineno):
                called = _name(call.func)
                if called in DATABASE_OPENERS or _last(called) in openers:
                    found.append(f"{where}:{call.lineno} {route.name} -> {called}")
    return found


def _trees():
    for path in sorted(APP.rglob("*.py")):
        yield path, ast.parse(path.read_text(encoding="utf-8"))


def test_no_async_function_makes_a_blocking_call():
    found = offenders(_tree_map())
    assert not found, (
        "A blocking call in an async function stalls a worker; await an asynchronous "
        "client, or hand the call to run_in_threadpool:\n" + "\n".join(found)
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


def test_the_guard_follows_the_helpers():
    """⚠️ A password hashed through the product's helpers, and a relay spoken through
    them, are caught; the threadpool, a nested function and an awaited coroutine sharing a
    helper's name pass."""
    tree = ast.parse(
        "def hash_password(raw):\n"
        "    return _pwd.hash(raw)\n"
        "def hash_twice(raw):\n"
        "    return hash_password(raw)\n"
        "async def create_manager(data):\n"
        "    return User(hashed_password=hash_twice(data.password))\n"
        "async def create_manager_off_the_loop(data):\n"
        "    def later():\n"
        "        time.sleep(1)\n"
        "    return await run_in_threadpool(hash_password, data.password)\n"
        "async def login(data, user):\n"
        "    return verify_password(data.password, user.hashed_password)\n"
        "def verify_password(raw, hashed):\n"
        "    return _pwd.verify(raw, hashed)\n"
        "def _request(url):\n"
        "    time.sleep(1)\n"
        "async def answer(db):\n"
        "    return await _request(db, 1)\n"
    )
    assert offenders({"x.py": tree}) == [
        "x.py:6 create_manager -> hash_twice",
        "x.py:12 login -> verify_password",
    ]


def test_the_health_route_opens_no_connection():
    trees = _tree_map()
    assert any(any(_health_routes(t)) for t in trees.values()), (
        "the guard must see /health"
    )
    assert health_offenders(trees) == []


def test_the_health_guard_sees_what_it_forbids():
    """The probe of 30 Sept (a throwaway engine per call) and a connection opened in the
    route are caught; a route reading the shared verdict passes."""
    tree = ast.parse(
        "async def _probe_database():\n"
        "    engine = create_async_engine(url, poolclass=NullPool)\n"
        "@app.get('/health')\n"
        "async def health():\n"
        "    await asyncio.wait_for(_probe_database(), timeout=5)\n"
        "@router.get('/ready')\n"
        "async def ready():\n"
        "    async with engine.connect() as conn:\n"
        "        pass\n"
        "@app.get('/healthz')\n"
        "async def healthz():\n"
        "    return await _database_error()\n"
    )
    assert health_offenders({"x.py": tree}) == [
        "x.py:5 health -> _probe_database",
        "x.py:8 ready -> engine.connect",
    ]
