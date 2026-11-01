"""Read-only acceptance of existing sync artifacts. No HTTP, state repair or dispatch."""

import hashlib
import json
import re
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from pathlib import Path

from .inputs import day_ahead_version, number
from .normalize import ForecastError, timestamp
from .sync import verify_solution

MAX_ARTIFACT_BYTES = 8_000_000


def _read(directory, name):
    path = directory / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ForecastError("Missing, unsafe or oversized acceptance artifact: " + name)
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_ARTIFACT_BYTES + 1)
        if len(raw) > MAX_ARTIFACT_BYTES:
            raise ForecastError("Oversized acceptance artifact: " + name)
        value = json.loads(raw)
    except (OSError, ValueError):
        raise ForecastError("Unreadable or invalid acceptance artifact: " + name) from None
    if not isinstance(value, dict):
        raise ForecastError("Acceptance artifact must be an object: " + name)
    return value, hashlib.sha256(raw).hexdigest()


@contextmanager
def _snapshot(directory):
    # The writer takes LOCK_EX for its complete cycle. Open the existing lock
    # read-only: even an empty output directory must remain completely unchanged.
    import fcntl

    path = directory / "sync.lock"
    if path.is_symlink() or not path.is_file():
        raise ForecastError("Unsafe sync lock")
    try:
        with path.open("rb") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ForecastError("Sync cycle in progress; retry Doctor later") from None
            yield
    except OSError:
        raise ForecastError("Sync lock is missing or not readable") from None


