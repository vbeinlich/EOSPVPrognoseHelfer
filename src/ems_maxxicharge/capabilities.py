"""Operator-forwarded manufacturer facts; no firmware or transport verification."""

CONFIRMED = {
    "provenance": "operator_forwarded_Maxxisun_confirmation_2026-11-16",
    "specific_firmware_verified": False,
    "parallel_e3dc_in_principle": True,
    "local_mqtt_telemetry": True,
    "power_and_soc_limits": "firmware_dependent",
    "exact_discharge_setpoint_supported": False,
    "regulation_source": "compatible_site_smart_meter",
    "ac_grid_charging_in_principle": True,
    "external_grid_charge_start_stop_confirmed": False,
    "virtual_smart_meter_from_e3dc_officially_supported": False,
    "max_south_pv_wp_per_m5_v2plus": 3000,
    "storage_block_wh": 5000,
    "real_meter_compatibility_verified": False,
}

MODELS = {"autonomous": "A · Autonom", "coordinated": "B · Grenzen koordiniert",
          "ideal": "C · Ideal / theoretisch"}

EXPANSIONS = {
    "e3dc": ("Bestand · 11 kWp + 13 kWh E3/DC", 0, 0),
    "pv2_only": ("+2 kWp · ohne Zusatzspeicher", 1, 0),
    "pv2_bat5": ("+2 kWp + MaxxiCharge 5 kWh", 1, 1),
    "pv3_only": ("+3 kWp · ohne Zusatzspeicher", 1.5, 0),
    "pv3_bat5": ("+3 kWp + MaxxiCharge 5 kWh", 1.5, 1),
    "pv6_only": ("+6 kWp · ohne Zusatzspeicher", 3, 0),
    "pv6_bat10": ("+6 kWp + MaxxiCharge 10 kWh", 3, 2),
}
