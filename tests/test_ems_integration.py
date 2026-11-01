"""Cross-PR contracts and frozen release controls, no private data or GitHub mutations."""

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_all_review_consumers_are_in_one_ci_with_no_optimizer_execution():
    w = yaml.load((ROOT/".github/workflows/test.yaml").read_text(), Loader=yaml.BaseLoader)
    runs = "\n".join(s.get("run", "") for s in w["jobs"]["unit"]["steps"])
    for name in ("doctor_container_smoke.py", "make_evidence_fixture.py", "evidence_container_smoke.py",
                 "plan_inspector_smoke.py", "plan_ui_smoke.mjs"):
        assert name in runs
    for job in w["jobs"].values():
        assert job["env"]["PYTEST_ADDOPTS"] == '-m "not genetic_execution"'
    assert w["permissions"] == {"contents": "read"}


def test_frozen_release_acceptance_and_publication_controls_are_unchanged():
    manifest = json.loads((ROOT/"docs/EMS_SOURCE_MANIFEST.json").read_text())
    assert set(manifest["reviewed_heads"]) == {"9", "10", "13", "14", "15"}
    for name, digest in manifest["unchanged_controls_sha256"].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest


def test_new_example_features_do_not_enable_writes_or_archiving():
    import tomllib
    config = tomllib.loads((ROOT/"config.example.toml").read_text())
    assert config["evidence"]["enabled"] is False
    assert config["eos"]["write_enabled"] is False
    assert config["trigger"]["run_enabled"] is False
    assert config["prices"]["retail_prices_confirmed"] is False


def test_nas_bundle_cannot_load_new_actuals_or_start_a_simulation():
    import inspect
    import io
    import zipfile

    from build_plan_inspector import build

    from eos_pv_helper.plan_inspector import parse_plan
    with zipfile.ZipFile(io.BytesIO(build())) as bundle:
        assert "plan_actual.py" not in bundle.namelist()
        assert "event_context.py" not in bundle.namelist()
    assert inspect.signature(parse_plan).parameters["calculate"].default is False
