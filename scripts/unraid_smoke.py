"""Run template security/volumes/CMD against synthetic data on an isolated Docker engine.

Does not contact Unraid, EOS, evcc, HA or Forecast.Solar. Only temporary test directories
and unnamed, automatically removed containers are used. Never changes existing containers.
"""

import argparse
import json
import shlex
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from pathlib import Path


def docker(*args, **kwargs):
    return subprocess.run(["docker", *args], check=True, text=True, capture_output=True, **kwargs)


def smoke(image, revision=None):
    template = ET.parse(Path(__file__).resolve().parents[1] / "templates/eos-pv-helper.xml").getroot()
    info = json.loads(docker("image", "inspect", image).stdout)[0]["Config"]
    assert info["User"] == "10001:10001"
    assert info["Entrypoint"] == ["python", "-m", "eos_pv_helper"]
    assert info["Cmd"] == ["run"]
    assert "DRY_RUN=true" in info["Env"]
    assert info["Healthcheck"]["Test"][1:] == ["python", "-m", "eos_pv_helper", "health"]
    if revision:
        assert info["Labels"]["org.opencontainers.image.revision"] == revision
    with tempfile.TemporaryDirectory(prefix="eos-unraid-smoke-") as folder:
        root = Path(folder)
        root.chmod(0o755)
        for name in ("input", "output"):
            (root / name).mkdir()
        # Only synthetic fixture output; no secrets. Avoid host-dependent UID/chown tools.
        (root / "output").chmod(0o777)
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        rows = [{"timestamp": (start + timedelta(minutes=i * 15)).isoformat(),
                 "power_w": 0 if i % 4 == 0 else 1000} for i in range(192)]
        (root / "input/source.json").write_text(json.dumps(rows))
        config = f'''[source]
kind = "file"
path = "/input/source.json"
[location]
latitude = 52.52
longitude = 13.405
timezone = "Europe/Berlin"
[horizon]
start = "{start.isoformat()}"
hours = 48
[output]
directory = "/output"
[eos]
write_enabled = false
'''
        (root / "config.toml").write_text(config)
        for file in (root / "config.toml", root / "input/source.json"):
            file.chmod(0o644)
        def run(command, *, check=True):
            args = ["run", "--rm", "--network", "none", *shlex.split(template.findtext("ExtraParams"))]
            for host, target, mode in [(root / "config.toml", "/app/config.toml", "ro"),
                                       (root / "input", "/input", "ro"),
                                       (root / "output", "/output", "rw")]:
                args += ["--mount", f"type=bind,source={host},target={target}" +
                         (",readonly" if mode == "ro" else "")]
            args += ["--env", "DRY_RUN=true", image, *command]
            return subprocess.run(["docker", *args], text=True, capture_output=True, check=check)

        run([*shlex.split(template.findtext("PostArgs")), "--once"])
        def read_output(name):
            # Output files intentionally remain private (0600, UID 10001). Read as
            # the image's own user instead of weakening host permissions for CI.
            response = docker("run", "--rm", "--network", "none", "--read-only", "--cap-drop=ALL",
                              "--mount", f"type=bind,source={root / 'output'},target=/output,readonly",
                              "--entrypoint", "python", image, "-c",
                              f"from pathlib import Path; print(Path('/output/{name}').read_text())")
            return json.loads(response.stdout)

        forecast = read_output("forecast.json")
        report = read_output("report.json")
        assert len(forecast["data"]) == 192 and report["mode"] == "dry-run"
        run(["health"])
        # Package/entrypoint and full native EOS dependency check, without an external request.
        docker("run", "--rm", "--network", "none", "--read-only", "--cap-drop=ALL",
               "--tmpfs=/tmp:rw,size=16m", "--entrypoint", "python", image, "-c",
               "from akkudoktoreos.prediction.pvforecastforecastsolar import PVForecastForecastSolar; "
               "assert callable(PVForecastForecastSolar._request_forecast)")
        # Both flags alone still cannot write with the stock DRY_RUN=true setting.
        (root / "config.toml").write_text(config.replace("write_enabled = false", "write_enabled = true"))
        failed = run(["run", "--once", "--write-eos"], check=False)
        assert failed.returncode == 1 and "DRY_RUN" in failed.stderr
        # First start without the native cache has a distinct, actionable diagnostic.
        code = '''from eos_pv_helper.eos_source import load_forecast
from eos_pv_helper.normalize import ForecastError
try:
    load_forecast({"cache_file": "/tmp/absent.json"}, {
        "general": {"latitude": 52.52, "longitude": 13.405, "timezone": "Europe/Berlin"},
        "pvforecast": {"provider": "PVForecastImport", "planes": [
            {"surface_tilt": 30, "surface_azimuth": 180, "peakpower": 11}]}})
except ForecastError as exc:
    assert "No matching fresh source cache" in str(exc)
else:
    raise AssertionError("Missing cache must never be silently fetched")
'''
        docker("run", "--rm", "--network", "none", "--read-only", "--cap-drop=ALL",
               "--tmpfs=/tmp:rw,size=16m", "--entrypoint", "python", image, "-c", code)
    print(json.dumps({"image": image, "revision": revision, "template_smoke": "passed",
                      "network": "none", "forecast_intervals": 192}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--revision")
    args = parser.parse_args()
    smoke(args.image, args.revision)
