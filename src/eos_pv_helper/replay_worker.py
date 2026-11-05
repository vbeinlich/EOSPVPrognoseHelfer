"""Discover committed original archives and publish isolated fixed-control replays."""

import argparse
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from . import economics, economics_native, historical
from . import replay_contract as contract
from .replay_worker_catalog import Catalog
from .replay_worker_io import WorkerError, directory, read, setup, sha, write

STATE_CONTRACT = "eos-pv-helper/replay-worker-state-v1"
VERSION = re.compile(r"[0-9a-f]{64}")
TRANSIENT = {"input_missing", "input_changed_during_read", "source_busy"}


def utcnow():
    return datetime.now(UTC)


def isolation_guard(source=None):
    """The deployed CLI refuses an accidentally privileged/connected execution."""
    status = Path("/proc/self/status").read_text()
    fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
    if (os.geteuid() == 0 or int(fields["CapEff"].strip(), 16) != 0
            or fields["NoNewPrivs"].strip() != "1"
            or not os.statvfs("/").f_flag & os.ST_RDONLY
            or {p.name for p in Path("/sys/class/net").iterdir()} != {"lo"}
            or source is not None and not os.statvfs(source).f_flag & os.ST_RDONLY
            or any(Path(p).exists() for p in ("/var/run/docker.sock", "/run/docker.sock"))):
        raise WorkerError("required_runtime_isolation_missing")


def object_json(raw):
    # Reuse the Doctor's duplicate-key, nonfinite-value and privacy guards.
    return historical.decode(raw)


@contextmanager
def source_lock(source):
    try:
        fd = os.open(source / "sync.lock", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as lock:
            import stat

            if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
                raise WorkerError("unsafe_source_lock")
            try:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                raise WorkerError("source_busy") from None
            yield
    except OSError:
        raise WorkerError("source_busy") from None


def snapshot(source, version, now):
    """Never consult current prices, forecasts, SoC, config, or HTTP endpoints."""
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise WorkerError("invalid_event_version")
    with source_lock(source):
        state = object_json(read(source / "sync-state.json", 8_000_000))
        claim = state.get("events", {}).get(version)
        if not isinstance(claim, dict) or claim.get("status") != "succeeded":
            raise WorkerError("claim_not_successful")
        report = object_json(read(source / "sync-report.json", 8_000_000))
        current_event = report.get("event", {})
        if current_event.get("version") == version and any(
            current_event.get(k) != claim.get(k) for k in (
                "status", "start_utc", "control_hours", "interval_seconds", "effective_tail_hours"
            )
        ):
            raise WorkerError("current_report_claim_conflict")
        raw = read(source / ("solution-" + version + ".json"), 8_000_000)
        archive_dir = source / "genetic-evidence"
        if not archive_dir.exists():
            raise WorkerError("input_missing")
        directory(archive_dir)
        archive = read(archive_dir / (version + ".zip"), historical.MAX_ZIP)
        try:
            manifest, files = historical.unpack(archive)
            saved_claim = object_json(files["sync-state.json"]).get("events", {}).get(version)
            if (manifest["event_version"] != version or saved_claim != claim
                    or files["solution-" + version + ".json"] != raw):
                raise WorkerError("archive_original_or_claim_conflict")
            evidence = historical.validate(manifest, files, now=now)
            if not (evidence["accepted"] and evidence["input_binding_complete"]
                    and evidence["validation_scope"] == "request_solver_inputs"
                    and all(evidence["checks"].values())
                    and manifest.get("producer", {}).get("contract") ==
                    "eos-pv-helper/automatic-evidence-v1"
                    and evidence["runtime_context"]["status"] ==
                    "consistent_observation_and_returned_inputs"):
                raise WorkerError("historical_binding_not_proven")
        except WorkerError:
            raise
        except Exception as exc:
            message = str(exc)
            reason = "archive_validation_failed"
            for fragment, code in (
                ("SHA256 mismatch", "archived_artifact_hash_mismatch"),
                ("incomplete", "historical_inputs_incomplete"),
                ("request", "historical_request_binding_invalid"),
                ("SoC", "historical_soc_binding_invalid"),
                ("PV", "historical_pv_binding_invalid"),
                ("price", "historical_price_binding_invalid"),
            ):
                if fragment in message:
                    reason = code
                    break
            raise WorkerError(reason) from None
        solution = object_json(raw)
        try:
            economics.project(solution)
        except Exception:
            raise WorkerError("unsupported_saved_inputs") from None
        return raw, {
            "event_version": version,
            "source_solution_sha256": sha(raw),
            "archive_sha256": sha(archive),
            "manifest_sha256": historical.manifest_digest(archive),
            "claim_sha256": contract.digest(claim),
            "artifact_sha256": evidence["artifact_sha256"],
            "validation_contract": historical.VALIDATION_CONTRACT,
            "validation_scope": evidence["validation_scope"],
            "input_binding_complete": True,
            "admission": "committed_original_archive",
        }


def signature(source, version, claim):
    result = [contract.digest(claim)]
    for path in (source / ("solution-" + version + ".json"),
                 source / "genetic-evidence" / (version + ".zip")):
        if path.is_symlink() or path.parent.is_symlink():
            raise WorkerError("unsafe_source_path")
        try:
            info = path.stat()
            result.append([info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns])
        except FileNotFoundError:
            result.append(None)
    return result


def native_job(root, source_hash, lock_fd, *, timeout, cpu_seconds, address_space_mb):
    args = [sys.executable, "-B", "-m", "eos_pv_helper.replay_worker_job",
            "--directory", str(root / "pending"), "--sha256", source_hash,
            "--timeout", str(timeout), "--cpu-seconds", str(cpu_seconds),
            "--address-space-mb", str(address_space_mb)]
    # Inheriting the same flock's open-file-description protects parent death too.
    child = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True,
                             pass_fds=(lock_fd,))
    try:
        code = child.wait(timeout=timeout + 5)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait()
        raise WorkerError("native_timeout") from None
    if code in (-signal.SIGALRM, -signal.SIGXCPU, -signal.SIGKILL):
        raise WorkerError("native_timeout_or_resource_limit")
    metrics_path = root / "pending" / (source_hash + ".metrics.json")
    if not metrics_path.exists():
        raise WorkerError("native_process_failed")
    metrics = object_json(read(metrics_path, 8192))
    allowed = {"verified", "native_dependency_unavailable", "native_source_mismatch",
               "native_result_or_flow_mismatch", "native_memory_limit", "native_io_or_resource_failure"}
    if metrics.get("reason") not in allowed or metrics.get("source_solution_sha256") != source_hash:
        raise WorkerError("native_metrics_invalid")
    if metrics["reason"] != "verified":
        raise WorkerError(metrics["reason"])
    if code != 0:
        raise WorkerError("native_process_failed")
    return metrics