def acceptance(config, *, now=None, _reader=None):
    """Return sanitized evidence and exit status: 0 accepted, 2 waiting, 1 blocked.

    This is a point-in-time check, not permission to change EOS or close an issue.
    SHA256 values identify the inspected private artifacts without exposing them.
    """
    now = now or datetime.now(UTC)
    evidence = {"schema_version": 1, "checked_at_utc": now.isoformat(),
                "read_only": True, "accepted": False, "status": "blocked", "checks": {},
                "artifact_sha256": {}}
    checks = evidence["checks"]
    try:
        directory = Path(config.get("output", {}).get("directory", "/output"))
        with _snapshot(directory) if _reader is None else nullcontext():
            def read(name):
                value, digest = _read(directory, name) if _reader is None else _reader(name)
                evidence["artifact_sha256"][name] = digest
                return value

            report, state, prices = read("sync-report.json"), read("sync-state.json"), read("prices.json")
            age = (now - timestamp(report["checked_at_utc"])).total_seconds()
            checks["sync_recent"] = 0 <= age <= 450
            checks["write_mode"] = report.get("mode") == "write"
            checks["sync_no_errors"] = report.get("errors") == {}
            checks["imports_verified"] = all(report.get(key, {}).get("import_verified") is True
                                             for key in ("pv", "soc", "prices"))
            checks["pv_state_verified"] = state.get("pv_import_verified") is True
            control = report.get("prices", {}).get("control_coverage", {})
            checks["price_control_complete"] = (control.get("control_complete") is True
                and number(control.get("required_control_hours")) >= 24)
            soc = report.get("soc", {})
            proof = soc.get("freshness_evidence", {})
            checks["soc_usable"] = soc.get("usable") is True
            checks["soc_fresh"] = 0 <= (
                now - timestamp(soc.get("source_timestamp", ""))).total_seconds() <= min(
                    300, config.get("soc", {}).get("max_age_seconds", 300))
            checks["soc_proof"] = (soc.get("source") == "evcc"
                and soc.get("freshness_verified") is True
                and soc.get("timestamp_kind") == "successful_uncached_device_read_lower_bound"
                and proof.get("contract") ==
                    "evcc-0.318.1/e3dc-rscp/uncached-getters")
            checks["soc_proof_values_match"] = (
                0 <= number(soc.get("percent")) <= 100
                and number(soc.get("factor")) == number(soc.get("percent")) / 100
                and number(proof.get("live_soc_percent")) == number(soc.get("percent"))
                and abs(number(proof.get("live_power_w"))) <= number(
                    config.get("soc", {}).get("max_abs_power_w", 20000))
                and timestamp(soc.get("source_timestamp", "")) ==
                    timestamp(proof.get("read_started_at_utc", ""))
                and 0 <= (timestamp(proof.get("read_completed_at_utc", "")) -
                          timestamp(proof.get("read_started_at_utc", ""))).total_seconds() <= 15)
            events = state["events"]
            if not isinstance(events, dict):
                raise ForecastError("Invalid persisted event map")
            checks["no_uncertain_claims"] = all(
                isinstance(claim, dict) and claim.get("status") == "succeeded"
                for claim in events.values())
            event = report.get("event", {})
            evidence["event_status"] = event.get("status")
            if event.get("status") == "waiting-publication":
                try:
                    day_ahead_version(prices, timestamp(report["checked_at_utc"]),
                                      config.get("timezone", "Europe/Berlin"))
                except ForecastError:
                    checks["waiting_matches_price_snapshot"] = True
                else:
                    checks["waiting_matches_price_snapshot"] = False
                # Before publication a short control horizon is expected, but is
                # never accepted for dispatch or mistaken for a completed plan.
                ready = all(value for key, value in checks.items() if key != "price_control_complete")
                evidence["status"] = "waiting-publication" if ready else "blocked"
                return evidence, 2 if evidence["status"] == "waiting-publication" else 1
            version = event.get("version", "")
            if not isinstance(version, str) or not re.fullmatch(r"[0-9a-f]{64}", version):
                raise ForecastError("No valid automatic GENETIC event version")
            claim = events.get(version)
            if not isinstance(claim, dict):
                raise ForecastError("No persisted claim for the reported event")
            if claim.get("status") != "succeeded" or event.get("status") != "succeeded":
                raise ForecastError("Automatic dispatch not confirmed; never retry or delete its claim")
            expected_version = day_ahead_version(prices, timestamp(claim["claimed_at_utc"]),
                                                config.get("timezone", "Europe/Berlin"))
            checks["delivery_version_matches"] = all(
                claim.get(k) == event.get(k) == v for k, v in expected_version.items())
            checks["plan_matches_claim"] = all(claim.get(k) == event.get(k) for k in (
                "start_utc", "control_hours", "interval_seconds", "effective_tail_hours"))
            checks["control_24h"] = (number(claim["control_hours"]) == 24
                                     and claim["interval_seconds"] == 3600)
            start, claimed = timestamp(claim["start_utc"]), timestamp(claim["claimed_at_utc"])
            checks["claim_timing"] = 0 <= (claimed - start).total_seconds() < 3600 and claimed <= now
            solution = read("solution-" + version + ".json")
            verify_solution(solution, claim)
            checks["solution_content_valid"] = True
            evidence["plan"] = {"version": version, "delivery_day": claim["delivery_day"],
                "start_utc": claim["start_utc"], "claimed_at_utc": claim["claimed_at_utc"],
                "control_hours": claim["control_hours"], "interval_seconds": claim["interval_seconds"],
                "effective_tail_hours": claim["effective_tail_hours"],
                "total_costs": number(solution["result"]["total_costs"])}
            if config.get("evidence", {}).get("enabled") is True:
                from .evidence import inspect_archive
                try:
                    archived = inspect_archive(directory, config, version, claim,
                        evidence["artifact_sha256"]["solution-" + version + ".json"], lambda: now)
                except Exception:
                    checks["event_archive_verified"] = False
                    raise ForecastError("Event archive missing or invalid; never retry optimization or reconstruct old inputs") from None
                checks["event_archive_verified"] = archived["status"] == "archived"
                evidence["event_archive_sha256"] = archived["sha256"]
            evidence["accepted"] = all(checks.values())
            evidence["status"] = "accepted" if evidence["accepted"] else "blocked"
    except Exception as exc:
        # Never print raw JSON, paths from OS errors, configuration or secrets.
        evidence["reason"] = str(exc) if isinstance(exc, ForecastError) else "Invalid acceptance artifacts"
    return evidence, 0 if evidence["accepted"] else 1


def snapshot_acceptance(path, *, now=None):
    """Complete historical evidence at its persisted claim time; never live freshness.

    Hashes protect consistency, not authenticity. An operator must review capture
    provenance. No extraction, source config, token access or network calls.
    """
    from .historical import ForecastError as HistoricalError
    from .historical import manifest_digest, unpack, validate

    current = now or datetime.now(UTC)
    failure = {"schema_version": 1, "read_only": True, "accepted": False,
               "status": "blocked", "evidence_mode": "historical_snapshot",
               "current_freshness_verified": False}
    try:
        path = Path(path)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 60_000_000:
            raise ForecastError("Missing, unsafe or oversized private snapshot")
        with path.open("rb") as handle:
            raw = handle.read(60_000_001)
        manifest, files = unpack(raw)
        evidence = validate(manifest, files, now=current)
        evidence["capture_manifest_sha256"] = manifest_digest(raw)
        return evidence, 0
    except Exception as exc:
        failure["reason"] = str(exc) if isinstance(exc, (ForecastError, HistoricalError)) else "Invalid private snapshot; no files changed or extracted"
        return failure, 1
