"""Reuse cached radiation/plane forecasts; optional declared geometry proxy only."""

import math
from calendar import isleap
from datetime import UTC, timedelta

from .config import SimulationError, number


def sun_position(at, latitude, longitude):
    """Approximate NOAA fractional-year solar position, without refraction.

    Interval midpoint approximation, not measured irradiance or calibrated yield.
    """
    at = at.astimezone(UTC)
    hour = at.hour + at.minute / 60 + at.second / 3600
    gamma = 2 * math.pi / (366 if isleap(at.year) else 365) * (
        at.timetuple().tm_yday - 1 + (hour - 12) / 24)
    eq = 229.18 * (0.000075 + 0.001868 * math.cos(gamma)
                  - 0.032077 * math.sin(gamma) - 0.014615 * math.cos(2 * gamma)
                  - 0.040849 * math.sin(2 * gamma))
    dec = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
           - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
           - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    ha = math.radians(((hour * 60 + eq + 4 * longitude) % 1440) / 4 - 180)
    lat = math.radians(latitude)
    sin_el = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(ha)
    elevation = math.degrees(math.asin(max(-1, min(1, sin_el))))
    azimuth = (math.degrees(math.atan2(math.sin(ha), math.cos(ha) * math.sin(lat)
                                    - math.tan(dec) * math.cos(lat))) + 180) % 360
    return elevation, azimuth


def poa(ghi, dni, dhi, elevation, azimuth, tilt, surface_azimuth, albedo):
    """Isotropic sky + ground reflection + nonnegative beam (W/m²)."""
    if elevation <= 0:
        return 0.0
    el, beta, diff = map(math.radians, (elevation, tilt, azimuth - surface_azimuth))
    incidence = max(0, math.sin(el) * math.cos(beta)
                    + math.cos(el) * math.sin(beta) * math.cos(diff))
    return (dni * incidence + dhi * (1 + math.cos(beta)) / 2
            + ghi * albedo * (1 - math.cos(beta)) / 2)


def generate(rows, source, config):
    mode = source.get("mode")
    if mode not in ("cached_weather", "cached_planes", "reference_proxy"):
        raise SimulationError("Additional PV needs cached weather/planes or an explicit proxy")
    output = {p.name: [] for p in config.panels}
    if mode == "reference_proxy":
        if source.get("proxy_acknowledged") is not True:
            raise SimulationError("Geometry proxy requires explicit acknowledgement")
        lat = number(source.get("latitude"), "latitude", -90, 90)
        lon = number(source.get("longitude"), "longitude", -180, 180)
        ref_wp = number(source.get("reference_wp"), "reference_wp", 1)
        tilt = number(source.get("reference_tilt_deg"), "reference_tilt_deg", 0, 90)
        az = number(source.get("reference_azimuth_deg"), "reference_azimuth_deg", 0, 360)
    for row in rows:
        hours = row["interval_seconds"] / 3600
        if mode == "cached_planes":
            planes = row.get("planes", {})
            for panel in config.panels:
                plane = planes.get(panel.name, {})
                if (plane.get("azimuth_deg") != panel.azimuth_deg
                        or plane.get("tilt_deg") != panel.tilt_deg
                        or plane.get("basis") != "ac_equivalent_front_wh_per_kwp"):
                    raise SimulationError("Cached plane geometry or energy basis mismatch")
                front = number(plane.get("wh_per_kwp"), "plane wh_per_kwp", 0)
                output[panel.name].append(front * panel.wp / 1000 * (1 + panel.bifacial_gain))
            continue
        if mode == "cached_weather":
            weather = row.get("weather", {})
            if weather.get("basis") != "interval_mean_w_m2":
                raise SimulationError("Weather must contain interval mean irradiance")
            ghi, dni, dhi = [number(weather.get(k), k, 0) for k in ("ghi", "dni", "dhi")]
            elevation = number(weather.get("solar_elevation_deg"), "elevation", -90, 90)
            azimuth = number(weather.get("solar_azimuth_deg"), "solar azimuth", 0, 360)
        else:
            midpoint = row["at"] + timedelta(seconds=row["interval_seconds"] / 2)
            elevation, azimuth = sun_position(midpoint, lat, lon)
            ghi, dhi = 1.0, config.proxy_diffuse_fraction
            dni = (1 - dhi) / max(0.05, math.sin(math.radians(elevation)))
        for panel in config.panels:
            irradiance = poa(ghi, dni, dhi, elevation, azimuth, panel.tilt_deg,
                             panel.azimuth_deg, config.albedo)
            if mode == "cached_weather":
                energy = irradiance / 1000 * panel.wp * panel.performance_ratio * hours
            else:
                reference = poa(ghi, dni, dhi, elevation, azimuth, tilt, az, config.albedo)
                ratio = min(config.proxy_max_orientation_ratio,
                            irradiance / reference) if reference > 1e-9 else 0
                energy = row["base_pv_wh"] / ref_wp * panel.wp * ratio
            output[panel.name].append(energy * (1 + panel.bifacial_gain))
    return output, {
        "mode": mode,
        "quality": "geometry_proxy_assumption" if mode == "reference_proxy" else "cached_input",
        "azimuth_convention": "north=0 east=90 south=180 west=270",
        "energy_basis": "ac_equivalent_wh",
        "bifacial_gain": "multiplicative assumption, not measured rear irradiance",
        "panels": [p.__dict__ for p in config.panels],
    }
