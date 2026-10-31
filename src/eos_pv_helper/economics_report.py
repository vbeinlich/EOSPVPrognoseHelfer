"""Re-evaluate a private numeric export on a diagnostic machine, never on the NAS."""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import economics, plan_inspector


def from_packet(packet, *, scaled_load=False):
    if (not isinstance(packet, dict) or packet.get("schema_version") != 1
            or packet.get("read_only") is not True or not isinstance(packet.get("plans"), list)
            or len(packet["plans"]) > plan_inspector.MAX_PLANS):
        raise economics.ComparisonError("Ungültiger privater Vergleichsexport.")
    plans = []
    now = datetime.now(UTC)
    for original in packet["plans"]:
        version = original.get("version") if isinstance(original, dict) else None
        if not isinstance(version, str) or not plan_inspector.VERSION.fullmatch(version):
            raise economics.ComparisonError("Ungültige Planversion im Export.")
        export = original.get("replay_inputs")
        problem = None
        solution = {}
        try:
            if not isinstance(export, dict) or export.get("schema_version") != 1:
                raise economics.ComparisonError("Originale Vergleichseingaben fehlen im Export.")
            source_hash = export["source_sha256"]
            if (not isinstance(source_hash, str) or not plan_inspector.VERSION.fullmatch(source_hash)
                    or source_hash != original.get("solution_sha256")):
                raise economics.ComparisonError("Original-Bytehash ist inkonsistent.")
            data = export["projection"]
            solution = economics.as_solution(data)
            checked = economics.project(solution)
            if economics.digest(checked) != export["projection_sha256"] or checked != data:
                raise economics.ComparisonError("Exportprojektion oder Hash ist inkonsistent.")
        except Exception as exc:
            solution = {}
            problem = str(exc) if isinstance(exc, economics.ComparisonError) else "Exporteingaben sind ungültig."
        # Rebuild all rendered fields from numeric inputs. Never render free text/config from the packet.
        claim = {"version": version, "status": original.get("claim_status"),
                 "start_utc": original.get("start_utc"), "interval_seconds": original.get("interval_seconds"),
                 "control_hours": original.get("control_hours"), "effective_tail_hours": original.get("effective_tail_hours"),
                 "claimed_at_utc": original.get("claimed_at_utc")}
        raw = economics.canonical(solution)
        plan = plan_inspector.parse_plan(None, version, raw, claim, ZoneInfo("Europe/Berlin"), None,
                                        now, archive_lookup=False, scaled_load=scaled_load, calculate=True)
        if problem:
            plan["comparison"] = {"status": "not_calculable", "message": "Nicht berechenbar: "+problem}
        else:
            plan["solution_sha256"] = export["source_sha256"]
            plan["comparison"]["source_solution_sha256"] = export["source_sha256"]
            plan["comparison"]["projection_sha256"] = export["projection_sha256"]
        plans.append(plan)
    return {"schema_version": 1, "phase": 2, "read_only": True, "timezone": "Europe/Berlin",
            "generated_at_utc": now.isoformat(), "latest_sync_status": packet.get("latest_sync_status")
            if packet.get("latest_sync_status") in plan_inspector.STATUSES else "unknown",
            "warnings": ["Privater Offline-Vergleich aus numerischer Operator-Projektion. Hashes belegen Konsistenz, keine Authentizität oder historische Quellfrische."],
            "plans": plans, "summary_fields": plan_inspector.SUMMARY_FIELDS,
            "model_fields": plan_inspector.MODEL_FIELDS, "tail_fields": plan_inspector.TAIL_FIELDS}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--input-report", help="Private --comparison-inputs export; never a live endpoint")
    inputs.add_argument("--solution", action="append", help="Existing private original JSON; repeat for multiple plans")
    parser.add_argument("--format", choices=("json", "html"), default="json")
    parser.add_argument("--scaled-load-sensitivity", action="store_true")
    args = parser.parse_args()
    try:
        if args.input_report:
            path = Path(args.input_report)
            raw = plan_inspector.read(path.parent, path.name, 32_000_000)
            data = from_packet(json.loads(raw), scaled_load=args.scaled_load_sensitivity)
        else:
            if args.format != "json":
                raise economics.ComparisonError("HTML benötigt einen privaten Inspector-Export mit Planversionen.")
            data = {"schema_version": 1, "read_only": True, "plans": []}
            if len(args.solution) > plan_inspector.MAX_PLANS:
                raise economics.ComparisonError("Zu viele Pläne.")
            for name in args.solution:
                raw, solution = None, {}
                try:
                    path = Path(name)
                    raw = plan_inspector.read(path.parent, path.name)
                    solution = plan_inspector.obj(raw)
                    comparison = economics.evaluate(solution, scaled_load=args.scaled_load_sensitivity)
                except Exception:
                    comparison = {"status": "not_calculable", "message": "Nicht berechenbar: historische Originaldatei fehlt, ist unsicher oder ungültig."}
                data["plans"].append({"source_solution_sha256": hashlib.sha256(raw).hexdigest() if raw else None,
                    "start_utc": plan_inspector.stamp(solution.get("start_solution_datetime")).isoformat()
                    if plan_inspector.stamp(solution.get("start_solution_datetime")) else None,
                    "comparison": comparison})
        if args.format == "html":
            from .plan_view import render
            output = render(data)
        else:
            output = json.dumps(data, ensure_ascii=False, allow_nan=False)
        sys.stdout.buffer.write(output.encode())
        return 0 if data["plans"] and all(p.get("comparison", {}).get("status") == "calculated"
                                         for p in data["plans"]) else 2
    except Exception as exc:
        reason = str(exc) if isinstance(exc, economics.ComparisonError) else "Privater Vergleichseingang ungültig; keine Quelldateien geändert."
        print(reason, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
