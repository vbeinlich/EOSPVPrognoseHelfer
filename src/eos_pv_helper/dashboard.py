"""Offline EMS dashboard: existing files in, one atomically replaced HTML file out."""

import argparse
import fcntl
import hashlib
import heapq
import json
import math
import os
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import economics, replay_contract
from . import plan_inspector as inspector

MAX_PLANS = 4096
FLOW_KEYS = (
    "battery_charge_dc_wh_per_hour",
    "battery_discharge_dc_wh_per_hour",
    "battery_pv_charge_dc_wh_per_hour",
    "battery_grid_charge_dc_wh_per_hour",
)
DATA_PATTERN = re.compile(
    r'<script id="dashboard-data" type="application/json">(.*?)</script>', re.S
)


def finite(value):
    return inspector.numeric(value)


def flows(solution, count, start, seconds):
    """Only an explicit stored DC-energy contract can establish a source split."""
    result = solution.get("result", {})
    missing = [
        {
            "charge_wh": None,
            "discharge_wh": None,
            "pv_wh": None,
            "grid_wh": None,
            "unknown_wh": None,
            "proof": "unavailable",
        }
        for _ in range(count)
    ]
    if (
        result.get("battery_flow_energy_basis") != "battery_dc"
        or result.get("battery_flow_interval_seconds") != seconds
        or inspector.stamp(result.get("battery_flow_start_utc")) != start
    ):
        return missing
    charge, discharge, pv, grid = [result.get(k) for k in FLOW_KEYS]
    if not all(isinstance(a, list) and len(a) == count for a in (charge, discharge)):
        raise inspector.InspectorError("Gespeicherte Batterieflussdaten sind unvollständig.")
    split = pv is not None or grid is not None
    if split and not all(isinstance(a, list) and len(a) == count for a in (pv, grid)):
        raise inspector.InspectorError("Gespeicherter Herkunftsnachweis ist unvollständig.")
    output = []
    for i in range(count):
        c, d = finite(charge[i]), finite(discharge[i])
        p, g = (finite(pv[i]), finite(grid[i])) if split else (None, None)
        if c is None or d is None or min(c, d) < 0:
            raise inspector.InspectorError("Gespeicherte Batterieenergie ist ungültig.")
        if split and (p is None or g is None or min(p, g) < 0 or p + g > c + 1e-6):
            raise inspector.InspectorError("Gespeicherte Energieherkunft ist widersprüchlich.")
        output.append(
            {
                "charge_wh": c,
                "discharge_wh": d,
                "pv_wh": p,
                "grid_wh": g,
                "unknown_wh": max(0, c - (p or 0) - (g or 0)),
                "proof": "stored_source_split" if split else "stored_total_only",
            }
        )
    return output


