"""Writer admission, exact pre-dispatch inputs and atomic commit fault cases."""

import copy
import json
import threading
from datetime import timedelta
from pathlib import Path

import pytest
from test_evidence import archive, build_case, tick
from test_sync import writes

from eos_pv_helper import evidence, historical
from eos_pv_helper.replay_worker import Worker, snapshot


@pytest.fixture
def case(config, monkeypatch, tmp_path):
    config["output"]["directory"] = str(tmp_path / "originals")
    value = build_case(config, monkeypatch)
    monkeypatch.setenv("DRY_RUN", "false")
    return value


@pytest.mark.parametrize("missing", ["controls_start_at_now", "parameters", "terminal_value",
                                    "inverter_option", "result_series"])
def test_incomplete_model_response_keeps_original_success_but_cannot_commit_replay_archive(case, missing):
    original = case["http"]

    def http(url, **kwargs):
        value = original(url, **kwargs)
        if url.endswith("/v1/optimize"):
            if missing == "inverter_option":
                del value["parameters"]["inverter"]["ac_charge_limits_total_charge"]
            elif missing == "result_series":
                del value["result"]["battery_soc_per_hour"]
            else:
                del value[missing]
        return value

    case["http"] = http
    report = tick(case)
    root = Path(case["config"]["output"]["directory"])
    assert report["event"]["status"] == "succeeded" and report["errors"] == {}
    reason = ("invalid_incomplete_or_private_evidence" if missing in ("controls_start_at_now", "parameters")
              else "archive_saved_model_not_replay_compatible")
    assert report["evidence"] == {"status": "evidence_missing", "reason": reason}
    saved = next(root.glob("solution-*.json")).read_bytes()
    assert tick(case)["evidence"]["status"] == "evidence_missing"
    assert next(root.glob("solution-*.json")).read_bytes() == saved
    assert not list((root / evidence.DIRECTORY).glob("*.zip")) and len(writes(case, "POST")) == 1


@pytest.mark.parametrize("key", ["total_load", "feed_in_tariff_per_wh"])
def test_returned_model_cannot_silently_change_dispatch_load_or_tariff(case, key):
    original = case["http"]

    def http(url, **kwargs):
        value = original(url, **kwargs)
        if url.endswith("/v1/optimize"):
            value["parameters"]["ems"][key][0] += .01
            if key == "feed_in_tariff_per_wh":
                value["result"]["feed_in_tariff"][0] += .01
        return value

    case["http"] = http
    report = tick(case)
    assert report["event"]["status"] == "succeeded"
    assert report["evidence"]["reason"] == "archive_dispatch_solver_series_differ"
    assert len(writes(case, "POST")) == 1


@pytest.mark.parametrize("gate", ["accepted", "checks", "runtime_context", "validation_scope"])
def test_no_final_archive_when_any_worker_admission_gate_is_missing(case, monkeypatch, gate):
    original = historical.validate

    def validate(*args, **kwargs):
        result = original(*args, **kwargs)
        if gate == "checks":
            result["checks"]["historical_inputs_complete"] = False
        elif gate == "runtime_context":
            result[gate] = {"status": "not_available"}
        else:
            result[gate] = False if gate == "accepted" else "event_artifacts_only"
        return result

    monkeypatch.setattr(historical, "validate", validate)
    report = tick(case)
    assert report["evidence"]["reason"] == "archive_replay_binding_not_proven"
    root = Path(case["config"]["output"]["directory"])
    assert not list((root / evidence.DIRECTORY).glob("*.zip"))


def test_writer_output_is_accepted_by_unmodified_worker_admission(case):
    report = tick(case)
    version = report["event"]["version"]
    root = Path(case["config"]["output"]["directory"])
    raw, binding = snapshot(root, version, case["now"])
    manifest, files = historical.unpack(archive(case).read_bytes())
    captured = manifest["producer"]["dispatch_series_binding"]
    assert captured["contract"] == evidence.REPLAY_ADMISSION
    assert set(captured["series"]) == set(evidence.SERIES.values())
    assert binding["input_binding_complete"] and raw == files["solution-"+version+".json"]
    assert report["evidence"]["replay_admission"]["status"] == "ready_for_native_replay"
    assert report["evidence"]["replay_admission"]["native_result_verified"] is False


