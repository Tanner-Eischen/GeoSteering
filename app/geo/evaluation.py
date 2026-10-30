from __future__ import annotations

import numpy as np
import pandas as pd

from app.geo.formation import Scenario, formation_top_base


def evaluate_trajectory(
    trajectory_df: pd.DataFrame, scenario: Scenario, integration_step_ft: float = 1.0,
) -> dict[str, float | int]:
    """Retrospective lateral score against withheld truth.

    Integrate on fixed MD intervals, splitting each linear boundary crossing.
    The spatial field is nonlinear; refinement tests bound discretization error.
    Report the numerical integration resolution explicitly.
    """
    if not np.isfinite(integration_step_ft) or integration_step_ft <= 0:
        raise ValueError("Integration step must be positive and finite.")
    traj = trajectory_df.sort_values("md_ft")
    start = max(scenario.lateral_start_md_ft, float(traj.md_ft.min()))
    end = min(scenario.max_md_ft, float(traj.md_ft.max()))
    if end < scenario.max_md_ft - 1e-8:
        raise ValueError("Truth evaluation requires a completed trajectory.")
    if end <= start:
        raise ValueError("Evaluation requires a positive-length lateral interval.")
    md = np.linspace(start, end, max(2, int(np.ceil((end - start) / integration_step_ft)) + 1))
    xcol = "x_ft" if "x_ft" in traj else "east_ft"
    x = np.interp(md, traj.md_ft, traj[xcol])
    tvd = np.interp(md, traj.md_ft, traj.tvd_ft)
    top, base = formation_top_base(x, scenario)
    a, b = tvd - top, base - tvd
    length = np.diff(md)
    lo = np.zeros_like(length)
    hi = np.ones_like(length)
    valid = np.ones_like(length, dtype=bool)
    for clearance in (a, b):
        left, right = clearance[:-1], clearance[1:]
        slope = right - left
        positive = slope > 0
        negative = slope < 0
        crossing = np.divide(-left, slope, out=np.zeros_like(left), where=slope != 0)
        lo = np.where(positive, np.maximum(lo, crossing), lo)
        hi = np.where(negative, np.minimum(hi, crossing), hi)
        valid &= (slope != 0) | (left >= 0)
    fractions = np.where(valid, np.maximum(0.0, np.minimum(1.0, hi) - np.maximum(0.0, lo)), 0.0)
    in_zone = float(np.dot(length, fractions))
    distance = np.abs(tvd - (top + base) / 2.0)
    mean_distance = float(np.sum(length * (distance[:-1] + distance[1:]) / 2.0) / (end - start))
    dls = traj.loc[(traj.md_ft > start) & (traj.md_ft <= end), "dls_deg_per_100ft"]
    return {
        "percent_in_zone": 100.0 * in_zone / (end - start),
        "in_zone_length_ft": in_zone,
        "evaluated_length_ft": end - start,
        "avg_center_distance_ft": mean_distance,
        "max_overshoot_ft": float(np.maximum(np.maximum(-a, -b), 0.0).max()),
        "max_dls_deg_per_100ft": float(dls.max()) if len(dls) else 0.0,
        "dls_violation_count": int((dls > scenario.max_dls_deg_per_100ft + 1e-8).sum()),
        "integration_step_max_ft": float(length.max()),
    }