def saved_comparison(plan, solution, cached):
    """Bind an explicitly supplied, previously computed offline report to original bytes."""
    unavailable = {"status": "unavailable", "advantage_eur": None}
    if not cached:
        return unavailable
    try:
        from .economics_native import EOS_REVISION, EXPECTED_SOURCE

        data = economics.project(solution)
        other = next(p for p in cached["plans"] if p["solution_sha256"] == plan["solution_sha256"])
        c = other["comparison"]
        if (
            c["status"] != "calculated"
            or c["replay_verified"] is not True
            or c["input_sha256"] != economics.digest(data)
            or c["engine"]["source_sha256"] != EXPECTED_SOURCE
            or c["engine"]["expected_source_revision"] != EOS_REVISION
            or c["engine"]["optimizer_invoked"] is not False
            or c["terminal_method"] != "identical_saved_curve"
        ):
            return unavailable
        for scenario in ("genetic", "baseline"):
            slots = c["slots"][scenario]
            if len(slots) != data["control_slots"]:
                return unavailable
            for i, slot in enumerate(slots):
                expected = inspector.stamp(data["start_utc"]) + timedelta(
                    seconds=i * data["interval_seconds"]
                )
                if (
                    inspector.stamp(slot["start_utc"]) != expected
                    or slot["interval_seconds"] != data["interval_seconds"]
                ):
                    return unavailable
                for key in (
                    "pv_wh",
                    "load_wh",
                    "price_eur_kwh",
                    "losses_wh",
                    "grid_import_wh",
                    "grid_export_wh",
                    "grid_cost_eur",
                    "wear_eur",
                    "feed_in_revenue_eur",
                    "soc_start_percent",
                    "soc_end_percent",
                ):
                    economics.number(slot[key])
                if min(slot["grid_import_wh"], slot["grid_export_wh"], slot["wear_eur"]) < 0:
                    return unavailable
                if any(
                    not math.isclose(slot[k], data["series"][original][i], abs_tol=1e-7)
                    for k, original in (("pv_wh", "pv_forecast_wh"), ("load_wh", "total_load"))
                ):
                    return unavailable
                if scenario == "genetic":
                    checks = (
                        (slot["grid_import_wh"], "grid_consumption_wh_per_hour"),
                        (slot["grid_export_wh"], "grid_feed_in_wh_per_hour"),
                        (slot["soc_start_percent"], "battery_soc_per_hour"),
                        (slot["grid_cost_eur"] + slot["wear_eur"], "costs_per_hour"),
                        (slot["feed_in_revenue_eur"], "revenue_per_hour"),
                        (slot["losses_wh"], "losses_per_hour"),
                    )
                    if any(
                        not math.isclose(value, data["expected"][key][i], abs_tol=1e-7)
                        for value, key in checks
                    ):
                        return unavailable
                if not math.isclose(
                    slot["grid_cost_eur"],
                    slot["grid_import_wh"] * data["series"]["electricity_price_per_wh"][i],
                    abs_tol=1e-7,
                ):
                    return unavailable
            if not math.isclose(
                slots[0]["soc_start_percent"],
                data["battery"]["initial_soc_percentage"],
                abs_tol=1e-7,
            ):
                return unavailable
            account = c[scenario]
            end = (
                (slots[-1]["soc_end_percent"] - data["battery"]["min_soc_percentage"])
                / 100
                * data["battery"]["capacity_wh"]
                * data["battery"]["discharging_efficiency"]
                * data["inverter"]["dc_to_ac_efficiency"]
            )
            credit = economics.terminal_value(data["terminal_curve"], end)
            adjusted = (
                sum(s["grid_cost_eur"] + s["wear_eur"] - s["feed_in_revenue_eur"] for s in slots)
                - credit
            )
            if not math.isclose(adjusted, account["adjusted_cost_eur"], abs_tol=1e-7):
                return unavailable
        advantage = c["baseline"]["adjusted_cost_eur"] - c["genetic"]["adjusted_cost_eur"]
        if not math.isclose(advantage, c["additional_savings_eur"], abs_tol=1e-7):
            return unavailable
        return {
            "status": "cached_native_replay",
            "advantage_eur": advantage,
            "baseline_eur": c["baseline"]["adjusted_cost_eur"],
            "genetic_eur": c["genetic"]["adjusted_cost_eur"],
            "input_sha256": c["input_sha256"],
            "historical_binding": plan["inputs"]["status"],
        }
    except (KeyError, TypeError, ValueError, StopIteration):
        return unavailable


