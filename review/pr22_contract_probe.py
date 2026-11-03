"""Adversarial pinned-PR22 review: synthetic files, no network or optimizer.

Exit 2 means reproduced blockers. This is an explicit review probe, not acceptance.
Run in local read-only/network-none container, with tests on PYTHONPATH.
"""

import copy
import hashlib
import json
import socket
import tempfile
from datetime import timedelta
from pathlib import Path

from test_economics import saved
from test_historical_doctor import NOW, complete_artifacts

from eos_pv_helper import doctor, event_context, historical, plan_inspector


def forbidden(*args, **kwargs):
    raise AssertionError("Network forbidden in independent review")


socket.socket = forbidden
socket.create_connection = forbidden


def payloads(root):
    directory, settings, original = complete_artifacts(root)
    version = original["sync-report.json"]["event"]["version"]
    solution = original["solution-" + version + ".json"]
    solution["controls_start_at_now"] = True
    # Snapshot SoC is 55%, prices .0003 EUR/Wh, PV includes daylight.
    solution["parameters"] = saved(count=48)["parameters"]
    solution["parameters"]["pv_battery"].update(initial_soc_percentage=0, min_soc_percentage=0)
    solution["parameters"]["ems"]["electricity_price_per_wh"] = [.009] * 48
    files = {name: json.dumps(value).encode() for name, value in original.items()}
    manifest = {"schema_version": 2, "event_version": version,
        "captured_at_utc": NOW.isoformat(), "timezone": "Europe/Berlin",
        "configured_constraints_read": True, "validation_constraints": historical.limits(settings),
        "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}}
    observation = event_context.observed_options({})
    receipt = original["sync-report.json"]["event"].get("request_binding")
    request_sha = receipt["request_sha256"] if receipt else "a"*64
    manifest["producer"] = {"contract": "eos-pv-helper/automatic-evidence-v1",
        "observed_options": observation,
        "observed_options_sha256": event_context.canonical_sha(observation),
        "dispatched_request_sha256": request_sha,
        "solution_inputs": event_context.solution_inputs(solution)}
    return directory, version, manifest, files, solution


def run():
    results = []
    with tempfile.TemporaryDirectory(prefix="pr22-independent-review-") as temporary:
        root = Path(temporary)
        directory, version, manifest, files, solution = payloads(root)
        try:
            core = historical.validate(manifest, files, now=NOW + timedelta(days=1))
        except historical.ForecastError:
            core = {"accepted": False}
        path = root / "synthetic.zip"
        path.write_bytes(historical.pack(manifest, files))
        app, code = doctor.snapshot_acceptance(path, now=NOW + timedelta(days=1))
        results.append({"id": "R1", "criterion": "snapshot_matches_returned_solver_inputs",
            "status": "PASS" if not core["accepted"] and code == 1 and not app["accepted"] else "BLOCKED",
            "core_accepted": core["accepted"], "app_exit": code,
            "returned_model_inputs_present": manifest["producer"]["solution_inputs"]["selected_model_inputs_present"],
            "saved_soc_percent": 55, "returned_soc_percent": 0,
            "saved_price_eur_wh": .0003, "returned_price_eur_wh": .009,
            "returned_pv_all_zero_despite_nonzero_source": True})

        altered = copy.deepcopy(manifest)
        observation = event_context.observed_options({})
        altered["producer"] = {"contract": "eos-pv-helper/automatic-evidence-v1",
            "observed_options": observation,
            "observed_options_sha256": event_context.canonical_sha(observation),
            "dispatched_request_sha256": manifest["producer"]["dispatched_request_sha256"],
            "solution_inputs": event_context.solution_inputs(solution)}
        # Corrupt optional context, preserving its original hash. All consumers
        # must agree about the exact same archive bytes.
        altered["producer"]["observed_options"]["annual_load_kwh"] = 8000
        raw = historical.pack(altered, files)
        path.write_bytes(raw)
        try:
            core = historical.validate(altered, files, now=NOW + timedelta(days=1))
        except historical.ForecastError:
            core = {"accepted": False}
        app, code = doctor.snapshot_acceptance(path, now=NOW + timedelta(days=1))
        evidence_dir = directory / "genetic-evidence"
        evidence_dir.mkdir()
        (evidence_dir / (version + ".zip")).write_bytes(raw)
        claim = json.loads(files["sync-state.json"])["events"][version]
        view = plan_inspector.archived_inputs(directory, version, claim,
            files["solution-" + version + ".json"], NOW + timedelta(days=1))
        results.append({"id": "R2", "criterion": "same_archive_same_consumer_decision",
            "status": "PASS" if not core["accepted"] and code == 1 and view["status"] == "unproven" else "BLOCKED",
            "core_accepted": core["accepted"], "app_accepted": app["accepted"],
            "app_exit": code, "inspector_inputs_status": view["status"]})

    return {"counterexamples_from": "1282d77754d29f271e700ec700d52e13c625b75c",
        "validation_contract": historical.VALIDATION_CONTRACT,
        "tested_engine_sha256": hashlib.sha256(Path(historical.__file__).read_bytes().rstrip(b"\n")).hexdigest(),
        "synthetic_only": True, "network_forbidden": True, "optimizer_invoked": False,
        "productive_files_accessed": False, "criteria": results,
        "recommendation": "BLOCKED" if any(r["status"] == "BLOCKED" for r in results) else "PASS"}


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
    raise SystemExit(2 if result["recommendation"] == "BLOCKED" else 0)
