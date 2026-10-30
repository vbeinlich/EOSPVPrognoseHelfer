import copy
from pathlib import Path

import pytest
from workflow_policy import GROUP, load, validate

ROOT = Path(__file__).resolve().parents[1]


def test_actual_workflows_have_one_serialized_manual_publisher():
    workflows = load(ROOT / ".github/workflows")
    assert validate(workflows) == {"managed_publishers": 1, "automatic_publication": False,
                                   "global_lock": GROUP}
    assert "release/**" in workflows["test.yaml"]["on"]["push"]["branches"]


@pytest.mark.parametrize("failure", ["main-writer", "auto-trigger", "default-apply", "per-version-lock",
    "per-ref-lock", "cancel-active", "missing-environment", "missing-plan", "missing-opt-in",
    "planning-writer", "automatic-upload", "new-publisher"])
def test_unsafe_workflow_mutations_fail_policy(failure):
    workflows = copy.deepcopy(load(ROOT / ".github/workflows"))
    promotion = workflows["promote.yaml"]
    if failure == "main-writer":
        workflows["test.yaml"]["jobs"]["unit"]["permissions"] = {"packages": "write"}
    elif failure == "auto-trigger":
        promotion["on"]["push"] = {}
    elif failure == "default-apply":
        promotion["on"]["workflow_dispatch"]["inputs"]["apply"]["default"] = "true"
    elif failure in ("per-version-lock", "per-ref-lock"):
        promotion["concurrency"]["group"] = GROUP + "-${{ inputs.version }}" if failure == "per-version-lock" else "${{ github.ref }}"
    elif failure == "cancel-active":
        promotion["concurrency"]["cancel-in-progress"] = "true"
    elif failure == "missing-environment":
        promotion["jobs"]["promote"].pop("environment")
    elif failure == "missing-plan":
        promotion["jobs"]["promote"].pop("needs")
    elif failure == "missing-opt-in":
        promotion["jobs"]["promote"]["if"] = "inputs.apply"
    elif failure == "planning-writer":
        promotion["jobs"]["plan"]["permissions"]["packages"] = "write"
    elif failure == "automatic-upload":
        workflows["test.yaml"]["jobs"]["unit"]["steps"].append({"run": "docker push unsafe"})
    else:
        workflows["second.yaml"] = {"on": {"workflow_dispatch": {}},
            "jobs": {"publish": {"permissions": {"packages": "write"}}}}
    with pytest.raises(ValueError):
        validate(workflows)
