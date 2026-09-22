"""Prove that a change touched ONLY comments and docstrings.

Used by the comment-anglicisation passes. For every Python file changed against a
git ref, it compares the AST before and after with every docstring neutralised.
If the two trees are identical, no statement, no expression, no literal and no
identifier moved: the diff is comments and docstrings, nothing else.

    python scripts/check_comments_only.py            # vs HEAD
    python scripts/check_comments_only.py origin/main
    python scripts/check_comments_only.py --messages  # + assertion messages

`--messages` widens the neutralisation to the MESSAGE of an `assert`, and to nothing
else. A test's failure message is prose exactly like a comment -- it is read by a human
when the test goes red, never by the program -- but it lives in a string literal, so the
plain check refuses it and the anglicisation of the test suites cannot be proved at all.
With the flag, the whole `msg` is replaced by a marker before the comparison: the
assertion's CONDITION, every other literal and the entire structure are still compared.

Why an AST and not a diff review: a docstring rewrite that accidentally swallows
the closing quotes, or a comment rewrite that eats a line of code, both produce a
diff that reads fine and a program that no longer does the same thing.

WARNING (learned the hard way): `git show` must be decoded as UTF-8 EXPLICITLY.
Letting subprocess decode with the Windows default codepage turns accented French
comments into mojibake, the parse then differs for reasons that have nothing to do
with the change, and the checker reports failures that are not real.
"""

import ast
import subprocess
import sys
from pathlib import Path

# git reports paths relative to the REPOSITORY root, while this script is
# normally run from `backend/`. Resolve against the root, not the cwd.
REPO_ROOT = Path(
    subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, check=True)
    .stdout.decode("utf-8")
    .strip()
)


class _NeutraliseDocstrings(ast.NodeTransformer):
    """Replace every docstring with a fixed marker, so wording is invisible."""

    _MARKER = "<docstring>"

    def __init__(self, messages: bool = False) -> None:
        self.messages = messages

    def visit_Assert(self, node):
        self.generic_visit(node)
        if self.messages and node.msg is not None:
            node.msg = ast.Constant(value="<message>")
        return node

    def _strip(self, node):
        self.generic_visit(node)
        body = getattr(node, "body", None)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body[0].value.value = self._MARKER
        return node

    visit_Module = _strip
    visit_ClassDef = _strip
    visit_FunctionDef = _strip
    visit_AsyncFunctionDef = _strip


def _normalise(source: str, messages: bool = False) -> str:
    tree = ast.parse(source)
    tree = _NeutraliseDocstrings(messages).visit(tree)
    ast.fix_missing_locations(tree)
    # dump without positions: reindenting a docstring shifts the lines below it.
    return ast.dump(tree, include_attributes=False)


def _changed_python_files(ref: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=M", ref],
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    return [f for f in out.splitlines() if f.endswith(".py")]


def _file_at_ref(ref: str, path: str) -> str:
    out = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, check=True).stdout
    # Explicit UTF-8: see the warning in the module docstring.
    return out.decode("utf-8")


def main(ref: str = "HEAD", messages: bool = False) -> int:
    files = _changed_python_files(ref)
    if not files:
        print(f"No modified Python file against {ref}.")
        return 0

    failures = []
    for path in files:
        try:
            before = _normalise(_file_at_ref(ref, path), messages)
        except SyntaxError as exc:
            failures.append(f"{path}: the version at {ref} does not parse ({exc})")
            continue
        try:
            with open(REPO_ROOT / path, encoding="utf-8") as fh:
                after = _normalise(fh.read(), messages)
        except SyntaxError as exc:
            failures.append(f"{path}: the working copy does not parse ({exc})")
            continue
        except UnicodeDecodeError as exc:
            failures.append(f"{path}: the working copy is not valid UTF-8 ({exc})")
            continue
        if before != after:
            failures.append(f"{path}: the code changed, not only its comments")

    for line in failures:
        print(f"FAIL {line}")
    what = "comment, docstring and message" if messages else "comment-only"
    print(f"\n{len(files) - len(failures)}/{len(files)} files are {what} changes.")
    return 1 if failures else 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--messages"]
    sys.exit(main(args[0] if args else "HEAD", messages="--messages" in sys.argv))