def test_post_cannot_replace_captured_series_with_new_current_values(case):
    original = case["http"]

    def http(url, **kwargs):
        value = original(url, **kwargs)
        if url.endswith("/v1/optimize"):
            for series in case["series"].values():
                for key in series:
                    series[key] = 9999
            case["settings"]["prediction"]["hours"] = 168
        return value

    case["http"] = http
    assert tick(case)["evidence"]["status"] == "archived"
    manifest, _ = historical.unpack(archive(case).read_bytes())
    assert set(manifest["producer"]["dispatch_series_binding"]["series"]["total_load"]) == {500}
    assert manifest["producer"]["observed_options"]["prediction_hours"] == 48


@pytest.mark.parametrize("rehash", [False, True])
def test_changed_dispatch_series_proof_is_rejected_even_with_valid_artifact_hashes(case, rehash):
    report = tick(case)
    path = archive(case)
    manifest, files = historical.unpack(path.read_bytes())
    proof = manifest["producer"]["dispatch_series_binding"]
    proof["series"]["total_load"][0] += 10
    if rehash:
        proof["series_sha256"] = historical.canonical_sha(proof["series"])
    path.chmod(0o600)  # Explicit synthetic tamper; no original archives involved.
    path.write_bytes(historical.pack(manifest, files))
    claim = json.loads(files["sync-state.json"])["events"][report["event"]["version"]]
    with pytest.raises(evidence.EvidenceError, match="archive_dispatch_"):
        evidence.inspect_archive(path.parent.parent, case["config"], path.stem, claim,
            manifest["files"]["solution-"+path.stem+".json"], lambda: case["now"])


def test_conflicting_manifest_is_not_silently_accepted_when_artifact_hashes_match(case):
    tick(case)
    path = archive(case)
    original = path.read_bytes()
    manifest, files = historical.unpack(original)
    alternate = copy.deepcopy(manifest)
    alternate["captured_at_utc"] = (case["now"]+timedelta(seconds=1)).isoformat()
    target = path.parent
    def verify(raw):
        return historical.unpack(raw)[0]
    with pytest.raises(evidence.EvidenceError, match="archive_conflict_preserved"):
        evidence._publish(target, target / ".pending", historical.pack(alternate, files), path.stem, verify)
    assert path.read_bytes() == original


def test_reader_sees_no_partial_archive_and_worker_waits_for_sync_commit(case, tmp_path, monkeypatch):
    root = Path(case["config"]["output"]["directory"])
    work = tmp_path / "private-replays"
    work.mkdir(mode=0o700)
    reached, finish = threading.Event(), threading.Event()
    link, outcome = evidence.os.link, []

    def held_link(source, target):
        if str(target).endswith(".zip"):
            reached.set()
            assert finish.wait(10)
        return link(source, target)

    def forbidden(*args, **kwargs):
        pytest.fail("Worker must never run a native model before the writer's commit")

    monkeypatch.setattr(evidence.os, "link", held_link)
    writer = threading.Thread(target=lambda: outcome.append(tick(case)))
    writer.start()
    try:
        assert reached.wait(10)
        assert not list((root / evidence.DIRECTORY).glob("*.zip"))
        ready = next((root / evidence.DIRECTORY / ".pending").glob("*.ready"))
        assert historical.validate(*historical.unpack(ready.read_bytes()), now=case["now"])["accepted"]
        worker = Worker(root, work, runner=forbidden, now=lambda: case["now"]-timedelta(seconds=1))
        with pytest.raises(ValueError, match="source_busy"):
            worker.tick()
        assert not (work / "catalog.json").exists()
    finally:
        finish.set()
        writer.join(10)
    assert not writer.is_alive() and outcome[0]["evidence"]["status"] == "archived"
    assert historical.validate(*historical.unpack(archive(case).read_bytes()), now=case["now"])["accepted"]
    assert json.loads((root / "sync-state.json").read_bytes())["events"]
