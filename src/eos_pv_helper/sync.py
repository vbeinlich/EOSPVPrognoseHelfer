"""Input synchronization and an opt-in event consumer, not a periodic optimizer."""

import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from .app import atomic_json, eos_base, request_json, run_once, verify_contract
from .inputs import (
    PRICE_KEY,
    SOC_KEY,
    coverage,
    day_ahead_version,
    number,
    raw_series,
    retail_prices,
    soc_sample,
)
from .normalize import ForecastError, timestamp

LOG = logging.getLogger("eos-pv-helper")
TESTED_EOS_VERSION = "v0.3.0.dev2602241646141478"


def verify_sync_contract(schema):
    verify_contract(schema)
    try:
        operation = schema["paths"]["/v1/measurement/value"]["put"]
        params = {p["name"] for p in operation["parameters"] if p["in"] == "query"}
        ref = schema["paths"]["/v1/optimize"]["post"]["requestBody"][
            "content"]["application/json"]["schema"]
        if not {"datetime", "key", "value"} <= params or not (
            ref.get("$ref", "").endswith("/ConfigOptimizationRequest")
        ):
            raise KeyError("contract")
        if schema["info"]["version"] != TESTED_EOS_VERSION:
            raise ForecastError("EOS version differs from the tested gross-price/simulation contract")
    except (KeyError, TypeError):
        raise ForecastError("EOS measurement/optimization contract changed") from None


def price_provider_ready(settings, config):
    prices = settings.get("elecprice", {})
    if prices.get("provider") != "ElecPriceImport":
        raise ForecastError("Price import blocked: EOS must already select ElecPriceImport after approval")
    source = prices.get("elecpriceimport") or {}
    if source.get("import_file_path") or source.get("import_json"):
        raise ForecastError("EOS file/JSON price import could overwrite retail prices")
    if config.get("retail_prices_confirmed") is not True:
        raise ForecastError("Confirm evcc retail prices against LUOX before importing")


def simulation_safe(settings):
    ems = settings.get("ems", {})
    if ems.get("mode") != "PREDICTION" or ems.get("interval") != 3600:
        raise ForecastError("Expected existing EOS PREDICTION mode and 3600-second interval")
    if settings.get("optimization", {}).get("algorithm") != "GENETIC":
        raise ForecastError("Expected existing GENETIC algorithm")
    # EMS.run updates adapters and may send a completion webhook. Never disable them here.
    if settings.get("adapter", {}).get("provider") or ems.get("notify_url"):
        raise ForecastError("Simulation blocked: active EOS adapters or notification webhook")
    devices = settings.get("devices", {})
    batteries = devices.get("batteries", {})
    if (not isinstance(batteries, dict) or set(batteries) != {SOC_KEY.removesuffix("-soc-factor")}
            or devices.get("electric_vehicles")):
        raise ForecastError("Simulation requires exactly the mapped battery and no unvalidated EV SoC")
    if next(iter(batteries.values())).get("measurement_key_soc_factor") != SOC_KEY:
        raise ForecastError("Battery SoC measurement mapping differs from the validated source")


def readback(http, origin, path, expected):
    observed = raw_series(http(origin + path))
    for key, value in expected.items():
        if observed.get(timestamp(key)) != value:
            raise ForecastError("EOS import raw readback differs")


def verify_solution(solution, plan):
    if (not isinstance(solution, dict)
            or solution.get("interval_seconds") != plan["interval_seconds"]
            or timestamp(solution.get("start_solution_datetime", "")) != timestamp(plan["start_utc"])):
        raise ForecastError("EOS did not return a new solution for this interval")
    count = int(plan["control_hours"] * 3600 / plan["interval_seconds"])
    for key in ("ac_charge", "dc_charge", "discharge_allowed"):
        values = solution.get(key)
        if not isinstance(values, list) or len(values) < count:
            raise ForecastError("Incomplete EOS solution")
        for value in values:
            number(value)
    number(solution.get("result", {}).get("total_costs"))


