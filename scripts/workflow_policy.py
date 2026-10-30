"""Offline checks for the sole managed publisher; no GitHub or registry writes."""

import argparse
from pathlib import Path

import yaml

GROUP = "eos-pv-helper-stable-public-promotion"


def validate(workflows):
    publishers = []
    for filename, workflow in workflows.items():
        if workflow.get("permissions", {}).get("packages") == "write":
            raise ValueError("Registry write permission must be job-scoped")
        for name, job in workflow.get("jobs", {}).items():
            if job.get("permissions", {}).get("packages") == "write":
                publishers.append((filename, name))
        if filename != "promote.yaml":
            steps = str(workflow.get("jobs", {}))
            if any(token in steps for token in ("--push", "type=registry", "docker push", "--apply")):
                raise ValueError("Automatic workflow contains a publication command")
            if "docker/build-push-action" in steps or "docker/login-action" in steps:
                raise ValueError("Build CI must not log in or publish images")
    if publishers != [("promote.yaml", "promote")]:
        raise ValueError("Exactly one manually gated registry writer is allowed")
    promotion = workflows["promote.yaml"]
    if set(promotion["on"]) != {"workflow_dispatch"}:
        raise ValueError("Promotion must never be triggered automatically")
    if promotion["on"]["workflow_dispatch"]["inputs"]["apply"]["default"] != "false":
        raise ValueError("Default must be read-only planning")
    concurrency = promotion.get("concurrency", {})
    if concurrency.get("group") != GROUP or concurrency.get("cancel-in-progress") != "false":
        raise ValueError("Every version and ref must hold the same workflow-wide lock")
    job = promotion["jobs"]["promote"]
    if (job.get("environment") != "public-image-release" or job.get("needs") != "plan"
            or job.get("if") != "inputs.apply && vars.PUBLICATION_ENABLED == 'true' && github.ref == 'refs/heads/main'"):
        raise ValueError("Explicit apply, main, repository opt-in, plan and protected environment required")
    if promotion["jobs"]["plan"].get("permissions", {}).get("packages") != "read":
        raise ValueError("Planning must only have registry read permission")
    return {"managed_publishers": 1, "automatic_publication": False, "global_lock": GROUP}


def load(directory):
    return {p.name: yaml.load(p.read_text(), Loader=yaml.BaseLoader)
            for p in sorted(Path(directory).glob("*.y*ml"))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflows", default=".github/workflows")
    args = parser.parse_args()
    print(validate(load(args.workflows)))
