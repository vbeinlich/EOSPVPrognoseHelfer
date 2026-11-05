"""Offline gates for the manually executed test installation. No requests or search."""

import fcntl
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


def require(value):
    if not value:
        raise ValueError("offline_gate_failed")


def runtime(value):
    old, new = value["old"][0], value["new"][0]
    require(new["State"]["Running"])
    for key in ("User", "Entrypoint", "Cmd", "WorkingDir", "Healthcheck", "StopSignal"):
        require(old["Config"].get(key) == new["Config"].get(key))
    require((old["Config"].get("Labels") or {}).items() <= (new["Config"].get("Labels") or {}).items())
    def env(info):
        return dict(row.split("=", 1) for row in info["Config"].get("Env", []))
    require(env(old).items() <= env(new).items())
    for key in ("ReadonlyRootfs", "Privileged", "CapAdd", "CapDrop", "SecurityOpt", "Devices",
                "DeviceRequests", "Memory", "MemorySwap", "NanoCpus", "CpuPeriod", "CpuQuota",
                "CpuShares", "CpusetCpus", "PidsLimit", "RestartPolicy", "NetworkMode", "PortBindings",
                "ExtraHosts", "Dns", "Tmpfs", "LogConfig", "Ulimits", "Sysctls"):
        require(old["HostConfig"].get(key) == new["HostConfig"].get(key))
    def mounts(info):
        return sorted((m["Type"], m["Source"], m["Destination"], m["RW"], m.get("Propagation", ""))
                      for m in info["Mounts"])
    require(mounts(old) == mounts(new))
    return {"running": True, "original_command_env_mounts_and_limits_preserved": True,
            "health": new["State"].get("Health", {}).get("Status", "not_configured")}


def archive(root=Path("/archive"), backup=Path("/migration")):
    from eos_pv_helper import evidence, historical
    from eos_pv_helper.replay_worker import snapshot

    now = datetime.now(UTC)
    before = historical.decode((backup / "claims-before.json").read_bytes())
    installed = historical.timestamp((backup / "installed-at-utc").read_text().strip())
    state = historical.decode((root / "sync-state.json").read_bytes())
    candidates = [(c["claimed_at_utc"], v) for v, c in state["events"].items()
                  if v not in before["events"] and c.get("status") == "succeeded"
                  and historical.timestamp(c["claimed_at_utc"]) >= installed
                  and (root / "genetic-evidence" / (v+".zip")).is_file()]
    require(candidates)
    version = max(candidates)[1]
    raw, binding = snapshot(root, version, now)
    original = root / ("solution-"+version+".json")
    require(original.read_bytes() == raw)
    committed = root / "genetic-evidence" / (version+".zip")
    manifest, files = historical.unpack(committed.read_bytes())
    claim = historical.decode(files["sync-state.json"])["events"][version]
    require(historical.timestamp(claim["claimed_at_utc"]) >= historical.timestamp(
        (backup / "installed-at-utc").read_text().strip()))
    require(len(files) == 7 and committed.stat().st_mode & 0o777 == 0o400)
    admitted = evidence.inspect_archive(root, {}, version, claim, binding["source_solution_sha256"], lambda: now)
    require(admitted["replay_admission"]["status"] == "ready_for_native_replay")
    return {"status": "archive_accepted", "version": version,
            "source_solution_sha256": binding["source_solution_sha256"],
            "archive_sha256": binding["archive_sha256"], "artifacts": 7,
            "network_requests": 0, "optimizer_searches": 0}


def worker(root=Path("/replays"), source=Path("/archive"), backup=Path("/migration")):
    from eos_pv_helper import historical, replay_contract
    from eos_pv_helper.replay_worker import snapshot
    from eos_pv_helper.replay_worker_catalog import Catalog

    expected = json.loads((backup / "archive-accepted.json").read_bytes())
    raw, binding = snapshot(source, expected["version"], datetime.now(UTC))
    require(binding["archive_sha256"] == expected["archive_sha256"])
    catalog = Catalog(root).load()
    require(catalog)
    plan = next(p for p in catalog["plans"] if p["source_solution_sha256"] == expected["source_solution_sha256"])
    replay_contract.validate(plan, raw, historical.decode(raw))
    return {"status": "worker_accepted", "version": expected["version"],
            "source_solution_sha256": expected["source_solution_sha256"],
            "catalog_plans": len(catalog["plans"]), "native_flows_verified": True}


def init_worker(root=Path("/replays"), source=Path("/archive"), backup=Path("/migration")):
    from eos_pv_helper.replay_worker import Worker

    installed = datetime.fromisoformat((backup / "installed-at-utc").read_text().strip())
    worker = Worker(source, root, now=lambda: installed)
    fd = os.open(root / "state/worker.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = worker.state()
        if not (root / "state/status.json").exists():
            worker.save(state)
    return {"status": "worker_state_ready", "automatic_since_utc": state["automatic_since_utc"]}


def main():
    try:
        mode = sys.argv[1]
        result = {"runtime": lambda: runtime(json.load(sys.stdin)), "archive": archive,
                  "worker": worker, "init-worker": init_worker}[mode]()
        print(json.dumps(result))
    except Exception:
        raise SystemExit("Offline gate not passed; no additional dispatch or device action attempted") from None


if __name__ == "__main__":
    main()
