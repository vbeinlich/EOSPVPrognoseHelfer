"""Read-only evcc battery validation with a narrowly audited freshness proof.

Cached /api/state, historyUpdated and value changes are never freshness evidence.
Only the uncached E3/DC RSCP getters in evcc 0.318.1 are currently audited.
"""

import re
from urllib.parse import quote

from .inputs import SOC_KEY, number
from .normalize import ForecastError


def evcc_soc_sample(state, config, origin, http, clock, *, auth=None, refresh_snapshot=None):
    diagnostic = {"source": "evcc", "device_name": config.get("device_name"),
                  "source_timestamp": None, "device_timestamp_available": False,
                  "freshness_verified": False}
    try:
        name = config.get("device_name", "")
        if not isinstance(name, str) or not re.fullmatch(r"db:[0-9]+", name):
            raise ForecastError("Configure the exact evcc E3/DC device_name (db:<id>)")
        limit = number(config.get("max_abs_power_w", 20000))

        def snapshot_soc(raw):
            if not isinstance(raw, dict) or raw.get("version") != "0.318.1":
                raise ForecastError("evcc version differs from the audited uncached-device contract")
            devices = (raw.get("battery") or {}).get("devices")
            if not isinstance(devices, list):
                raise ForecastError("evcc battery devices are absent")
            matches = [d for d in devices if isinstance(d, dict) and d.get("name") == name]
            if len(matches) != 1:
                raise ForecastError("Expected evcc battery device is missing or duplicated")
            device = matches[0]
            soc, power = number(device.get("soc")), number(device.get("power"))
            if not 0 <= soc <= 100 or not 0 < limit <= 100000 or abs(power) > limit:
                raise ForecastError("Invalid evcc device SoC or implausible battery power")
            if raw.get("error") is not None or device.get("error") is not None:
                raise ForecastError("evcc reports an error; battery freshness is not accepted")
            diagnostic.update(percent=soc, factor=soc / 100, power_w=power)
            return soc

        soc = snapshot_soc(state)
        if config.get("freshness") != "e3dc-rscp-status":
            raise ForecastError("evcc /api/state has no proven measurement freshness; select audited proof")
        auth = auth or {}
        ident = name.removeprefix("db:")
        meter = http(origin + "/api/config/devices/meter/" + ident, uncached=True, **auth)
        if not isinstance(meter, dict) or not isinstance(meter.get("config"), dict):
            raise ForecastError("Device configuration response is missing")
        params = meter["config"]
        native = meter.get("type") == "e3dc-rscp"
        template = meter.get("type") == "template" and params.get("template") == "e3dc-rscp"
        if (meter.get("name") != name or not (native or template)
                or params.get("usage") != "battery" or "cache" in params or "yaml" in params):
            raise ForecastError("Device configuration is not the audited uncached E3/DC RSCP battery")
        diagnostic["meter_template"] = "e3dc-rscp"
        started = clock()
        status = http(origin + "/api/config/devices/meter/" + quote(name, safe=":") + "/status",
                      timeout=15, uncached=True, **auth)
        completed = clock()
        diagnostic["freshness_evidence"] = {"read_started_at_utc": started.isoformat(),
                                             "read_completed_at_utc": completed.isoformat()}
        diagnostic["read_window_seconds"] = (completed - started).total_seconds()
        if not 0 <= (completed - started).total_seconds() <= 15:
            raise ForecastError("Device-read proof exceeded its bounded request window")
        values = {}
        for key in ("soc", "power"):
            row = status.get(key)
            if not isinstance(row, dict) or row.get("error") != "" or row.get("asleep"):
                raise ForecastError("Unsuccessful or absent live evcc device getter: " + key)
            values[key] = number(row.get("value"))
        if not 0 <= values["soc"] <= 100 or abs(values["power"]) > limit:
            raise ForecastError("Implausible power in live battery proof")
        if values["soc"] != soc and refresh_snapshot is not None:
            # Exactly one cache GET, never another hardware getter or a polling loop.
            # The successful uncached read remains the sole freshness evidence.
            diagnostic["snapshot_retry_count"] = 1
            soc = snapshot_soc(refresh_snapshot())
        if values["soc"] != soc:
            raise ForecastError("Cached evcc SoC differs from live device read; wait for the next snapshot")
        age = (clock() - started).total_seconds()
        if not 0 <= age <= min(300, config.get("max_age_seconds", 300)):
            raise ForecastError("Verified device read is stale or dated in the future")
        # This is a lower bound on a proven successful *uncached* device read, not a
        # fabricated device clock and never a timestamp for an unproven cached value.
        return {**diagnostic, "key": SOC_KEY, "source_timestamp": started.isoformat(),
                "timestamp_kind": "successful_uncached_device_read_lower_bound",
                "age_seconds": age, "freshness_verified": True, "freshness_evidence": {
                    "contract": "evcc-0.318.1/e3dc-rscp/uncached-getters",
                    "read_started_at_utc": started.isoformat(),
                    "read_completed_at_utc": completed.isoformat(),
                    "live_soc_percent": values["soc"], "live_power_w": values["power"]}}
    except ForecastError as exc:
        exc.report = {**diagnostic, "blocked_reason": str(exc)}
        raise


def ha_diagnostics(state, now):
    """HA comparison does not become an implicit fallback or an optimization gate."""
    from .normalize import timestamp

    result = {"last_reported": state.get("last_reported"), "last_updated": state.get("last_updated")}
    try:
        result["percent"] = number(state.get("state"))
        selected = state.get("last_reported") or state.get("last_updated")
        result["age_seconds"] = (now - timestamp(selected)).total_seconds()
        result["fresh"] = 0 <= result["age_seconds"] <= 300
    except ForecastError:
        result["fresh"] = False
        result["reason"] = "Missing/invalid HA measurement or timestamp"
    return result
