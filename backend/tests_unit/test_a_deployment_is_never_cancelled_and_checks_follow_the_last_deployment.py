"""A started deployment is never cancelled, and an outdated run never deploys.

The owner, 28 Nov 2026 ("oui pour les 11"): the remedy of Immo 7b30d3c5. On 27 Nov a
newer push cancelled Immo's run 46049637071 in the middle of its `deploy` job, and Immo
answered 502. This deploy.yml had the same workflow-level group with cancel-in-progress,
which cancels every job of the run. The deployment now has a group of its own that never
cancels a started job, and a step that keeps an outdated run from deploying after a newer
one. There is no paths filter here: the checks run on every push, and a filter added one
day must compare with the last deployment, not with the previous push (Immo, 27 Nov:
server code went online that pytest had never run on).

Read from the workflow file: no test run can see what GitHub starts after it.
"""

from __future__ import annotations

import re
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deploy.yml"
#: The jobs that only check: a newer push may cancel them.
CHECK_JOBS = ("tests", "build-push")
DEPLOY_STEP = "Pull & up sur le VPS"


def _text() -> str:
    return DEPLOY.read_text(encoding="utf-8")


def _jobs() -> dict[str, str]:
    body = _text().split("\njobs:\n", 1)[1]
    jobs = {}
    for block in re.split(r"^  (?=[A-Za-z0-9_-]+:\s*$)", body, flags=re.MULTILINE):
        head, _, rest = block.partition("\n")
        match = re.fullmatch(r"([A-Za-z0-9_-]+):\s*", head)
        if match:
            jobs[match.group(1)] = rest
    return jobs


def _concurrency(block: str) -> dict[str, str]:
    match = re.search(
        r"^    concurrency:\n((?:      .*\n)+)", block, flags=re.MULTILINE
    )
    assert match, "no job-level `concurrency`"
    return dict(
        re.findall(r"^      ([a-z-]+):\s*(.+?)\s*$", match.group(1), flags=re.MULTILINE)
    )


def test_no_workflow_level_group_can_cancel_the_deployment():
    head = _text().split("\njobs:\n", 1)[0]
    assert not re.search(r"^concurrency:", head, flags=re.MULTILINE), (
        "a workflow-level group cancels every job of an outdated run, the deployment "
        "included (Immo's run 46049637071, 27 Nov 2026: Immo answered 502)"
    )


def test_a_started_deployment_is_never_cancelled_and_deployments_share_one_group():
    group = _concurrency(_jobs()["deploy"])
    assert group.get("cancel-in-progress") == "false"
    assert "github." not in group["group"], "one group for production, whatever the run"


def test_an_outdated_run_never_deploys_after_a_newer_one():
    deploy = _jobs()["deploy"]
    steps = deploy.split("\n    steps:\n", 1)[1]
    first, *others = re.split(r"^      - ", steps, flags=re.MULTILINE)[1:]
    assert "id: order" in first, "the order guard must be the first step of `deploy`"
    assert '"$last" -gt "$GITHUB_RUN_ID"' in first
    assert f'select(.name == "{DEPLOY_STEP}")' in first
    for step in others:
        assert "steps.order.outputs.go == 'true'" in step, (
            f"a step of `deploy` runs whatever the order guard said: {step.splitlines()[0]}"
        )
    assert re.search(
        r"^    permissions:\n(?:      .*\n)*      actions: read", deploy, re.M
    )


def test_the_checks_stay_cancellable_by_a_newer_push():
    jobs = _jobs()
    for job in CHECK_JOBS:
        group = _concurrency(jobs[job])
        assert group.get("cancel-in-progress") == "true", (
            f"`{job}` would run for nothing"
        )
        assert "${{ github.ref }}" in group["group"], (
            f"`{job}`: a manual run on another branch would cancel main's"
        )
    groups = [_concurrency(jobs[job])["group"] for job in (*CHECK_JOBS, "deploy")]
    assert len(set(groups)) == len(groups), (
        "two jobs of one run would cancel each other"
    )


def test_a_check_cancelled_by_a_newer_push_builds_nothing():
    jobs = _jobs()
    assert 'echo "go=false"' in jobs["checks"] and 'echo "go=true"' in jobs["checks"]
    assert "needs.checks.outputs.go == 'true'" in jobs["build-push"], (
        "an outdated commit whose check was cancelled would be built and deployed"
    )


def test_every_push_is_checked_whole_or_against_the_last_deployment():
    if "paths-filter" not in _text():
        for job in CHECK_JOBS[:-1]:
            assert not re.search(r"^    if:", _jobs()[job], re.M), (
                f"`{job}` can be skipped: a skipped check needs a base, the last deployment"
            )
        return
    changes = _jobs()["changes"]
    assert "base: ${{ steps.base.outputs.sha }}" in changes, (
        "paths-filter would compare with the previous push"
    )
    assert f'select(.name == "{DEPLOY_STEP}")' in changes


def test_the_step_read_as_the_deployment_still_exists():
    deploy = _jobs()["deploy"]
    assert re.search(rf"^      - name: {re.escape(DEPLOY_STEP)}\s*$", deploy, re.M), (
        "the API marks the last deployment by this step: renamed, the order guard is blind"
    )
