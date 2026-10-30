import copy
import hashlib

import pytest
from publication import DockerRegistry, decision, promote, semver, validate_ci
from release_gate import validate_license_review

DIGEST = "sha256:" + "d" * 64
SOURCE = "a" * 40
RAW = b'{"synthetic_inventory":true}\n'


@pytest.fixture
def approval():
    checks = {key: True for key in ("sync_recent", "write_mode", "sync_no_errors", "imports_verified",
        "pv_state_verified", "price_control_complete", "soc_usable", "soc_fresh", "soc_proof",
        "no_uncertain_claims", "delivery_version_matches", "plan_matches_claim", "control_24h",
        "claim_timing", "solution_content_valid", "soc_proof_values_match")}
    return {"status": "approved", "operator_approved": True, "source_revision": SOURCE,
        "acceptance_comment": "https://github.com/vbeinlich/EOSPVPrognoseHelfer/issues/1#issuecomment-1",
        "issue_1_closed_comment": "https://github.com/vbeinlich/EOSPVPrognoseHelfer/issues/1#issuecomment-2",
        "doctor": {"accepted": True, "status": "accepted", "checks": checks,
            "plan": {"version": "b" * 64}, "artifact_sha256": {name: "c" * 64 for name in (
                "sync-report.json", "sync-state.json", "prices.json", "solution-" + "b" * 64 + ".json")}},
        "license_review": {"approved": True, "reviewer": "Synthetic reviewer",
            "reviewed_at_utc": "2026-10-29T13:00:00Z", "image_digest": DIGEST,
            "inventory_sha256": hashlib.sha256(RAW).hexdigest(), "source_revision": SOURCE,
            "version": "v0.1.0", "source_material_sha256": "f" * 64,
            "source_material_url": "https://github.com/vbeinlich/EOSPVPrognoseHelfer/releases/download/v0.1.0/sources.tar.gz"},
        "publication": {"enabled": True, "allow_initial_latest": True}}


class Registry:
    def __init__(self):
        self.tags, self.writes, self.smokes = {}, [], []
        self.labels = {DIGEST: {"version": "v0.1.0", "revision": SOURCE,
            "source": "https://github.com/vbeinlich/EOSPVPrognoseHelfer", "inventory": RAW}}
        self.fail_smoke = False
        self.fail_write = None
        self.fail_sources = False

    def candidate(self, digest):
        return self.labels[digest]

    def smoke(self, digest, revision):
        self.smokes.append((digest, revision))
        if self.fail_smoke:
            raise ValueError("Synthetic smoke failure")

    def source_material(self, review, inventory):
        if self.fail_sources:
            raise ValueError("Synthetic source-coverage failure")

    def digest(self, tag):
        return self.tags.get(tag)

    def latest(self):
        digest = self.tags.get("latest")
        return {"digest": digest, "version": self.labels[digest]["version"]} if digest else None

    def assign(self, tag, digest):
        if tag == self.fail_write:
            raise ValueError("Synthetic registry error")
        self.writes.append((tag, digest))
        self.tags[tag] = digest


def test_default_dry_run_has_no_public_writes_even_with_approved_evidence(approval):
    registry = Registry()
    result = promote(approval, "v0.1.0", DIGEST, registry)
    assert result["mode"] == "dry-run" and result["writes"] == 0
    assert registry.writes == [] and registry.tags == {}
    assert registry.smokes == [(DIGEST, SOURCE)]


def test_approved_exact_candidate_is_promoted_once_and_rerun_is_idempotent(approval):
    registry = Registry()
    assert promote(approval, "v0.1.0", DIGEST, registry, apply=True)["writes"] == 2
    assert registry.tags == {"v0.1.0": DIGEST, "latest": DIGEST}
    assert promote(approval, "v0.1.0", DIGEST, registry, apply=True)["writes"] == 0
    assert len(registry.writes) == 2


@pytest.mark.parametrize("failure", ["digest", "inventory", "revision", "version", "source",
    "no-operator", "no-license", "no-doctor", "initial-not-approved", "publication-disabled", "smoke", "sources"])
def test_failed_candidate_never_writes_any_tag(approval, failure):
    registry = Registry()
    if failure == "digest":
        approval["license_review"]["image_digest"] = "sha256:" + "e" * 64
    elif failure in ("inventory", "revision", "version", "source"):
        registry.labels[DIGEST][failure] = b"changed" if failure == "inventory" else "changed"
    elif failure == "no-operator":
        approval["operator_approved"] = False
    elif failure == "no-license":
        approval["license_review"]["approved"] = False
    elif failure == "no-doctor":
        approval["doctor"] = None
    elif failure == "initial-not-approved":
        approval["publication"]["allow_initial_latest"] = False
    elif failure == "publication-disabled":
        approval["publication"]["enabled"] = False
    elif failure == "sources":
        registry.fail_sources = True
    else:
        registry.fail_smoke = True
    with pytest.raises(ValueError):
        promote(approval, "v0.1.0", DIGEST, registry, apply=True)
    assert registry.writes == []