def enrich(plan, solution, cached=None, *, replays=None, original_raw=None):
    start, seconds = inspector.stamp(plan.get("start_utc")), plan.get("interval_seconds")
    count = plan["source_slots"]
    for key in ("ac_charge", "dc_charge", "discharge_allowed"):
        values = solution.get(key)
        if (
            not isinstance(values, list)
            or len(values) != count
            or any(
                inspector.numeric(v, "flag" if key == "discharge_allowed" else "factor") is None
                for v in values
            )
        ):
            raise inspector.InspectorError("Originale Steuerarrays sind beschädigt.")
    flow = flows(solution, count, start, seconds)
    sidecar = replay_contract.find(replays, plan["solution_sha256"])
    if sidecar is not None:
        if original_raw is None:
            raise replay_contract.ReplayError("Originalbytes für Replay-Prüfung fehlen.")
        replay_contract.validate(sidecar, original_raw, solution)
        flow = [
            {
                "charge_wh": s["charge_internal_wh"],
                "pv_wh": s["pv_charge_internal_wh"],
                "grid_wh": s["grid_charge_internal_wh"],
                "discharge_wh": s["discharge_internal_wh"],
                "unknown_wh": 0,
                "internal_discharge_wh": s["discharge_internal_wh"],
                "proof": replay_contract.PROOF,
                "energy_basis": replay_contract.BASIS,
                "original_replay_values": s,
            }
            for s in sidecar["slots"]
        ]
        plan["flow_replay"] = {
            "status": "verified",
            "sha256": sidecar["sha256"],
            "proof": sidecar["proof"],
            "energy_basis": sidecar["energy_basis"],
            "summary": sidecar["summary"],
        }
    params = solution.get("parameters", {})
    ems = params.get("ems", {}) if isinstance(params, dict) else {}
    battery = params.get("pv_battery", {}) if isinstance(params, dict) else {}
    capacity = None
    try:
        capacity = (
            economics.number(battery["capacity_wh"])
            * (
                economics.number(battery["max_soc_percentage"])
                - economics.number(battery["min_soc_percentage"])
            )
            / 100
        )
        if capacity <= 0:
            capacity = None
    except (KeyError, TypeError, ValueError):
        pass
    # Stored solver inputs, explicitly distinguished from independently bound historical archives.
    series = {}
    if (
        solution.get("controls_start_at_now") is True
        and params.get("forecast_interval_seconds") == seconds
    ):
        for key in ("pv_forecast_wh", "total_load", "electricity_price_per_wh"):
            values = ems.get(key)
            if isinstance(values, list) and count <= len(values) <= inspector.MAX_SLOTS:
                series[key] = [finite(v) for v in values[:count]]
    for i, row in enumerate(plan["rows"]):
        row.pop("quarters", None)
        row["flow"] = flow[i]
        row["usable_capacity_wh"] = capacity
        row["forecast"] = {k: a[i] for k, a in series.items()}
        row["forecast_proof"] = (
            (
                "request_solver_bound"
                if plan["inputs"]["status"] == "verified"
                else "stored_solver_input_only"
            )
            if series
            else "unavailable"
        )
    plan["model_comparison"] = saved_comparison(plan, solution, cached)
    return plan


def collect(
    source,
    *,
    now=None,
    economics_file=None,
    legacy_timezone=None,
    cached=None,
    replays=None,
    replay_file=None,
):
    root = Path(source).resolve(strict=True)
    now = now or datetime.now(UTC)
    if economics_file:
        path = Path(economics_file)
        cached = inspector.obj(inspector.read(path.parent, path.name, 32_000_000))
    replays = load_replays(replays, replay_file)
    # Outer shared lock spans Inspector and enrichment; it uses the SAME existing lock as the writer.
    lock_path = root / "sync.lock"
    if lock_path.is_symlink() or not lock_path.is_file():
        raise inspector.InspectorError("Vorhandenes sicheres sync.lock fehlt.")
    with lock_path.open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        events = inspector.obj(inspector.read(root, "sync-state.json")).get("events", {})
        if not isinstance(events, dict):
            raise inspector.InspectorError("Claimdatei ist ungültig.")
        starts = [
            inspector.stamp(c.get("start_utc"))
            for c in events.values()
            if isinstance(c, dict)
            and c.get("status") == "succeeded"
            and inspector.stamp(c.get("start_utc"))
        ]
        cutoff = max(starts) - timedelta(days=37) if starts else None
        report = inspector.collect(
            root,
            now=now,
            legacy_timezone=legacy_timezone,
            max_plans=MAX_PLANS,
            max_bytes=256_000_000,
            since=cutoff,
        )
        if report["warnings"] or report["latest_sync_status"] == "unknown":
            raise inspector.InspectorError("Status- oder Claimdatei ist nicht gültig lesbar.")
        for plan in report["plans"]:
            if plan["solution_status"] != "readable":
                raise inspector.InspectorError("Ein gespeicherter Plan ist nicht gültig lesbar.")
            raw = inspector.read(root, plan["file"])
            if hashlib.sha256(raw).hexdigest() != plan["solution_sha256"]:
                raise inspector.InspectorError("Plan wurde während des Lesens geändert.")
            archive = root / "genetic-evidence" / (plan["version"] + ".zip")
            if (archive.exists() or archive.is_symlink()) and plan["inputs"][
                "status"
            ] == "unproven":
                raise inspector.InspectorError("Vorhandener historischer Nachweis ist beschädigt.")
            solution = inspector.obj(raw)
            enrich(plan, solution, cached, replays=replays, original_raw=raw)
            plan["synthetic_only"] = solution.get("synthetic_only") is True
    report.update(
        dashboard_schema=1,
        checked_at_utc=now.isoformat(),
        update_error=False,
        exact_solver_options_proven=False,
        synthetic_only=bool(report["plans"])
        and all(p.get("synthetic_only") for p in report["plans"]),
    )
    return report


