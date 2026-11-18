"""Nothing goes online unless the checks are green, and only from main.

The owner, 18 Nov 2026, on the model of Alice, Sejour, Immo and Portail360.
deploy.yml waited for its single check job (ruff, pytest, i18n, tsc, ESLint, vitest),
but nothing tied build-push and deploy to main: a manual run (workflow_dispatch) on
another branch put that branch online once its tests were green. The jobs that build and
deploy now go through a gate that fails when a check failed or was cancelled, and only
from main; the concurrency group is per branch.

Read from the workflow files: no test run can see what GitHub starts after it.
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
DEPLOY = "deploy.yml"
#: The check workflows deploy.yml calls, and what each one must still run.
CHECKS: dict[str, tuple[str, ...]] = {}
#: The checks that live in deploy.yml itself, and what each one must still run.
INLINE_CHECKS: dict[str, tuple[str, ...]] = {
    "tests": (
        "python -m ruff check",
        "python -m pytest",
        "npx tsc --noEmit",
        "npx vitest run",
    )
}
DEPLOYING_JOBS = ("build-push", "deploy")
GATE = "checks"


def _text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _triggers(name: str) -> str:
    """The `on:` section of a workflow."""
    match = re.search(r"^on:\n(.*?)^\S", _text(name), flags=re.MULTILINE | re.DOTALL)
    assert match, f"{name}: no `on:` section"
    return match.group(1)


def _jobs(name: str) -> dict[str, str]:
    """Each job of a workflow, by name, with the text of its block."""
    body = _text(name).split("\njobs:\n", 1)[1]
    jobs = {}
    for block in re.split(r"^  (?=[A-Za-z0-9_-]+:\s*$)", body, flags=re.MULTILINE):
        head, _, rest = block.partition("\n")
        match = re.fullmatch(r"([A-Za-z0-9_-]+):\s*", head)
        if match:
            jobs[match.group(1)] = rest
    return jobs


def _needs(block: str) -> list[str]:
    match = re.search(r"^    needs:\s*(.+)$", block, flags=re.MULTILINE)
    if not match:
        return []
    return [
        name.strip() for name in match.group(1).strip("[] ").split(",") if name.strip()
    ]


def _condition(block: str) -> str:
    """The `if:` of a job, a folded `>-` block joined on one line."""
    lines = block.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^    if:\s*(.*)$", line)
        if match:
            value = match.group(1).strip()
            if value in (">-", ">", "|-", "|"):
                folded = []
                for following in lines[index + 1 :]:
                    if not following.startswith("      "):
                        break
                    folded.append(following.strip())
                value = " ".join(folded)
            return value
    return ""


def _upstream(jobs: dict[str, str], name: str) -> set[str]:
    seen: set[str] = set()
    todo = list(_needs(jobs[name]))
    while todo:
        job = todo.pop()
        if job not in seen:
            seen.add(job)
            todo.extend(_needs(jobs[job]))
    return seen


def _caller_of(jobs: dict[str, str], workflow: str) -> str:
    callers = [
        name
        for name, block in jobs.items()
        if re.search(
            rf"^    uses:\s*\./\.github/workflows/{re.escape(workflow)}\s*$",
            block,
            re.M,
        )
    ]
    assert callers, (
        f"{DEPLOY} does not call {workflow}: the deployment does not wait for it"
    )
    return callers[0]


def _all_checks(jobs: dict[str, str]) -> list[str]:
    return [_caller_of(jobs, workflow) for workflow in CHECKS] + list(INLINE_CHECKS)


def test_no_other_workflow_runs_checks_on_the_side():
    # A check that starts on its own push, next to the deployment, blocks nothing: its
    # red reads like a verdict while the image is already online.
    others = {path.name for path in WORKFLOWS.glob("*.y*ml")} - {DEPLOY}
    assert others == set(CHECKS), (
        f"workflows outside {DEPLOY} that it does not call: {sorted(others - set(CHECKS))}"
    )


def test_every_check_is_a_workflow_the_deployment_can_call_and_that_runs_once():
    for workflow, commands in CHECKS.items():
        triggers = _triggers(workflow)
        assert "workflow_call:" in triggers, f"{workflow} cannot be called by {DEPLOY}"
        for own_trigger in ("push:", "pull_request:"):
            assert own_trigger not in triggers, (
                f"{workflow} also starts on its own {own_trigger} the checks would run twice, "
                "and the run nobody waits for would look like the one that gates"
            )
        text = _text(workflow)
        for command in commands:
            assert command in text, f"{workflow} no longer runs {command}"


def test_the_checks_inside_the_deployment_still_run_what_they_are_named_for():
    jobs = _jobs(DEPLOY)
    for job, commands in INLINE_CHECKS.items():
        for command in commands:
            assert command in jobs[job], f"`{job}` no longer runs {command}"


def test_building_and_deploying_need_every_check_directly_or_not():
    jobs = _jobs(DEPLOY)
    checks = _all_checks(jobs)
    assert checks, "no check at all before the build"
    for check in checks:
        for job in DEPLOYING_JOBS:
            assert check in _upstream(jobs, job), f"`{job}` does not wait for `{check}`"
            assert GATE in _upstream(jobs, job), f"`{job}` does not wait for the gate"


def test_the_gate_blocks_on_a_failed_or_cancelled_check():
    jobs = _jobs(DEPLOY)
    gate = jobs[GATE]
    for check in _all_checks(jobs):
        assert check in _needs(gate), f"the gate does not read `{check}`"
    # It must run when a check failed, to say so; a gate skipped on a failure is green
    # nowhere and red nowhere.
    assert _condition(gate).replace(" ", "") == "${{!cancelled()}}"
    assert "contains(needs.*.result, 'failure')" in gate
    assert "contains(needs.*.result, 'cancelled')" in gate
    assert "exit 1" in gate


def test_building_and_deploying_run_only_on_a_green_gate_and_only_from_main():
    jobs = _jobs(DEPLOY)
    for job in DEPLOYING_JOBS:
        condition = _condition(jobs[job])
        assert condition, (
            f"`{job}` has no condition: a manual run on any branch goes online"
        )
        assert "always()" not in condition, f"`{job}` would run on a cancelled run"
        # The implicit success() reads every job upstream: a check skipped on purpose
        # would skip the build and the deployment. Each deploying job reads the result of
        # what it needs instead, past `!cancelled()`.
        assert "!cancelled()" in condition, f"`{job}` is skipped whenever a check is"
        for need in _needs(jobs[job]):
            assert f"needs.{need}.result == 'success'" in condition, (
                f"`{job}` would run whatever `{need}` said"
            )
        assert "github.ref == 'refs/heads/main'" in condition, (
            f"`{job}` could put another branch online (a manual run on any branch)"
        )


def test_a_run_on_another_branch_never_cancels_a_deployment_of_main():
    match = re.search(
        r"^concurrency:\n(?:\s*#.*\n)*  group:\s*(.+)$",
        _text(DEPLOY),
        flags=re.MULTILINE,
    )
    assert match, f"{DEPLOY} has no concurrency group"
    assert "${{ github.ref }}" in match.group(1), "one group for every branch"