def test_delayed_older_release_after_newer_cannot_roll_back_latest(approval):
    registry = Registry()
    newer, newer_digest = copy.deepcopy(approval), "sha256:" + "e" * 64
    newer["license_review"].update(version="v0.2.0", image_digest=newer_digest)
    newer["license_review"]["source_material_url"] = newer["license_review"]["source_material_url"].replace("v0.1.0", "v0.2.0")
    registry.labels[newer_digest] = {**registry.labels[DIGEST], "version": "v0.2.0"}
    promote(newer, "v0.2.0", newer_digest, registry, apply=True)
    before = copy.deepcopy(registry.tags)
    registry.writes.clear()
    with pytest.raises(ValueError, match="older"):
        promote(approval, "v0.1.0", DIGEST, registry, apply=True)
    assert registry.tags == before and registry.writes == []


def test_registry_change_after_planning_stops_before_writes(approval):
    registry = Registry()
    original = registry.digest
    calls = []

    def changed(tag):
        calls.append(tag)
        return "sha256:" + "f" * 64 if len(calls) > 1 else original(tag)

    registry.digest = changed
    with pytest.raises(ValueError, match="changed"):
        promote(approval, "v0.1.0", DIGEST, registry, apply=True)
    assert registry.writes == []


def test_failed_version_assignment_never_moves_latest(approval):
    registry = Registry()
    registry.fail_write = "v0.1.0"
    with pytest.raises(ValueError):
        promote(approval, "v0.1.0", DIGEST, registry, apply=True)
    assert "latest" not in registry.tags and registry.writes == []


@pytest.mark.parametrize("version", ["v01.0.0", "v1.0.0-rc.1", "1.0.0", "v1.0", "v1.0.0;echo bad"])
def test_nonstable_or_ambiguous_version_is_rejected(version):
    with pytest.raises(ValueError):
        semver(version)


def test_existing_version_and_ambiguous_latest_are_fail_closed():
    with pytest.raises(ValueError, match="Version tag"):
        decision("v0.1.0", DIGEST, "sha256:" + "a" * 64, None, allow_initial=True)
    with pytest.raises(ValueError):
        decision("v0.1.0", DIGEST, None, {"version": "preview", "digest": DIGEST})


def test_inventory_cannot_be_approved_without_a_digest_binding(approval):
    with pytest.raises(ValueError, match="digest, source"):
        validate_license_review(approval["license_review"], inventory=RAW)


@pytest.mark.parametrize("stderr", [b"unauthorized", b"timeout", b"unexpected server response 500"])
def test_registry_failure_is_never_interpreted_as_missing_tag(monkeypatch, stderr):
    from types import SimpleNamespace
    monkeypatch.setattr("publication.subprocess.run", lambda *a, **kw: SimpleNamespace(
        returncode=1, stderr=stderr, stdout=b""))
    with pytest.raises(ValueError, match="Registry command failed"):
        DockerRegistry().digest("latest")


def test_candidate_ci_must_belong_to_exact_source_and_latest_run():
    good = {"id": 1, "head_sha": SOURCE, "event": "push", "path": ".github/workflows/test.yaml",
            "run_number": 1, "run_attempt": 1, "status": "completed", "conclusion": "success"}
    assert validate_ci([good], SOURCE) == 1
    with pytest.raises(ValueError):
        validate_ci([good], "b" * 40)
    with pytest.raises(ValueError):
        validate_ci([good, {**good, "run_attempt": 2, "conclusion": "failure"}], SOURCE)
    with pytest.raises(ValueError):
        validate_ci([{**good, "event": "pull_request"}], SOURCE)


def test_historical_doctor_needs_explicit_provenance_approval(approval):
    approval["doctor"].update(evidence_mode="historical_snapshot",
        current_freshness_verified=False, captured_at_utc="2026-10-29T13:00:00Z",
        capture_manifest_sha256="f" * 64)
    registry = Registry()
    with pytest.raises(ValueError, match="provenance"):
        promote(approval, "v0.1.0", DIGEST, registry)
    assert registry.writes == []
    approval["historical_snapshot_operator_approved"] = True
    assert promote(approval, "v0.1.0", DIGEST, registry)["writes"] == 0
    approval["doctor"]["current_freshness_verified"] = True
    with pytest.raises(ValueError, match="provenance"):
        promote(approval, "v0.1.0", DIGEST, registry)


def test_newer_latest_appearing_after_version_write_is_not_overwritten(approval):
    registry = Registry()
    assign = registry.assign
    newer = "sha256:" + "9" * 64
    registry.labels[newer] = {**registry.labels[DIGEST], "version": "v9.0.0"}

    def concurrent(tag, digest):
        assign(tag, digest)
        registry.tags["latest"] = newer

    registry.assign = concurrent
    with pytest.raises(ValueError, match="Latest changed"):
        promote(approval, "v0.1.0", DIGEST, registry, apply=True)
    assert registry.tags["latest"] == newer
    assert registry.writes == [("v0.1.0", DIGEST)]