def sync_once(config, *, write_eos=False, refresh_source=False, now=None, http=request_json,
              pv_runner=run_once, clock=None):
    """One 60-second tick. A durable claim precedes POST; ambiguous outcomes never retry."""
    import fcntl

    clock = clock or (lambda: datetime.now(UTC))
    output = Path(config.get("output", {}).get("directory", "/output"))
    output.mkdir(parents=True, exist_ok=True)
    with (output / "sync.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        now = now or clock()
        state_path = output / "sync-state.json"
        state = json.loads(state_path.read_text()) if state_path.exists() else {"events": {}}
        report = {"checked_at_utc": now.isoformat(), "mode": "dry-run", "errors": {}}
        write = write_eos and os.environ.get("DRY_RUN", "true").lower() == "false"
        if write and config.get("eos", {}).get("write_enabled") is not True:
            raise ForecastError("EOS writes require write_enabled=true and --write-eos")
        if write:
            report["mode"] = "write"
        origin = eos_base(config["eos"])
        settings = http(origin + "/v1/config")
        schema = http(origin + "/openapi.json")
        verify_sync_contract(schema)
        soc, prices = config.get("soc", {}), config.get("prices", {})

        def attempt(name, operation):
            try:
                return operation()
            except Exception as exc:
                detail = str(exc) if isinstance(exc, ForecastError) else type(exc).__name__
                report["errors"][name] = detail
                LOG.warning("sync_blocked component=%s reason=%s", name, detail)
                return None

        # PV keeps its own cadence; a failed PV refresh must not suppress independent SoC reads.
        if (now.timestamp() - state.get("pv_checked_at", 0) >= config.get("poll_seconds", 300)
                or (write and not state.get("pv_import_verified"))):
            state["pv_checked_at"] = now.timestamp()
            pv = attempt("pv", lambda: pv_runner(config, write_eos=write,
                         refresh_source=refresh_source, now=now, http=http))
            state["pv_ok"] = pv is not None
            state["pv_import_verified"] = bool(pv and pv[1].get("import_verified"))
        if not state.get("pv_ok"):
            report["errors"].setdefault("pv", "Last PV validation failed")

        sample, frame = None, None
        if soc.get("enabled") is True:
            def sync_soc():
                base = eos_base({"url": soc["url"]})
                value = soc_sample(http(base + "/api/states/sensor.evcc_battery_soc",
                                       token_env=soc.get("bearer_token_env"),
                                       token_file=soc.get("bearer_token_file")), clock(),
                                   soc.get("max_age_seconds", 300))
                report["soc"] = value
                atomic_json(output / "soc.json", value)
                if write and soc.get("write_enabled") is True:
                    query = urlencode({"datetime": value["source_timestamp"], "key": SOC_KEY,
                                       "value": value["factor"]})
                    http(origin + "/v1/measurement/value?" + query, method="PUT")
                    readback(http, origin, "/v1/measurement/series?" + urlencode(
                        {"key": SOC_KEY, "processing": "raw", "dropna": "false"}),
                        {value["source_timestamp"]: value["factor"]})
                    report["soc"]["import_verified"] = True
                return value
            sample = attempt("soc", sync_soc)
        if prices.get("enabled") is True:
            def sync_prices():
                base = eos_base({"url": prices["url"]})
                raw = http(base + "/api/state")
                value = retail_prices(raw)
                atomic_json(output / "prices-source.json", {"fetched_at_utc": now.isoformat(),
                            "currency": raw["currency"], "grid": raw["forecast"]["grid"]})
                atomic_json(output / "prices.json", value)
                report["prices"] = {"count": len(value["data"]), "unit": "EUR/Wh",
                                    "fees_added": False}
                # Dry-run reports provider blockers but still exports the central cache.
                attempt("price_provider", lambda: price_provider_ready(settings, prices))
                if write and prices.get("write_enabled") is True:
                    price_provider_ready(settings, prices)
                    http(origin + "/v1/prediction/import/ElecPriceImport", method="PUT", payload=value)
                    readback(http, origin, "/v1/prediction/series?" + urlencode(
                        {"key": PRICE_KEY, "processing": "raw", "dropna": "false"}),
                        {key: row[PRICE_KEY] for key, row in value["data"].items()})
                    report["prices"]["import_verified"] = True
                return value
            frame = attempt("prices", sync_prices)

        trigger = config.get("trigger", {})
        if trigger.get("enabled") is True:
            def event():
                timeout = trigger.get("request_timeout_seconds", 300)
                if isinstance(timeout, bool) or not isinstance(timeout, int) or not 10 <= timeout <= 1800:
                    raise ForecastError("Simulation request timeout must be 10..1800 seconds")
                if sample is None or frame is None or not state.get("pv_ok"):
                    raise ForecastError("Event needs valid fresh SoC, prices and PV")
                pv_config = settings.get("pvforecast", {})
                pv_import = pv_config.get("pvforecastimport") or {}
                if (pv_config.get("provider") != "PVForecastImport"
                        or pv_import.get("import_file_path") or pv_import.get("import_json")):
                    raise ForecastError("Simulation needs PVForecastImport without file/JSON override")
                simulation_safe(settings)
                try:
                    version = day_ahead_version(frame, clock(), config.get("timezone", "Europe/Berlin"))
                except ForecastError:
                    report["event"] = {"status": "waiting-publication"}
                    return
                report["event"] = version
                prior = state["events"].get(version["version"])
                if prior:
                    report["event"]["status"] = prior["status"]
                    if prior["status"] != "succeeded":
                        raise ForecastError("Previous dispatch outcome uncertain; manual review required")
                    return
                series = {PRICE_KEY: {timestamp(k): v[PRICE_KEY] for k, v in frame["data"].items()}}
                # GET raw cached EOS inputs only: never call prediction/update or a weather API.
                for key in ("pvforecast_ac_power", "loadforecast_power_w", "feed_in_tariff_wh"):
                    series[key] = raw_series(http(origin + "/v1/prediction/series?" + urlencode(
                        {"key": key, "processing": "raw", "dropna": "false"})))
                plan = coverage(settings, series, clock())
                report["event"].update(plan, status="ready-dry-run")
                LOG.info("simulation_ready mode=%s delivery_day=%s version=%s tail_hours=%s",
                         report["mode"], version["delivery_day"], version["version"],
                         plan["effective_tail_hours"])
                if report["errors"]:
                    raise ForecastError("Input validation or provider checks block simulation")
                if not write or trigger.get("run_enabled") is not True:
                    return
                if (not state.get("pv_import_verified")
                        or not report.get("soc", {}).get("import_verified")
                        or not report.get("prices", {}).get("import_verified")):
                    raise ForecastError("Simulation requires approved and verified PV/SoC/price imports")
                # Recheck configuration and data at the final boundary; never issue device commands.
                final_settings = http(origin + "/v1/config")
                simulation_safe(final_settings)
                for key in ("ems", "adapter", "devices", "optimization", "prediction",
                            "pvforecast", "elecprice", "elecfee"):
                    if final_settings.get(key) != settings.get(key):
                        raise ForecastError("EOS configuration changed during input validation")
                readback(http, origin, "/v1/measurement/series?" + urlencode(
                    {"key": SOC_KEY, "processing": "raw", "dropna": "false"}),
                    {sample["source_timestamp"]: sample["factor"]})
                actual_age = (clock() - timestamp(sample["source_timestamp"])).total_seconds()
                if not 0 <= actual_age <= min(300, settings["optimization"]["genetic"].get(
                    "measurement_max_age_seconds", 300)):
                    raise ForecastError("SoC expired before simulation dispatch")
                # Do not dispatch using coverage validated for the preceding slot.
                final_plan = coverage(settings, series, clock())
                if final_plan["start_utc"] != plan["start_utc"]:
                    raise ForecastError("GENETIC slot changed; revalidate on the next input tick")
                claim = {**version, **plan, "status": "uncertain", "claimed_at_utc": now.isoformat()}
                state["events"][version["version"]] = claim
                atomic_json(state_path, state)  # Crash/network ambiguity: never automatically retry.
                report["event"]["status"] = "uncertain"
                # EOS itself quantizes initial SoC to integer percent. Explicitly pass the
                # validated value so a queued request cannot silently fall back to assumed 0%.
                body = {"soc": {SOC_KEY.removesuffix("-soc-factor"): int(sample["percent"])}}
                result = http(origin + "/v1/optimize", method="POST", payload=body, timeout=timeout)
                verify_solution(result, plan)
                atomic_json(output / ("solution-" + version["version"] + ".json"), result)
                claim["status"] = "succeeded"
                report["event"]["status"] = "succeeded"
                LOG.info("simulation_succeeded delivery_day=%s version=%s", version["delivery_day"],
                         version["version"])
            attempt("event", event)

        atomic_json(state_path, state)
        atomic_json(output / "sync-report.json", report)
        atomic_json(output / "health.json", {"ok": not report["errors"], "checked_at": time.time(),
                    "mode": report["mode"]})
        LOG.info("sync_completed mode=%s errors=%s", report["mode"], ",".join(report["errors"]))
        return report