class Worker:
    def __init__(self, source, workspace, *, now=utcnow, runner=native_job,
                 settle_seconds=2, retries=3, timeout=90, cpu_seconds=30,
                 address_space_mb=3072, max_jobs=1):
        self.source, self.root = setup(source, workspace)
        self.now, self.runner = now, runner
        self.settle_seconds, self.retries, self.timeout = settle_seconds, retries, timeout
        self.cpu_seconds, self.address_space_mb, self.max_jobs = cpu_seconds, address_space_mb, max_jobs
        self.catalog = Catalog(self.root)

    def save(self, state):
        write(self.root / "state" / "status.json", contract.canonical(contract.seal(state)))

    def state(self):
        path = self.root / "state" / "status.json"
        if not path.exists():
            return {"contract": STATE_CONTRACT, "automatic_since_utc": self.now().isoformat(),
                    "eos_revision": economics_native.EOS_REVISION, "jobs": {}, "observed": {}}
        value = object_json(read(path, 8_000_000))
        contract.check_seal(value)
        if (value.get("contract") != STATE_CONTRACT
                or value.get("eos_revision") != economics_native.EOS_REVISION
                or not isinstance(value.get("jobs"), dict)
                or not isinstance(value.get("observed"), dict)):
            raise WorkerError("worker_state_invalid")
        return {k: v for k, v in value.items() if k != "sha256"}

    def fail(self, job, reason, now):
        transient = reason in TRANSIENT
        job["reason"] = reason
        if transient and job["attempts"] < self.retries:
            job.update(status="retry_later", retry_at=now.timestamp() + min(
                3600, 60 * 2 ** (job["attempts"] - 1)))
        else:
            job.update(status="rejected", retry_at=None)
            if transient:
                job["reason"] = "incomplete_archive_retry_exhausted"
        if job["status"] == "rejected":
            key = contract.digest({k: job[k] for k in ("version", "signature")})
            path = self.root / "rejected" / (key + ".json")
            if not path.exists():
                write(path, contract.canonical(contract.seal(job)), immutable=True)

    def tick(self, *, version=None):
        lock_path = self.root / "state" / "worker.lock"
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"status": "running", "reason": "worker_lock_busy"}
            return self._tick(lock.fileno(), version)

    def import_sidecar(self, path):
        """Explicit operator import proves model reproducibility, never execution."""
        value = contract.decode(read(path, contract.MAX_BYTES))
        wanted = {p["source_solution_sha256"]: p for p in value["plans"]}
        matches, budget = {}, 0
        with source_lock(self.source):
            for count, source in enumerate(sorted(self.source.glob("solution-*.json"))):
                if count >= 4096:
                    raise WorkerError("import_source_budget_exceeded")
                version = source.name[len("solution-"):-len(".json")]
                if not VERSION.fullmatch(version):
                    continue
                raw = read(source, 8_000_000)
                budget += len(raw)
                if budget > 256_000_000:
                    raise WorkerError("import_source_budget_exceeded")
                source_hash = sha(raw)
                if source_hash in wanted:
                    if source_hash in matches:
                        raise WorkerError("import_source_ambiguous")
                    contract.validate(wanted[source_hash], raw, object_json(raw))
                    matches[source_hash] = version
        if set(matches) != set(wanted):
            raise WorkerError("import_original_not_found")
        fd = os.open(self.root / "state" / "worker.lock",
                     os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise WorkerError("worker_lock_busy") from None
            self.catalog.load()
            for source_hash, plan in wanted.items():
                self.catalog.add(contract.canonical(contract.catalog([plan])), {
                    "event_version": matches[source_hash],
                    "source_solution_sha256": source_hash,
                    "admission": "explicit_import_native_model_only",
                    "import_file_sha256": sha(read(path, contract.MAX_BYTES)),
                    "validation_scope": "native_model_reproducibility_only",
                    "input_binding_complete": False,
                }, {"imported": True, "native_executed_by_worker": False})
        return {"status": "verified", "imported_plans": len(wanted),
                "historical_execution_proven": False}

    def _tick(self, lock_fd, selected):
        state, now = self.state(), self.now()
        state["checked_at_utc"] = now.isoformat()
        current_jobs = state.setdefault("current_jobs", {})
        prior_catalog = self.catalog.load()  # Never silently repair corrupt catalog data.
        verified_hashes = set(prior_catalog["worker_catalog"]["entries"]) if prior_catalog else set()
        self.save(state)  # Persist the activation watermark even without source input.
        with source_lock(self.source):
            current = object_json(read(self.source / "sync-state.json", 8_000_000))
            events = current.get("events", {})
            if not isinstance(events, dict) or len(events) > 4096:
                raise WorkerError("claim_budget_or_structure_invalid")
            selected_events = {selected: events.get(selected)} if selected else events
            candidates = []
            for version, claim in sorted(selected_events.items()):
                if not VERSION.fullmatch(version or ""):
                    raise WorkerError("invalid_event_version")
                if not isinstance(claim, dict):
                    if selected:
                        raise WorkerError("selected_claim_missing")
                    continue
                try:
                    claimed = historical.timestamp(claim.get("claimed_at_utc"))
                except Exception:
                    if selected:
                        raise WorkerError("claim_time_invalid") from None
                    continue
                if not selected and claimed < historical.timestamp(state["automatic_since_utc"]):
                    continue
                sig = signature(self.source, version, claim)
                observed = state["observed"].get(version)
                if not observed or observed["signature"] != sig:
                    observed = {"signature": sig, "seen_at": now.timestamp()}
                    state["observed"][version] = observed
                key = contract.digest({"version": version, "signature": sig})
                current_jobs[version] = key
                job = state["jobs"].setdefault(key, {
                    "version": version, "signature": sig, "source_solution_sha256": None,
                    "status": "pending", "reason": "awaiting_stable_archive", "attempts": 0,
                    "eos_revision": economics_native.EOS_REVISION, "replay_duration_seconds": None,
                })
                if job["status"] in ("verified", "rejected"):
                    continue
                if job.get("retry_at", 0) and job["retry_at"] > now.timestamp():
                    continue
                if now.timestamp() - observed["seen_at"] < self.settle_seconds:
                    continue
                source_hash = job.get("source_solution_sha256")
                completed = (isinstance(source_hash, str) and VERSION.fullmatch(source_hash)
                             and (self.root / "pending" / (source_hash+".json")).exists())
                if (job["status"] == "running" and job["attempts"] >= self.retries
                        and not completed and source_hash not in verified_hashes):
                    self.fail(job, "interrupted_native_retry_exhausted", now)
                    continue
                candidates.append(job)
        self.save(state)
        for job in candidates[:self.max_jobs]:
            job["attempts"] += 1
            started = time.monotonic()
            try:
                job["source_solution_sha256"] = sha(read(
                    self.source / ("solution-" + job["version"] + ".json"), 8_000_000))
                raw, binding = snapshot(self.source, job["version"], now)
                source_hash = binding["source_solution_sha256"]
                job.update(source_solution_sha256=source_hash, status="running", reason="native_replay")
                self.save(state)
                candidate_path = self.root / "pending" / (source_hash + ".json")
                catalog = self.catalog.load()
                if catalog and source_hash in catalog["worker_catalog"]["entries"]:
                    receipt = object_json(read(self.root / "receipts" / (source_hash + ".json")))
                    if any(receipt.get(k) != v for k, v in binding.items()):
                        raise WorkerError("verified_original_binding_conflict")
                    job["replay_duration_seconds"] = receipt.get("metrics", {}).get("wall_seconds")
                else:
                    write(self.root / "pending" / (source_hash + ".solution"), raw, immutable=True)
                    if candidate_path.exists():
                        metrics = object_json(read(self.root / "pending" / (source_hash + ".metrics.json"), 8192))
                    else:
                        metrics = self.runner(self.root, source_hash, lock_fd, timeout=self.timeout,
                                              cpu_seconds=self.cpu_seconds,
                                              address_space_mb=self.address_space_mb)
                    job["replay_duration_seconds"] = metrics.get("wall_seconds")
                    candidate = read(candidate_path)
                    plans = contract.decode(candidate)["plans"]
                    if len(plans) != 1:
                        raise WorkerError("candidate_not_single_plan")
                    contract.validate(plans[0], raw, object_json(raw))
                    if snapshot(self.source, job["version"], self.now())[1] != binding:
                        raise WorkerError("original_changed_before_publication")
                    self.catalog.add(candidate, binding, metrics)
                job.update(status="verified", reason="verified", retry_at=None)
            except WorkerError as exc:
                self.fail(job, str(exc), now)
            except Exception:
                self.fail(job, "validation_or_resource_failure", now)
            job["processing_duration_seconds"] = round(time.monotonic() - started, 6)
            self.save(state)
        return {"status": "idle", "counts": {
            name: sum(state["jobs"][key]["status"] == name for key in current_jobs.values())
            for name in ("pending", "running", "verified", "rejected", "retry_later")
        }}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="/archive")
    parser.add_argument("--workspace", default="/replays")
    parser.add_argument("--version", help="Explicit historical version; never bypasses admission")
    parser.add_argument("--import-sidecar", help="Explicit immutable historical native-model proof")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--settle-seconds", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--cpu-seconds", type=int, default=30)
    parser.add_argument("--address-space-mb", type=int, default=3072)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()
    if args.import_sidecar and (args.version or args.watch):
        parser.error("sidecar import cannot select a native run or watch mode")
    if not (15 <= args.poll_seconds <= 3600 and 1 <= args.settle_seconds <= 300
            and 1 <= args.timeout <= 300 and 1 <= args.cpu_seconds <= 120
            and 512 <= args.address_space_mb <= 4096 and 1 <= args.retries <= 5):
        parser.error("resource limits outside supported bounds")
    try:
        isolation_guard(Path(args.source))
        os.nice(10)
    except Exception:
        print('{"status":"blocked","reason":"required_runtime_isolation_missing"}')
        return 2
    worker = Worker(Path(args.source), Path(args.workspace), settle_seconds=args.settle_seconds,
                    timeout=args.timeout, retries=args.retries, cpu_seconds=args.cpu_seconds,
                    address_space_mb=args.address_space_mb)
    while True:
        try:
            result = (worker.import_sidecar(Path(args.import_sidecar)) if args.import_sidecar
                      else worker.tick(version=args.version))
            print(json.dumps(result), flush=True)
        except Exception:
            print(json.dumps({"status": "blocked", "reason": "source_state_or_catalog_invalid"}),
                  flush=True)
            if not args.watch:
                return 2
        if not args.watch:
            return 0
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
