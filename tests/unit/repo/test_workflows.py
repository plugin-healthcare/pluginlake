"""Workflow rules: actions pinned to a full version, minimal permissions (docs/guides/security.md)."""

import re
from pathlib import Path

import pytest
import yaml

WORKFLOWS = sorted((Path(__file__).resolve().parents[3] / ".github" / "workflows").glob("*.y*ml"))
# A full version tag (v7.0.1): readable and easy to bump; no branches or major-only tags.
_PINNED = re.compile(r"^[\w.-]+/[\w./-]+@v\d+\.\d+\.\d+$")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _steps_and_jobs(workflow: dict) -> list[dict]:
    items: list[dict] = []
    for job in workflow.get("jobs", {}).values():
        items.append(job)
        items.extend(job.get("steps", []))
    return items


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_actions_pinned_to_full_version(workflow: Path):
    uses = [item["uses"] for item in _steps_and_jobs(_load(workflow)) if "uses" in item]
    unpinned = [ref for ref in uses if not ref.startswith("./") and not _PINNED.match(ref)]
    assert not unpinned


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_permissions_default_to_none(workflow: Path):
    data = _load(workflow)
    # Reusable workflows inherit the permissions of the calling job instead.
    if "workflow_call" in (data.get(True) or data.get("on") or {}):
        assert "permissions" not in data
        return
    assert data.get("permissions") == {}
    for name, job in data["jobs"].items():
        assert "permissions" in job, f"job {name} must declare its permissions"
