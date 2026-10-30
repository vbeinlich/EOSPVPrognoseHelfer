import copy
import json
from pathlib import Path

import pytest
from admin_plan_check import validate

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def plan():
    return json.loads((ROOT / "docs/release-admin/security-plan.json").read_text())


def test_prepared_plan_is_safe_but_not_authorized_or_applied(plan):
    assert validate(plan) == {"safe_proposal": True, "applied": False,
        "reviewer_selection_pending": True, "administration_authorized": False}
    ready = copy.deepcopy(plan)
    ready["environment"]["reviewers"][0]["id"] = 123456
    assert validate(ready)["reviewer_selection_pending"] is False
    assert plan["operator_approved"] is False


def test_review_worksheet_identifies_only_the_frozen_candidate_without_approval():
    form = json.loads((ROOT / "docs/release-admin/license-review-template.json").read_text())
    active = json.loads((ROOT / "docs/GENETIC_ACCEPTANCE.json").read_text())
    for key in ("source_revision", "version", "image_digest", "inventory_sha256", "source_material_sha256"):
        assert form[key] == active["license_review"][key]
    assert form["approved"] is False and form["operator_release_approved"] is False
    assert form["reviewer"] is None and form["reviewed_at_utc"] is None


@pytest.mark.parametrize("failure", ["spoof-check", "admin-bypass", "stale-review", "bypass-user",
    "linear-history", "force-push", "deployment-tag", "deployment-wildcard", "self-review", "no-reviewer", "env-bypass"])
def test_insecure_admin_proposals_are_rejected(plan, failure):
    if failure == "spoof-check":
        plan["main_protection"]["required_status_checks"]["checks"][0]["app_id"] = -1
    elif failure == "admin-bypass":
        plan["main_protection"]["enforce_admins"] = False
    elif failure == "stale-review":
        plan["main_protection"]["required_pull_request_reviews"]["dismiss_stale_reviews"] = False
    elif failure == "bypass-user":
        plan["main_protection"]["required_pull_request_reviews"]["bypass_pull_request_allowances"]["users"] = ["anyone"]
    elif failure == "linear-history":
        plan["main_protection"]["required_linear_history"] = True
    elif failure == "force-push":
        plan["main_protection"]["allow_force_pushes"] = True
    elif failure in ("deployment-tag", "deployment-wildcard"):
        plan["deployment_branch"]["type" if failure == "deployment-tag" else "name"] = "tag" if failure == "deployment-tag" else "*"
    elif failure == "self-review":
        plan["environment"]["prevent_self_review"] = False
    elif failure == "no-reviewer":
        plan["environment"]["reviewers"] = []
    else:
        plan["manual_environment_settings"]["allow_admin_bypass"] = True
    with pytest.raises(ValueError):
        validate(plan)
