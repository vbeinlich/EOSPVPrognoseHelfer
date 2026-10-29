"""Local input adapter. All production writes require explicit opt-ins."""

import argparse
import hashlib
import ipaddress
import json
import logging
import os
import signal
import socket
import sys
import threading
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .normalize import ForecastError, SolarNight, normalize, records_from_json, timestamp
from .storage import atomic_json

LOG = logging.getLogger("eos-pv-helper")
IMPORT_PATH = "/v1/prediction/import/PVForecastImport"
MAX_BYTES = 4_000_000


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ForecastError("HTTP redirects are disabled")


def validate_url(url, local_only=True):
    parts = urlsplit(url)
    if (parts.scheme not in ("http", "https") or not parts.hostname
            or parts.username or parts.password or parts.fragment):
        raise ForecastError("Use an HTTP(S) URL without embedded credentials or fragments")
    if local_only:
        try:
            addresses = socket.getaddrinfo(parts.hostname, parts.port or 80, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ForecastError("Local HTTP host could not be resolved") from exc
        if not addresses or any(not (ipaddress.ip_address(x[4][0]).is_private
                                    or ipaddress.ip_address(x[4][0]).is_loopback)
                                for x in addresses):
            raise ForecastError("Only local source/EOS addresses are enabled")
    return url


def request_json(url, *, method="GET", payload=None, token_env=None, token_file=None, timeout=10,
                 uncached=False):
    # Callers construct the limited writable EOS paths internally.
    if method not in ("GET", "PUT", "POST"):
        raise ForecastError("Unsupported HTTP method")
    headers = {"Accept": "application/json"}
    if uncached:
        headers.update({"Cache-Control": "no-cache, no-store", "Pragma": "no-cache"})
    if token_env and token_file:
        raise ForecastError("Choose either bearer_token_env or bearer_token_file")
    if token_env or token_file:
        if token_file:
            try:
                path = Path(token_file)
                if not path.is_file() or path.stat().st_size > 8192:
                    raise OSError("Invalid secret file")
                token = path.read_text(encoding="utf-8").strip()
            except OSError:
                raise ForecastError("Bearer secret file is absent, unreadable or too large") from None
        else:
            token = os.environ.get(token_env)
        if not token:
            raise ForecastError("Configured bearer token is absent")
        if any(character.isspace() for character in token):
            raise ForecastError("Bearer token contains whitespace")
        headers["Authorization"] = "Bearer " + token
    body = None
    if payload is not None:
        body = json.dumps(payload, allow_nan=False).encode()
        headers["Content-Type"] = "application/json"
    try:
        with build_opener(NoRedirect()).open(
            Request(url, data=body, headers=headers, method=method), timeout=timeout
        ) as response:
            if uncached and response.headers.get("Age") is not None:
                raise ForecastError("Cached HTTP response is not a device-read freshness proof")
            content = response.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                raise ForecastError("HTTP response exceeds size limit")
            return json.loads(content) if content else None
    except HTTPError as exc:
        # Never log response bodies, request URLs, bearer tokens or their query strings.
        raise ForecastError(f"HTTP request failed with status {exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise ForecastError("HTTP request failed or timed out") from None


def eos_base(config):
    base = config.get("url", "").rstrip("/")
    validate_url(base)
    if urlsplit(base).query or urlsplit(base).path not in ("", "/"):
        raise ForecastError("EOS URL must be an origin without path or query")
    return base


def verify_contract(schema):
    """Require the explicit DataFrame contract, not just the permissive dict fallback."""
    try:
        operation = schema["paths"]["/v1/prediction/import/{provider_id}"]["put"]
        body = operation["requestBody"]["content"]["application/json"]["schema"]
        choices = body.get("anyOf", [body])
        ref = "#/components/schemas/PydanticDateTimeDataFrame"
        if not any(x.get("$ref") == ref for x in choices):
            raise ForecastError("EOS API does not advertise the DateTimeDataFrame import")
        model = schema["components"]["schemas"]["PydanticDateTimeDataFrame"]
        if "data" not in model.get("required", []) or "tz" not in model["properties"]:
            raise ForecastError("EOS DateTimeDataFrame contract changed")
    except (KeyError, TypeError) as exc:
        raise ForecastError("EOS import schema is incomplete") from exc
    return {
        "eos_version": schema.get("info", {}).get("version"),
        "openapi_sha256": hashlib.sha256(
            json.dumps(schema, sort_keys=True).encode()
        ).hexdigest(),
    }


def read_source(config):
    kind = config.get("kind", "file")
    if kind == "file":
        path = Path(config["path"])
        if path.stat().st_size > MAX_BYTES:
            raise ForecastError("Source file exceeds size limit")
        return json.loads(path.read_text(encoding="utf-8"))
    if kind == "http":
        url = validate_url(config["url"])
        return request_json(url, token_env=config.get("bearer_token_env"),
                            token_file=config.get("bearer_token_file"))
    raise ForecastError("Source kind must be file or http; no remote forecast APIs are called")


def run_once(config, *, write_eos=False, refresh_source=False, now=None,
             source_reader=read_source, http=request_json, clock=None):
    output = Path(config.get("output", {}).get("directory", "/output"))
    clock = clock or ((lambda: now) if now is not None else lambda: datetime.now(UTC))
    now = now or clock()
    horizon = config.get("horizon", {})
    start = (timestamp(horizon["start"]) if horizon.get("start") else
             now.astimezone(UTC).replace(minute=now.minute // 15 * 15, second=0, microsecond=0))
    source = config["source"]
    provenance = {}
    maximum = horizon.get("max_hours", horizon.get("hours", 48))
    mode = horizon.get("mode", "dynamic")
    minimum = horizon.get("minimum_hours", 24) if mode == "dynamic" else None
    if mode not in ("dynamic", "fixed"):
        raise ForecastError("horizon.mode must be dynamic or fixed")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 24 <= maximum <= 168:
        raise ForecastError("PV maximum hours must be an integer in 24..168")
    if minimum is not None and (isinstance(minimum, bool) or not isinstance(minimum, int)
                                or not 24 <= minimum <= maximum):
        raise ForecastError("Dynamic minimum_hours must be >=24 and <= maximum hours")
    if source.get("kind") == "eos-forecastsolar":
        from .eos_source import load_forecast

        origin = eos_base(config["eos"])
        settings = http(origin + "/v1/config")
        requested = maximum
        eos_hours = settings.get("prediction", {}).get("hours", maximum)
        if isinstance(eos_hours, bool) or not isinstance(eos_hours, int):
            raise ForecastError("EOS prediction.hours must be an integer")
        if isinstance(maximum, bool) or not isinstance(maximum, int):
            raise ForecastError("PV maximum hours must be an integer")
        maximum = min(maximum, eos_hours)
        if minimum is not None and maximum < minimum:
            raise ForecastError("EOS prediction horizon is below the required PV minimum")
        raw, site, source, provenance = load_forecast(
            source, settings, refresh=refresh_source, clock=clock
        )
        provenance["configured_max_hours"] = requested
        values = records_from_json(raw, source)
    else:
        values = records_from_json(source_reader(source), source)
        site = config["location"]
    if not horizon.get("start"):
        aligned_now = clock().astimezone(UTC)
        start = aligned_now.replace(minute=aligned_now.minute // 15 * 15, second=0, microsecond=0)
    night = SolarNight(site["latitude"], site["longitude"], site.get("timezone", "Europe/Berlin"))
    try:
        payload, report = normalize(values, start, maximum, night,
                                    source.get("interval_seconds", 900),
                                    minimum_hours=minimum)
    except ForecastError as exc:
        failure = {**(exc.report or {}), **provenance, "ok": False,
                   "checked_at_utc": clock().isoformat(), "reason": str(exc)}
        atomic_json(output / "forecast-error.json", failure)
        atomic_json(output / "health.json", {"ok": False, "checked_at": time.time()})
        raise
    report.update(provenance)
    eos = config.get("eos", {})
    if write_eos and eos.get("write_enabled") is not True:
        raise ForecastError("EOS writing requires both write_enabled=true and --write-eos")
    if write_eos and os.environ.get("DRY_RUN", "true").lower() != "false":
        raise ForecastError("EOS writes are blocked by DRY_RUN (default true)")
    contract = {}
    base = None
    if eos.get("url"):
        base = eos_base(eos)
        schema = http(base + "/openapi.json")
        contract = verify_contract(schema)
        # Never change provider settings or force-enable a provider.
        active = http(base + "/v1/config")
        if active.get("pvforecast", {}).get("provider") != "PVForecastImport":
            raise ForecastError("EOS must already select PVForecastImport")
        import_config = active.get("pvforecast", {}).get("pvforecastimport") or {}
        if import_config.get("import_file_path") or import_config.get("import_json"):
            raise ForecastError("EOS file/JSON import may overwrite HTTP imports; resolve explicitly")
    elif write_eos:
        raise ForecastError("An EOS URL is required for writing")
    report.update(contract)
    report.update({"checked_at_utc": clock().isoformat(), "mode": "write" if write_eos else "dry-run"})
    atomic_json(output / "forecast.json", payload)
    atomic_json(output / "report.json", report)
    if write_eos:
        # Exactly one scoped write. No updates, optimization, configuration, or device commands.
        http(base + IMPORT_PATH, method="PUT", payload=payload)
        returned = http(base + "/v1/prediction/series?" + urlencode({
            "key": "pvforecast_ac_power", "processing": "raw", "dropna": "false",
            "start_datetime": report["start_utc"], "end_datetime": report["end_exclusive_utc"]}))
        observed = {timestamp(k): v for k, v in returned.get("data", {}).items()}
        for key, value in payload["data"].items():
            if observed.get(timestamp(key)) != value["pvforecast_ac_power"]:
                raise ForecastError("EOS import readback differs from the prepared forecast")
        report["import_verified"] = True
        atomic_json(output / "report.json", report)
    atomic_json(output / "health.json", {"ok": True, "checked_at": time.time(), "mode": report["mode"]})
    LOG.info("forecast_valid mode=%s intervals=%s source=%s night_filled=%s",
             report["mode"], report["count"], report["source_count"], report["filled_night_count"])
    return payload, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("run", "sync", "health"), default="run")
    parser.add_argument("--config", default="/app/config.toml")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--write-eos", action="store_true", help="Requires prior operator approval")
    parser.add_argument("--refresh-source", action="store_true",
                        help="Permit the native EOS provider to fetch the existing source")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        try:
            with open(args.config, "rb") as handle:
                config = tomllib.load(handle)
        except (FileNotFoundError, IsADirectoryError):
            raise ForecastError("Private config.toml missing or a directory; create the file first "
                                "and mount it read-only at /app/config.toml") from None
        interval = config.get("poll_seconds", 300)
        if isinstance(interval, bool) or not isinstance(interval, int) or not 30 <= interval <= 3600:
            raise ForecastError("poll_seconds must be an integer between 30 and 3600")
        output = Path(config.get("output", {}).get("directory", "/output"))
        health_age = max(interval * 2 + 30,
                         config.get("trigger", {}).get("request_timeout_seconds", 300) + 150)
        if args.command == "health":
            state = json.loads((output / "health.json").read_text())
            return 0 if state.get("ok") is True and time.time() - state["checked_at"] < health_age else 1
        if args.command == "sync":
            interval = 60
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        while not stop.is_set():
            try:
                if args.command == "sync":
                    from .sync import sync_once
                    report = sync_once(config, write_eos=args.write_eos,
                                       refresh_source=args.refresh_source)
                    if args.once and report["errors"]:
                        return 1
                else:
                    run_once(config, write_eos=args.write_eos, refresh_source=args.refresh_source)
            except Exception as exc:
                atomic_json(output / "health.json", {"ok": False, "checked_at": time.time()})
                if isinstance(exc, ForecastError) and exc.report:
                    atomic_json(output / "forecast-error.json", {**exc.report, "ok": False,
                                "checked_at_utc": datetime.now(UTC).isoformat(), "reason": str(exc)})
                # Whitelist our own safe diagnostics; do not dump source bodies, URLs or secrets.
                detail = str(exc) if isinstance(exc, ForecastError) else type(exc).__name__
                LOG.error("forecast_invalid %s; cycle stopped, no further writes", detail)
                if args.once:
                    return 1
            if args.once:
                return 0
            stop.wait(interval)
        return 0
    except Exception as exc:
        detail = str(exc) if isinstance(exc, ForecastError) else type(exc).__name__
        LOG.error("startup_failed %s", detail)
        return 1


if __name__ == "__main__":
    sys.exit(main())
