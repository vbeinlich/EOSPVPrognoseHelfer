"""Explicit isolated private review. No NAS/API access or historical claim creation."""

import argparse
import hashlib
import json
from datetime import timedelta
from pathlib import Path

from replay_worker_fixture import create

from eos_pv_helper import dashboard, replay_contract
from eos_pv_helper.replay_worker import Worker, isolation_guard, native_job
from eos_pv_helper.replay_worker_io import read, write


def review(originals, old_sidecar, destination):
    isolation_guard(originals)
    old_bytes = read(old_sidecar)
    historical = replay_contract.decode(old_bytes)
    wanted = {p["source_solution_sha256"]: p for p in historical["plans"]}
    before = {p.name: hashlib.sha256(read(p, 8_000_000)).hexdigest()
              for p in originals.glob("solution-*.json")}
    destination.mkdir(mode=0o700)
    source, workspace = destination / "copies", destination / "replays"
    source.mkdir(mode=0o700)
    workspace.mkdir(mode=0o700)
    copied = []
    for name, digest in before.items():
        if digest in wanted:
            raw = read(originals / name, 8_000_000)
            write(source / name, raw, immutable=True)
            copied.append((name, digest))
    assert {digest for _, digest in copied} == set(wanted)
    # Only a private test read-lock and EMPTY claim map are created in new copies.
    # These are never presented as historical successful execution evidence.
    (source / "sync.lock").touch()
    (source / "sync-state.json").write_text('{"events":{}}')
    worker = Worker(source, workspace)
    worker.import_sidecar(old_sidecar)
    measures = []
    for name, digest in copied:
        raw = read(source / name, 8_000_000)
        write(workspace / "pending" / (digest+".solution"), raw, immutable=True)
        lock_path = workspace / "state" / "private-native-review.lock"
        import fcntl

        with lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            metrics = native_job(workspace, digest, lock.fileno(), timeout=90,
                                 cpu_seconds=30, address_space_mb=3072)
        candidate = replay_contract.decode(read(workspace / "pending" / (digest+".json")))
        plan = replay_contract.validate(candidate["plans"][0], raw, json.loads(raw))
        old = wanted[digest]
        assert replay_contract.same_summary(plan["slots"], old["slots"])
        assert replay_contract.same_summary(plan["summary"], old["summary"])
        measures.append({k: metrics[k] for k in ("wall_seconds", "cpu_seconds", "max_rss_kib")})
    _, claimed, _ = create(source, day=28)
    clock = [claimed-timedelta(seconds=1)]
    worker = Worker(source, workspace, now=lambda: clock[0])
    worker.tick()
    clock[0] = claimed+timedelta(seconds=3)
    assert worker.tick()["counts"]["verified"] == 1
    assert len(worker.catalog.load()["plans"]) == len(wanted)+1
    site = destination / "site"
    site.mkdir(mode=0o700)
    assert dashboard.refresh(source, site, replay_file=workspace / "catalog.json")
    report = json.loads(dashboard.DATA_PATTERN.search((site / "index.html").read_text())[1])
    private_plans = [p for p in report["plans"] if p["solution_sha256"] in wanted]
    assert len(private_plans) == len(wanted)
    assert all(p["claim_status"] == "unmatched" for p in private_plans)
    assert old_sidecar.read_bytes() == old_bytes
    assert before == {p.name: hashlib.sha256(read(p, 8_000_000)).hexdigest()
                      for p in originals.glob("solution-*.json")}
    result = {"private_review": True, "originals_unchanged": True,
              "historical_sidecar_unchanged": True, "native_reproduced_plans": len(wanted),
              "historical_claims_not_upgraded": True,
              "automatic_synthetic_plan_added": True, "combined_catalog_plans": len(wanted)+1,
              "native_metrics": measures,
              "nas_archive_eligibility_tested": False}
    write(destination / "acceptance.json", replay_contract.canonical(result), immutable=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--originals", required=True, type=Path)
    parser.add_argument("--sidecar", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(review(args.originals, args.sidecar, args.destination)))
