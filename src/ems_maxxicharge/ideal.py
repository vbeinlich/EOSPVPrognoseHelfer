"""Offline ideal controllability bound. Never a device command generator."""

import math
import warnings

from .config import SimulationError

FIELDS = ("base_direct", "e3_charge", "base_export", "extra_direct", "m_charge",
          "extra_export", "curtail", "e3_discharge", "m_discharge", "grid_house",
          "grid_charge", "e3_end", "m_end", "e3_charge_mode", "m_charge_mode",
          "grid_import_mode", "grid_charge_mode")


def optimize(rows, extras, e3dc, maxxi, config, *, grid_optional=False):
    """MILP: physical SOC/AC limits, no simultaneous battery directions/peer charging.

    Perfect horizon knowledge and freely chosen powers are THEORETICAL only.
    Returned primal and dual objectives use EUR and identical terminal valuation.
    """
    try:
        import numpy as np
        from scipy.optimize import Bounds, LinearConstraint, milp
        from scipy.sparse import coo_array
    except ImportError:
        raise SimulationError("Ideal comparison requires the pinned scipy simulation extra") from None
    n, width = len(rows), len(FIELDS)
    if n > 744:
        raise SimulationError("Ideal MILP horizon exceeds the bounded 744-slot review workload")
    size = n * width
    lower, upper, objective = np.zeros(size), np.zeros(size), np.zeros(size)
    integral = np.zeros(size, dtype=int)
    matrix_r, matrix_c, matrix_v, constraint_l, constraint_u = [], [], [], [], []

    def idx(i, key):
        return i * width + FIELDS.index(key)

    def bound(i, key, low, high, cost=0):
        k = idx(i, key)
        lower[k], upper[k], objective[k] = low, max(low, high), cost

    def constrain(coefficients, low, high):
        r = len(constraint_l)
        for k, v in coefficients.items():
            matrix_r.append(r)
            matrix_c.append(k)
            matrix_v.append(v)
        constraint_l.append(low)
        constraint_u.append(high)

    initial_b = e3dc.capacity_wh * e3dc.initial_soc_percent / 100
    initial_m = maxxi.capacity_wh * maxxi.initial_soc_percent / 100 if maxxi else 0
    for i, (row, extra) in enumerate(zip(rows, extras)):
        h, base, load = row["interval_seconds"] / 3600, row["base_pv_wh"], row["load_wh"]
        bp, bd = e3dc.max_pv_charge_w * h, e3dc.max_discharge_w * h
        mp = maxxi.max_pv_charge_w * h if maxxi else 0
        md = min(maxxi.max_discharge_w, config.operation.maxxi_ac_output_limit_w) * h if maxxi else 0
        mg = maxxi.max_grid_charge_w * h if maxxi and grid_optional else 0
        ac = config.operation.maxxi_ac_output_limit_w * h if maxxi else (
            config.operation.pv_only_ac_limit_w * h
            if config.operation.pv_only_ac_limit_w is not None else extra)
        price, feed = row["import_eur_kwh"] / 1000, row["export_eur_kwh"] / 1000
        for key, cap in (("base_direct", base), ("e3_charge", min(base, bp)),
                         ("base_export", base), ("extra_direct", min(extra, ac)),
                         ("m_charge", min(extra, mp)), ("extra_export", min(extra, ac)),
                         ("curtail", extra), ("e3_discharge", min(load, bd)),
                         ("m_discharge", min(load, md)), ("grid_house", load), ("grid_charge", mg)):
            cost = price if key in ("grid_house", "grid_charge") else (
                -feed if key in ("base_export", "extra_export") else 0)
            if key == "e3_discharge":
                cost += e3dc.wear_eur_per_kwh_output / 1000
            if key == "m_discharge":
                cost += maxxi.wear_eur_per_kwh_output / 1000 if maxxi else 0
            bound(i, key, 0, cap, cost)
        bound(i, "e3_end", e3dc.capacity_wh * e3dc.min_soc_percent / 100,
              e3dc.capacity_wh * e3dc.max_soc_percent / 100)
        bound(i, "m_end", maxxi.capacity_wh * maxxi.min_soc_percent / 100 if maxxi else 0,
              maxxi.capacity_wh * maxxi.max_soc_percent / 100 if maxxi else 0)
        for key in FIELDS[-4:]:
            bound(i, key, 0, 1)
            integral[idx(i, key)] = 1
        constrain({idx(i, "base_direct"): 1, idx(i, "e3_charge"): 1,
                   idx(i, "base_export"): 1}, base, base)
        constrain({idx(i, "extra_direct"): 1, idx(i, "m_charge"): 1,
                   idx(i, "extra_export"): 1, idx(i, "curtail"): 1}, extra, extra)
        constrain({idx(i, k): 1 for k in ("base_direct", "extra_direct", "e3_discharge",
                                         "m_discharge", "grid_house")}, load, load)
        coefficients = {idx(i, "e3_end"): 1, idx(i, "e3_charge"): -e3dc.charge_efficiency,
                        idx(i, "e3_discharge"): 1 / e3dc.discharge_efficiency}
        if i:
            coefficients[idx(i - 1, "e3_end")] = -1
        constrain(coefficients, initial_b if not i else 0, initial_b if not i else 0)
        coefficients = {idx(i, "m_end"): 1,
                        idx(i, "m_charge"): -maxxi.charge_efficiency if maxxi else 0,
                        idx(i, "grid_charge"): -maxxi.charge_efficiency if maxxi else 0,
                        idx(i, "m_discharge"): 1 / maxxi.discharge_efficiency if maxxi else 0}
        if i:
            coefficients[idx(i - 1, "m_end")] = -1
        constrain(coefficients, initial_m if not i else 0, initial_m if not i else 0)
        constrain({idx(i, "e3_charge"): 1, idx(i, "e3_charge_mode"): -bp}, -math.inf, 0)
        constrain({idx(i, "e3_discharge"): 1, idx(i, "e3_charge_mode"): bd}, -math.inf, bd)
        constrain({idx(i, "m_charge"): 1, idx(i, "grid_charge"): 1,
                   idx(i, "m_charge_mode"): -mp}, -math.inf, 0)
        constrain({idx(i, "m_discharge"): 1, idx(i, "m_charge_mode"): md}, -math.inf, md)
        constrain({idx(i, k): 1 for k in ("extra_direct", "extra_export", "m_discharge")},
                  -math.inf, ac)
        constrain({idx(i, "grid_house"): 1, idx(i, "grid_charge"): 1,
                   idx(i, "grid_import_mode"): -(load + mg)}, -math.inf, 0)
        constrain({idx(i, "base_export"): 1, idx(i, "extra_export"): 1,
                   idx(i, "grid_import_mode"): base + extra}, -math.inf, base + extra)
        constrain({idx(i, "grid_charge"): 1, idx(i, "grid_charge_mode"): -mg}, -math.inf, 0)
        constrain({idx(i, "e3_discharge"): 1, idx(i, "m_discharge"): 1,
                   idx(i, "grid_charge_mode"): bd + md}, -math.inf, bd + md)
    terminal = config.terminal_value_eur_kwh_ac / 1000
    objective[idx(n - 1, "e3_end")] -= e3dc.discharge_efficiency * terminal
    objective[idx(n - 1, "m_end")] -= maxxi.discharge_efficiency * terminal if maxxi else 0
    matrix = coo_array((np.asarray(matrix_v), (np.asarray(matrix_r, dtype=np.int32),
                                              np.asarray(matrix_c, dtype=np.int32))),
                       shape=(len(constraint_l), size)).tocsc()
    # SciPy forwards this pinned HiGHS option but warns because it is not in
    # SciPy's shorter public option list. One solver thread respects pids_limit.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Unrecognized options detected:.*threads.*",
                                category=RuntimeWarning)
        result = milp(objective, integrality=integral, bounds=Bounds(lower, upper),
                      constraints=LinearConstraint(matrix, constraint_l, constraint_u),
                      options={"time_limit": config.operation.ideal_solver_time_limit_seconds,
                               "mip_rel_gap": 1e-9, "presolve": True, "threads": 1})
    if result.x is None or result.status != 0:
        raise SimulationError("Ideal bound not proven within solver limit; no invented fallback")
    plan = [{key: max(0.0, float(result.x[idx(i, key)])) for key in FIELDS[:13]} for i in range(n)]
    return plan, {"engine": "scipy.optimize.milp/HiGHS", "optimality_proven": True,
                  "mip_gap": float(result.mip_gap), "objective_eur": float(result.fun),
                  "dual_bound_eur": float(result.mip_dual_bound),
                  "objective": "operating_cost_minus_final_usable_inventory_value",
                  "perfect_foresight": True, "hardware_executable": False}
