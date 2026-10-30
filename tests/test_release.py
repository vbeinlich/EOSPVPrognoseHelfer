import copy
import importlib.util
import json
from email.message import Message
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_genetic_acceptance_alone_does_not_authorize_release():
    gate = script("release_gate")
    with pytest.raises(ValueError, match="approval"):
        gate.validate(json.loads((ROOT / "docs/GENETIC_ACCEPTANCE.json").read_text()))


def test_release_requires_complete_evidence_and_exact_candidate_inventory(tmp_path):
    gate = script("release_gate")
    path = tmp_path / "inventory.json"
    path.write_text("{}\n")
    import hashlib
    record = {"status": "approved", "operator_approved": True, "source_revision": "a" * 40,
        "acceptance_comment": "https://github.com/vbeinlich/EOSPVPrognoseHelfer/issues/1#issuecomment-1",
        "issue_1_closed_comment": "https://github.com/vbeinlich/EOSPVPrognoseHelfer/issues/1#issuecomment-2",
        "license_review": {"approved": True, "reviewer": "synthetic reviewer",
                           "reviewed_at_utc": "2026-10-29T13:00:00Z",
                           "image_digest": "sha256:" + "d" * 64,
                           "source_revision": "a" * 40, "version": "v0.1.0",
                           "source_material_url": "https://github.com/vbeinlich/EOSPVPrognoseHelfer/releases/download/v0.1.0/sources.tar.gz",
                           "source_material_sha256": "b" * 64,
                           "inventory_sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
        "doctor": {"accepted": True, "status": "accepted", "checks": {key: True for key in (
            "sync_recent", "write_mode", "sync_no_errors", "imports_verified", "pv_state_verified",
            "price_control_complete", "soc_usable", "soc_fresh", "soc_proof", "no_uncertain_claims",
            "delivery_version_matches", "plan_matches_claim", "control_24h", "claim_timing",
            "solution_content_valid", "soc_proof_values_match")}, "plan": {"version": "b" * 64}, "artifact_sha256": {
                name: "c" * 64 for name in ("sync-report.json", "sync-state.json", "prices.json",
                                          "solution-" + "b" * 64 + ".json")}}}
    binding = {"image_digest": "sha256:" + "d" * 64, "source_revision": "a" * 40,
               "version": "v0.1.0"}
    assert gate.validate(record, inventory=path, **binding) == "a" * 40
    for field in ("operator_approved", "acceptance_comment", "issue_1_closed_comment", "source_revision"):
        wrong = copy.deepcopy(record)
        wrong[field] = False if field == "operator_approved" else "invalid"
        with pytest.raises(ValueError):
            gate.validate(wrong, inventory=path, **binding)
    for field in record["doctor"]["checks"]:
        wrong = copy.deepcopy(record)
        wrong["doctor"]["checks"][field] = False
        with pytest.raises(ValueError):
            gate.validate(wrong, inventory=path, **binding)
    path.write_text('{"changed": true}')
    with pytest.raises(ValueError, match="differs"):
        gate.validate(record, inventory=path, **binding)


def distribution(tmp_path, name, license, files):
    metadata = Message()
    metadata["Name"], metadata["License-Expression"] = name, license
    for file in files:
        path = tmp_path / file
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_text("synthetic notice")
    return SimpleNamespace(metadata=metadata, version="1.0", files=files,
                           locate_file=lambda file: tmp_path / file)


def test_inventory_preserves_nested_notices_and_lgpl_source(tmp_path):
    inventory = script("license_inventory")
    packages = [distribution(tmp_path, "example", "BSD-3-Clause", ["d.dist-info/LICENSE",
                 "vendor/lib/NOTICE", "vendor/lib/licenses.py"]),
                distribution(tmp_path, "example-lgpl", "LGPL-2.1-or-later", ["x.dist-info/COPYING"])]
    calls = []

    def source(name, version, directory):
        calls.append((name, version))
        return {"notices": ["COPYING"], "sha256": "a" * 64, "filename": "source.tar.gz"}

    result = inventory.collect(tmp_path / "output", distributions=packages,
                               system=tmp_path / "no-os", fetch_source=source)
    assert calls == [("example-lgpl", "1.0")]
    assert len(result["python"][0]["notices"]) == 2
    assert result["legal_review_required"] is True
    for entry in result["python"]:
        for notice in entry["notices"]:
            assert (tmp_path / "output" / entry["directory"] / notice["file"]).is_file()


def test_unknown_missing_license_never_silently_passes(tmp_path):
    inventory = script("license_inventory")
    package = distribution(tmp_path, "unreviewed", "MIT", [])
    with pytest.raises(ValueError, match="Reviewed upstream notice required"):
        inventory.collect(tmp_path / "output", distributions=[package], system=tmp_path / "absent",
                          fetch_source=lambda *a: {"notices": []})


def test_known_missing_upstream_license_uses_exact_reviewed_version_and_hash(tmp_path):
    inventory = script("license_inventory")
    package = distribution(tmp_path, "loguru", "", [])
    package.version = "0.7.3"
    result = inventory.collect(tmp_path / "output", distributions=[package], system=tmp_path / "absent",
                               fetch_source=lambda *a: {"notices": []})
    notice = result["python"][0]["reviewed_upstream_notice"]
    assert notice["url"].endswith("/0.7.3/LICENSE")
    assert (tmp_path / "output/python/loguru-0.7.3" / notice["file"]).read_bytes() == (
        ROOT / "licenses" / notice["file"]).read_bytes()


def test_automatic_workflows_cannot_publish_and_manual_promotion_is_separate():
    import yaml
    # BaseLoader deliberately retains GitHub's 'on' key instead of YAML 1.1 bools.
    build = yaml.load((ROOT / ".github/workflows/test.yaml").read_text(), Loader=yaml.BaseLoader)
    manual = yaml.load((ROOT / ".github/workflows/promote.yaml").read_text(), Loader=yaml.BaseLoader)
    assert set(build["on"]) == {"push", "pull_request"}
    assert "packages" not in build["permissions"]
    assert all(job.get("permissions", {}).get("packages") != "write" for job in build["jobs"].values())
    assert "push: true" not in json.dumps(build)
    assert set(manual["on"]) == {"workflow_dispatch"}
    assert manual["on"]["workflow_dispatch"]["inputs"]["apply"]["default"] == "false"
    assert "github.ref" not in manual["concurrency"]["group"]
    assert manual["concurrency"]["cancel-in-progress"] == "false"
    assert "PUBLICATION_ENABLED" in manual["jobs"]["promote"]["if"]
    assert manual["jobs"]["promote"]["environment"] == "public-image-release"


@pytest.mark.parametrize("failure", [None, "binary-version", "source-version", "unverified", "missing"])
def test_debian_source_coverage_is_exact(failure):
    inventory = script("license_inventory")
    status = "Package: binary\nStatus: install ok installed\nVersion: 1.0+b2\nSource: original (1.0)\n"
    index = {"dsc_checksums_verified": True,
             "binary_packages": [{"name": "binary", "version": "1.0+b2", "source": "original (1.0)"}],
             "source_packages": [{"name": "original", "version": "1.0"}]}
    if failure == "binary-version":
        index["binary_packages"][0]["version"] = "2.0"
    elif failure == "source-version":
        index["source_packages"][0]["version"] = "2.0"
    elif failure == "unverified":
        index["dsc_checksums_verified"] = False
    elif failure == "missing":
        index["source_packages"] = []
    if failure:
        with pytest.raises(ValueError, match="coverage changed"):
            inventory.validate_debian_coverage(status, index)
    else:
        inventory.validate_debian_coverage(status, index)
