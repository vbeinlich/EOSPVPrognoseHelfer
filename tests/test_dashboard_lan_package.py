import hashlib
import json
from pathlib import Path

import pytest
from build_dashboard_lan_package import package
from check_dashboard_lan_hashes import check

ROOT = Path(__file__).resolve().parents[1]
REVISION = "8011a6d2849f5f17479dd1293f5806d39b3456e7"


def test_transfer_package_only_explicit_review_files_and_matching_hashes(tmp_path):
    check()
    target = tmp_path / "new-private-package"
    manifest = package(target, REVISION)
    assert manifest["activation_approved"] is False
    assert manifest["source_solution_hashes"] == []
    assert manifest["review_commit"] == REVISION
    assert all(name.startswith(("tools/", "server/", "docs/")) for name in manifest["files"])
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((target / name).read_bytes()).hexdigest() == digest
        assert (target / name).stat().st_mode & 0o077 == 0
    assert json.loads((target / "PACKAGE_HASHES.json").read_text()) == manifest
    with pytest.raises(FileExistsError):
        package(target, REVISION)


def test_optional_checked_sidecar_is_copied_without_replay(tmp_path):
    sidecar = ROOT / "tests/fixtures/replay-synthetic-sidecar.json"
    target = tmp_path / "with-private-replay"
    manifest = package(target, REVISION, sidecar)
    assert (target / "replays" / sidecar.name).read_bytes() == sidecar.read_bytes()
    assert len(manifest["source_solution_hashes"]) == 1
    assert not list(target.rglob("solution-*.json"))
    assert not list(target.rglob("*.png"))


def test_invalid_sidecar_never_creates_transfer_folder(tmp_path):
    bad = tmp_path / "bad-sidecar.json"
    bad.write_text('{"plans":[]}')
    target = tmp_path / "must-not-exist"
    with pytest.raises(ValueError):
        package(target, REVISION, bad)
    assert not target.exists()