def timeline(plans, days, *, end=None, model_coverage=False):
    """Latest successful plan known at each instant wins. No future plan and no double counting."""
    successful = [
        p
        for p in plans
        if p.get("start_utc")
        and (
            p.get("flow_replay", {}).get("status") == "verified"
            if model_coverage
            else p.get("claim_status") == "succeeded"
        )
    ]
    if not successful:
        return []
    anchor = max(inspector.stamp(p["start_utc"]) for p in successful)
    right = end or anchor + timedelta(hours=24)
    left = right - timedelta(days=days)
    candidates, boundaries = [], {left, right}
    for plan in successful:
        issued = max(
            inspector.stamp(plan["start_utc"]),
            inspector.stamp(plan["start_utc"])
            if model_coverage
            else inspector.stamp(plan.get("claimed_at_utc")) or inspector.stamp(plan["start_utc"]),
        )
        for row in plan["rows"]:
            a, b = inspector.stamp(row["start_utc"]), inspector.stamp(row["end_utc"])
            if (
                (
                    row["phase"] != "control"
                    and not (model_coverage and row["phase"] == "undeclared")
                )
                or not a
                or not b
                or b <= left
                or a >= right
            ):
                continue
            a = max(a, issued, left)
            b = min(b, right)
            if a < b:
                candidates.append((a, b, issued, plan["version"], row))
                boundaries.update((a, b))
    output, active, arrivals = [], [], {}
    for index, candidate in enumerate(candidates):
        a, b, issued, version, row = candidate
        arrivals.setdefault(a, []).append((-issued.timestamp(), -int(version, 16), index, b, row))
    points = sorted(boundaries)
    for a, b in zip(points, points[1:]):
        for candidate in arrivals.get(a, []):
            heapq.heappush(active, candidate)
        while active and active[0][3] <= a:
            heapq.heappop(active)
        if not active:
            output.append({"start_utc": a.isoformat(), "end_utc": b.isoformat(), "gap": True})
            continue
        _, _, index, _, row = active[0]
        version = candidates[index][3]
        fraction = (b - a).total_seconds() / (
            inspector.stamp(row["end_utc"]) - inspector.stamp(row["start_utc"])
        ).total_seconds()
        output.append(
            {
                "start_utc": a.isoformat(),
                "end_utc": b.isoformat(),
                "version": version,
                "source_index": row["source_index"],
                "fraction": fraction,
                "flow": {
                    k: (
                        v * fraction
                        if isinstance(v, (int, float)) and not isinstance(v, bool)
                        else v
                    )
                    for k, v in row["flow"].items()
                },
                "grid_wh": None
                if row["model"].get("grid_consumption_wh_per_hour") is None
                else row["model"]["grid_consumption_wh_per_hour"] * fraction,
            }
        )
    return output


def prepare(report):
    report["ranges"] = {str(days): timeline(report["plans"], days) for days in (1, 7, 30)}
    report["model_ranges"] = {
        str(days): timeline(report["plans"], days, model_coverage=True) for days in (1, 7, 30)
    }
    return report


def load_replays(value=None, filename=None):
    if filename:
        path = Path(filename)
        return replay_contract.decode(
            inspector.read(path.parent, path.name, replay_contract.MAX_BYTES)
        )
    return replay_contract.decode(replay_contract.canonical(value)) if value is not None else None


