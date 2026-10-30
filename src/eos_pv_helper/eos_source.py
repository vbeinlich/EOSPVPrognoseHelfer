"""Reuse EOS's Forecast.Solar provider, never a second Forecast.Solar client.

The normalizer image can read a previously exported JSON cache. Only the optional
EOS-source image includes the native provider. External retrieval requires two opt-ins.
"""

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .normalize import ForecastError, records_from_json, timestamp
from .storage import atomic_json


def native_forecast(settings, working_directory):
    """Call only the upstream request method in a private, local EOS instance."""
    try:
        from loguru import logger
        logger.disable("akkudoktoreos")  # Upstream HTTP exceptions can contain secret URLs.
        from akkudoktoreos.core.coreabc import get_config
        from akkudoktoreos.prediction.pvforecastforecastsolar import PVForecastForecastSolar
    except ImportError as exc:
        raise ForecastError("Native EOS source needs the eos-source Docker target") from exc
    folder = Path(working_directory)
    folder.mkdir(parents=True, exist_ok=True)
    os.environ["EOS_DIR"] = str(folder)
    os.environ["EOS_CONFIG_DIR"] = str(folder)
    local = get_config(init={
        "with_init_settings": True, "with_env_settings": False,
        "with_dotenv_settings": False, "with_file_settings": False,
        "with_file_secret_settings": False,
    })
    # These are this container's settings, NOT a PUT to the existing EOS server.
    local.merge_settings_from_dict({
        "general": {**settings["general"], "data_folder_path": str(folder)},
        "pvforecast": {**settings["pvforecast"], "provider": "PVForecastForecastSolar"},
        "ems": {"mode": "DISABLED"},
    })
    try:
        # The pinned native method has its own 1-hour file cache. Only our locked
        # TTL decides when a fetch is due; bypass that inner cache so a successful
        # refresh cannot relabel an older native response with a new fetched_at.
        return PVForecastForecastSolar()._request_forecast(force_update=True)
    except Exception as exc:
        raise ForecastError("The native EOS Forecast.Solar request failed") from exc


def load_forecast(source, eos_settings, *, refresh=False, now=None, fetcher=native_forecast,
                  clock=None):
    """Serialize every cache consumer, including standalone and periodic processes."""
    import fcntl

    clock = clock or ((lambda: now) if now is not None else lambda: datetime.now(UTC))
    path = Path(source["cache_file"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # Read the clock/cache AFTER waiting, not the potentially stale cycle start.
        return _load_locked(source, eos_settings, refresh, clock, fetcher)


def _load_locked(source, eos_settings, refresh, clock, fetcher):
    now = clock()
    general, pv = eos_settings["general"], eos_settings["pvforecast"]
    if pv.get("provider") != "PVForecastImport":
        raise ForecastError("Keep EOS on PVForecastImport to avoid two active source fetchers")
    planes = pv.get("planes")
    if not planes or any(any(p.get(k) is None for k in (
            "surface_tilt", "surface_azimuth", "peakpower")) for p in planes):
        raise ForecastError("EOS must provide complete PV geometry; no defaults are invented")
    location = {key: general.get(key) for key in ("latitude", "longitude", "timezone")}
    if any(value is None for value in location.values()):
        raise ForecastError("EOS must provide coordinates and timezone")
    settings = {
        "general": {"latitude": location["latitude"], "longitude": location["longitude"],
                    "timezone_override": location["timezone"]},
        "pvforecast": {"planes": planes, "forecastsolar": pv.get("forecastsolar") or {}},
    }
    fingerprint = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()
    path = Path(source["cache_file"])
    try:
        cached = json.loads(path.read_text()) if path.is_file() else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        cached = None
    if not isinstance(cached, dict):
        cached = None
    max_age = source.get("max_age_seconds", 3600)
    if isinstance(max_age, bool) or not isinstance(max_age, int) or not 300 <= max_age <= 86400:
        raise ForecastError("max_age_seconds must be 300..86400")
    valid = (isinstance(cached, dict) and cached.get("settings_sha256") == fingerprint
             and cached.get("fetched_at_utc")
             and timedelta(0) <= now - timestamp(cached["fetched_at_utc"]) < timedelta(seconds=max_age))
    stale_report = {"source_fetched_at_utc": (cached or {}).get("fetched_at_utc"),
                    "source_max_age_seconds": max_age, "source_status": "missing_expired_or_mismatched"}
    if not valid:
        if not refresh or source.get("refresh_enabled") is not True:
            raise ForecastError("No matching fresh source cache; explicit source-refresh approval needed",
                                report=stale_report)
        retry = source.get("retry_seconds", 300)
        if isinstance(retry, bool) or not isinstance(retry, int) or not 30 <= retry <= 3600:
            raise ForecastError("source.retry_seconds must be 30..3600")
        attempt_path = path.with_suffix(".attempt.json")
        previous = json.loads(attempt_path.read_text()) if attempt_path.exists() else {}
        if (previous.get("settings_sha256") == fingerprint
                and previous.get("status") in ("started", "failed")):
            age = (now - timestamp(previous["attempted_at_utc"])).total_seconds()
            if age < retry:
                raise ForecastError("Source refresh cooldown active; old cache is not fresh",
                                    report={**stale_report, "source_status": "cooldown",
                                            "last_attempt_at_utc": previous["attempted_at_utc"]})
        attempt = {"settings_sha256": fingerprint, "attempted_at_utc": now.isoformat(),
                   "status": "started"}
        atomic_json(attempt_path, attempt)
        try:
            raw = fetcher(settings, path.parent / "source-eos")
            if not isinstance(raw, dict) or not isinstance(raw.get("watts"), dict) or not raw["watts"]:
                raise ForecastError("Native Forecast.Solar source returned no watts")
            records_from_json([{"timestamp": key, "power_w": value}
                               for key, value in raw["watts"].items()],
                              {"timezone": raw.get("timezone") or location["timezone"],
                               "allow_irregular_points": True})
        except Exception:
            atomic_json(attempt_path, {**attempt, "status": "failed"})
            raise ForecastError("Native source refresh failed; previous cache was not renewed",
                                report={**stale_report, "source_status": "refresh_failed",
                                        "last_attempt_at_utc": now.isoformat()}) from None
        cached = {"settings_sha256": fingerprint, "fetched_at_utc": clock().isoformat(), "raw": raw}
        atomic_json(path, cached)
        atomic_json(attempt_path, {**attempt, "status": "succeeded"})
    raw = cached["raw"]
    records = [{"timestamp": key, "power_w": value} for key, value in raw["watts"].items()]
    return records, location, {
        "format": "records", "unit": "W", "timestamp_convention": "start",
        "timezone": raw.get("timezone") or location["timezone"],
        "allow_irregular_points": True,
        "interval_seconds": source.get("interval_seconds", 3600),
    }, {"source_provider": "EOS.PVForecastForecastSolar", "settings_sha256": fingerprint,
        "source_fetched_at_utc": cached["fetched_at_utc"], "source_max_age_seconds": max_age,
        "source_age_seconds": (clock() - timestamp(cached["fetched_at_utc"])).total_seconds(),
        "source_status": "fresh", "refresh_enabled": refresh and source.get("refresh_enabled") is True}
