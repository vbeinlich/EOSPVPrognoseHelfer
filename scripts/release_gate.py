"""Offline release evidence gate. Never creates tags, mutates state or calls EOS."""

import argparse
import hashlib
import json
import re
from pathlib import Path


def validate(record, *, inventory=None):
    if record.get("status") != "approved" or record.get("operator_approved") is not True:
        raise ValueError("Stable release requires explicit reviewed operator approval")
    revision = record.get("source_revision", "")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Record the actually accepted runtime source revision")
    for key in ("acceptance_comment", "issue_1_closed_comment"):
        if not re.fullmatch(r"https://github.com/vbeinlich/EOSPVPrognoseHelfer/issues/1#issuecomment-[0-9]+",
                            record.get(key, "")):
            raise ValueError("Link the real operator acceptance and Issue #1 completion")
    evidence = record.get("doctor", {})
    if evidence.get("accepted") is not True or evidence.get("status") != "accepted":
        raise ValueError("A real successful read-only Doctor report is required")
    checks = evidence.get("checks", {})
    required = {"sync_recent", "write_mode", "sync_no_errors", "imports_verified", "pv_state_verified",
        "price_control_complete", "soc_usable", "soc_fresh", "soc_proof", "no_uncertain_claims",
        "delivery_version_matches", "plan_matches_claim", "control_24h", "claim_timing",
        "solution_content_valid", "soc_proof_values_match"}
    if not required <= checks.keys() or not all(v is True for v in checks.values()):
        raise ValueError("Incomplete or failed Doctor checks")
    hashes = evidence.get("artifact_sha256", {})
    version = evidence.get("plan", {}).get("version", "")
    if not re.fullmatch(r"[0-9a-f]{64}", version) or not all(
        re.fullmatch(r"[0-9a-f]{64}", hashes.get(name, ""))
        for name in ("sync-report.json", "sync-state.json", "prices.json", "solution-" + version + ".json")
    ):
        raise ValueError("Plan and artifact hashes are required")
    legal = record.get("license_review", {})
    if legal.get("approved") is not True or not legal.get("reviewer") or not legal.get("reviewed_at_utc"):
        raise ValueError("Candidate-specific third-party license review is outstanding")
    digest = legal.get("inventory_sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Record the reviewed candidate's exact inventory hash")
    if inventory is not None and hashlib.sha256(Path(inventory).read_bytes()).hexdigest() != digest:
        raise ValueError("Candidate dependency/license inventory differs from the reviewed inventory")
    return revision


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", default="docs/GENETIC_ACCEPTANCE.json")
    parser.add_argument("--inventory")
    args = parser.parse_args()
    try:
        revision = validate(json.loads(Path(args.evidence).read_text()), inventory=args.inventory)
    except (OSError, ValueError, TypeError, AttributeError):
        raise SystemExit("Release blocked: real GENETIC/operator/license acceptance missing or invalid") from None
    print(revision)