def collect_originals(paths, *, replay_file=None, replays=None):
    """Private saved responses without inventing sync-state or successful claims."""
    replays = load_replays(replays, replay_file)
    now = datetime.now(UTC)
    plans = []
    for filename in paths:
        path = Path(filename)
        raw = inspector.read(path.parent, path.name)
        version = hashlib.sha256(raw).hexdigest()
        plan = inspector.parse_plan(
            None,
            version,
            raw,
            None,
            __import__("zoneinfo").ZoneInfo("Europe/Berlin"),
            None,
            now,
            archive_lookup=False,
        )
        solution = inspector.obj(raw)
        enrich(plan, solution, replays=replays, original_raw=raw)
        plan["synthetic_only"] = solution.get("synthetic_only") is True
        plans.append(plan)
    if len({p["version"] for p in plans}) != len(plans):
        raise inspector.InspectorError("Doppelte Originallösung.")
    plans.sort(key=lambda p: p["start_utc"] or "", reverse=True)
    return {
        "dashboard_schema": 1,
        "read_only": True,
        "plans": plans,
        "generated_at_utc": now.isoformat(),
        "checked_at_utc": now.isoformat(),
        "latest_sync_status": "unknown",
        "synthetic_only": bool(plans) and all(p.get("synthetic_only") for p in plans),
        "update_error": False,
        "exact_solver_options_proven": False,
    }


def atomic_write(path, raw):
    descriptor, temporary = tempfile.mkstemp(prefix=".ems-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def refresh(
    source,
    destination,
    *,
    economics_file=None,
    legacy_timezone=None,
    cached=None,
    replays=None,
    replay_file=None,
    solutions=None,
):
    root = Path(source).resolve(strict=True) if source else None
    output = Path(destination).resolve(strict=True)
    if root and (root == output or root in output.parents or output in root.parents):
        raise inspector.InspectorError("Dashboard-Ziel muss von den Originaldaten getrennt sein.")
    target = output / "index.html"
    if target.is_symlink() or (output / ".refresh.lock").is_symlink():
        raise inspector.InspectorError("Unsicheres Dashboard-Ziel.")
    with (output / ".refresh.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        previous = ""
        if target.is_file():
            previous = inspector.read(output, "index.html", 128_000_000).decode("utf-8")
        html, valid = render_refresh(
            root,
            previous,
            economics_file=economics_file,
            legacy_timezone=legacy_timezone,
            cached=cached,
            replays=replays,
            replay_file=replay_file,
            solutions=solutions,
        )
        atomic_write(target, html.encode("utf-8"))
        return valid


def render_refresh(
    source,
    previous="",
    *,
    economics_file=None,
    legacy_timezone=None,
    cached=None,
    replays=None,
    replay_file=None,
    solutions=None,
):
    from .dashboard_view import render

    valid = True
    try:
        report = prepare(
            collect_originals(solutions, replays=replays, replay_file=replay_file)
            if solutions
            else collect(
                source,
                economics_file=economics_file,
                legacy_timezone=legacy_timezone,
                cached=cached,
                replays=replays,
                replay_file=replay_file,
            )
        )
    except Exception:
        valid = False
        report = {
            "dashboard_schema": 1,
            "plans": [],
            "ranges": {},
            "generated_at_utc": None,
            "checked_at_utc": None,
            "latest_sync_status": "unknown",
        }
        try:
            candidate = json.loads(DATA_PATTERN.search(previous)[1])
            if candidate.get("dashboard_schema") == 1:
                report = candidate
        except (TypeError, ValueError):
            pass
        report["update_error"] = True
    return render(report), valid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--source", help="Existing read-only helper output directory")
    inputs.add_argument(
        "--solution", action="append", help="Private original response; no invented claims"
    )
    parser.add_argument("--replays", help="Existing private offline replay sidecar")
    parser.add_argument(
        "--destination", required=True, help="Separate existing private dashboard directory"
    )
    parser.add_argument(
        "--economics", help="Optional previously computed native offline economics report"
    )
    parser.add_argument("--legacy-timezone")
    args = parser.parse_args()
    try:
        return (
            0
            if refresh(
                args.source,
                args.destination,
                economics_file=args.economics,
                legacy_timezone=args.legacy_timezone,
                replay_file=args.replays,
                solutions=args.solution,
            )
            else 2
        )
    except Exception:
        print(
            "Dashboard konnte nicht veröffentlicht werden; Quelldaten unverändert.",
            file=__import__("sys").stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
