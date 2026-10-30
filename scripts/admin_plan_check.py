"""Validate an offline administrative proposal. No network or apply capability."""

import argparse
import json
from pathlib import Path


def validate(plan):
    main = plan["main_protection"]
    ci = main["required_status_checks"]
    if ci.get("strict") is not True or {(c["context"], c["app_id"]) for c in ci["checks"]} != {
        ("unit", 15368), ("eos-integration", 15368)
    }:
        raise ValueError("Require current GitHub Actions checks bound to their verified App ID")
    if (main.get("enforce_admins") is not True or main.get("required_linear_history") is not False
            or main.get("allow_force_pushes") is not False or main.get("allow_deletions") is not False
            or main.get("required_conversation_resolution") is not True):
        raise ValueError("Main protection must prevent bypass/downgrades and preserve normal merges")
    reviews = main["required_pull_request_reviews"]
    if (reviews.get("dismiss_stale_reviews") is not True or reviews.get("require_last_push_approval") is not True
            or reviews.get("required_approving_review_count", 0) < 1
            or any(reviews["bypass_pull_request_allowances"].values())):
        raise ValueError("Independent current approval without bypass is required")
    env = plan["environment"]
    if (plan.get("environment_name") != "public-image-release" or env.get("prevent_self_review") is not True
            or env.get("deployment_branch_policy") != {"protected_branches": False, "custom_branch_policies": True}
            or plan.get("deployment_branch") != {"name": "main", "type": "branch"}
            or plan.get("manual_environment_settings", {}).get("allow_admin_bypass") is not False):
        raise ValueError("Environment requires independent review, main branch only and no admin bypass")
    reviewers = env.get("reviewers", [])
    if not reviewers or any(r.get("type") != "User" or (
        r.get("id") is not None and (type(r["id"]) is not int or r["id"] <= 0)
    ) for r in reviewers):
        raise ValueError("Explicit authorized reviewer IDs required")
    return {"safe_proposal": True, "applied": False,
            "reviewer_selection_pending": any(r["id"] is None for r in reviewers),
            "administration_authorized": plan.get("operator_approved") is True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", default="docs/release-admin/security-plan.json")
    args = parser.parse_args()
    print(json.dumps(validate(json.loads(Path(args.plan).read_text())), indent=2))
