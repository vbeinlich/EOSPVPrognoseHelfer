"""Offline release evidence gate. Never creates tags, mutates state or calls EOS."""

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path


def validate_license_review(review, *, inventory=None, image_digest=None,
                            source_revision=None, version=None):
    """An approval names one candidate, not every image of a project/version."""
    if (not isinstance(review, dict) or review.get("approved") is not True
            or not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip()):
        raise ValueError("Candidate-specific third-party license review is outstanding")
    try:
        at = datetime.fromisoformat(review["reviewed_at_utc"].replace("Z", "+00:00"))
        if at.utcoffset() is None:
            raise ValueError("Naive review time")
    except (KeyError, TypeError, AttributeError, ValueError):
        raise ValueError("An aware license-review timestamp is required") from None
    for key, pattern in (("image_digest", r"sha256:[0-9a-f]{64}"),
                         ("inventory_sha256", r"[0-9a-f]{64}"),
                         ("source_material_sha256", r"[0-9a-f]{64}"),
                         ("source_revision", r"[0-9a-f]{40}"),
                         ("version", r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")):
        if not isinstance(review.get(key), str) or not re.fullmatch(pattern, review[key]):
            raise ValueError("License approval must identify the exact " + key)
    prefix = "https://github.com/vbeinlich/EOSPVPrognoseHelfer/releases/download/" + review["version"] + "/"
    url = review.get("source_material_url", "")
    if not isinstance(url, str) or not url.startswith(prefix) or not re.fullmatch(
        r"[A-Za-z0-9_.+-]+\.tar\.gz", url[len(prefix):]
    ):
        raise ValueError("Approved corresponding source must be a versioned release asset")
    for key, observed in (("image_digest", image_digest), ("source_revision", source_revision),
                           ("version", version)):
        if observed is not None and review[key] != observed:
            raise ValueError("License approval differs from candidate " + key)
    if inventory is not None:
        if image_digest is None or source_revision is None or version is None:
            raise ValueError("Inventory verification needs digest, source revision and version")
        raw = inventory if isinstance(inventory, bytes) else Path(inventory).read_bytes()
        if hashlib.sha256(raw).hexdigest() != review["inventory_sha256"]:
            raise ValueError("Candidate dependency/license inventory differs from the reviewed inventory")
    return review


def validate(record, *, inventory=None, image_digest=None, source_revision=None, version=None):
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
    if (not isinstance(evidence, dict) or evidence.get("accepted") is not True
            or evidence.get("status") != "accepted"):
        raise ValueError("A real successful read-only Doctor report is required")
    if evidence.get("evidence_mode") == "historical_snapshot":
        if (record.get("historical_snapshot_operator_approved") is not True
                or evidence.get("current_freshness_verified") is not False
                or not re.fullmatch(r"[0-9a-f]{64}", evidence.get("capture_manifest_sha256", ""))
                or not evidence.get("captured_at_utc")):
            raise ValueError("Historical snapshot needs explicit provenance review")
    checks = evidence.get("checks", {})
    required = {"sync_recent", "write_mode", "sync_no_errors", "imports_verified", "pv_state_verified",
        "price_control_complete", "soc_usable", "soc_fresh", "soc_proof", "no_uncertain_claims",
        "delivery_version_matches", "plan_matches_claim", "control_24h", "claim_timing",
        "solution_content_valid", "soc_proof_values_match"}
    if not required <= checks.keys() or not all(v is True for v in checks.values()):
        raise ValueError("Incomplete or failed Doctor checks")
    hashes = evidence.get("artifact_sha256", {})
    event_version = evidence.get("plan", {}).get("version", "")
    if not re.fullmatch(r"[0-9a-f]{64}", event_version) or not all(
        re.fullmatch(r"[0-9a-f]{64}", hashes.get(name, ""))
        for name in ("sync-report.json", "sync-state.json", "prices.json", "solution-" + event_version + ".json")
    ):
        raise ValueError("Plan and artifact hashes are required")
    validate_license_review(record.get("license_review"), inventory=inventory,
                            image_digest=image_digest, source_revision=source_revision,
                            version=version)
    return revision


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", default="docs/GENETIC_ACCEPTANCE.json")
    parser.add_argument("--inventory")
    parser.add_argument("--image-digest")
    parser.add_argument("--source-revision")
    parser.add_argument("--version")
    args = parser.parse_args()
    try:
        revision = validate(json.loads(Path(args.evidence).read_text()), inventory=args.inventory,
                            image_digest=args.image_digest, source_revision=args.source_revision,
                            version=args.version)
    except (OSError, ValueError, TypeError, AttributeError):
        raise SystemExit("Release blocked: real GENETIC/operator/license acceptance missing or invalid") from None
    print(revision)
