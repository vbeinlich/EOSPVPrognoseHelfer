"""Independent adversarial ZIP vectors from synthetic archives; stdlib, no validator.

Used by unit tests AND immutable-image consumers. Rehashing deliberately bypasses
mere byte-hash detection so wrong solver/request semantics must still be rejected.
"""

import copy
import hashlib
import io
import json
import zipfile


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def pack(manifest, values):
    files = {n: json.dumps(v).encode() for n, v in values.items()}
    manifest["files"] = {n: hashlib.sha256(raw).hexdigest() for n, raw in files.items()}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("snapshot.json", json.dumps(manifest))
        for name, raw in files.items():
            archive.writestr(name, raw)
    return stream.getvalue()


def vectors(manifest, files):
    for failure in ("solver-soc", "solver-device", "solver-pv", "solver-price", "request-soc", "request-price",
                    "request-hash", "request-timezone", "request-origin", "solver-interval",
                    "solver-time-basis", "solver-truncated", "request-extra", "context-hash",
                    "context-partial", "context-solution", "context-request-hash"):
        m = copy.deepcopy(manifest)
        values = {n: json.loads(raw) for n, raw in files.items()}
        solution = values["solution-" + m["event_version"] + ".json"]
        request = values["sync-report.json"]["event"]["request_binding"]
        if failure == "solver-soc":
            solution["parameters"]["pv_battery"]["initial_soc_percentage"] = 0
        elif failure == "solver-device":
            solution["parameters"]["pv_battery"]["device_id"] = "wrong-synthetic-device"
        elif failure in ("solver-pv", "solver-price"):
            key = "pv_forecast_wh" if failure == "solver-pv" else "electricity_price_per_wh"
            solution["parameters"]["ems"][key][0] += 123 if failure == "solver-pv" else .009
        elif failure == "request-soc":
            request["request"]["soc"]["e3dc_s10e_pro"] = 0
        elif failure == "request-price":
            request["request"]["forecasts"]["electricity_price_per_wh"][0] += .009
        elif failure == "request-hash":
            request["request_sha256"] = "0"*64
        elif failure == "request-timezone":
            request["timezone"] = "UTC"
        elif failure == "request-origin":
            request["origin_utc"] = values["sync-state.json"]["events"][m["event_version"]]["start_utc"]
        elif failure == "solver-interval":
            solution["parameters"]["forecast_interval_seconds"] = 900
        elif failure == "solver-time-basis":
            solution["controls_start_at_now"] = False
        elif failure == "solver-truncated":
            solution["parameters"]["ems"]["pv_forecast_wh"].pop()
        elif failure == "request-extra":
            request["request"]["arbitrary_extra"] = "not-the-reviewed-request"
        elif failure == "context-hash":
            m["producer"]["observed_options"]["annual_load_kwh"] = 9876
        elif failure == "context-partial":
            del m["producer"]["observed_options"]
        elif failure == "context-solution":
            m["producer"]["solution_inputs"]["parameters_sha256"] = "0"*64
        elif failure == "context-request-hash":
            m["producer"]["dispatched_request_sha256"] = "0"*64
        if failure.startswith("request-") and failure != "request-hash":
            request["request_sha256"] = sha(request["request"])
            if "producer" in m:
                m["producer"]["dispatched_request_sha256"] = request["request_sha256"]
        if failure.startswith("solver-") and "producer" in m:
            summary = m["producer"]["solution_inputs"]
            p = solution["parameters"]
            summary["parameters_sha256"] = sha(p)
            summary["battery"]["initial_soc_percentage"] = p["pv_battery"]["initial_soc_percentage"]
            for key, field in summary["series"].items():
                field.update(sha256=sha(p["ems"][key]), slots=len(p["ems"][key]))
        yield failure, pack(m, values)
