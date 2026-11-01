from __future__ import annotations

import math

import pandas as pd

from app.alg.trajectory_min_curve import compute_trajectory


def advance_station(
    previous: dict[str, float],
    action: str,
    step_ft: float = 50.0,
    max_dls_deg_per_100ft: float = 3.0,
    target_inc_deg: float | None = None,
) -> tuple[dict[str, float], dict[str, object]]:
    if action not in {"HOLD", "BUILD", "DROP"}:
        raise ValueError("Action must be HOLD, BUILD, or DROP.")
    if step_ft <= 0 or max_dls_deg_per_100ft <= 0:
        raise ValueError("Step length and dogleg limit must be positive.")
    inc = previous["inc_deg"]
    max_change = max_dls_deg_per_100ft * step_ft / 100.0
    requested = inc if action == "HOLD" else inc + (max_change if action == "BUILD" else -max_change)
    if target_inc_deg is not None and action != "HOLD":
        requested = float(target_inc_deg)
        if (action == "BUILD" and requested < inc) or (action == "DROP" and requested > inc):
            raise ValueError("Target inclination contradicts action.")
    effective = max(85.0, min(95.0, max(inc - max_change, min(inc + max_change, requested))))
    survey = pd.DataFrame({
        "md_ft": [0.0, step_ft], "inc_deg": [inc, effective],
        "azi_deg": [previous["azi_deg"], previous["azi_deg"]],
    })
    delta = compute_trajectory(survey).iloc[-1]
    result = {
        "md_ft": previous["md_ft"] + step_ft,
        "tvd_ft": previous["tvd_ft"] + float(delta.tvd_ft),
        "north_ft": previous["north_ft"] + float(delta.north_ft),
        "east_ft": previous["east_ft"] + float(delta.east_ft),
        "x_ft": previous["east_ft"] + float(delta.east_ft),
        "inc_deg": effective, "azi_deg": previous["azi_deg"],
        "dogleg_deg": float(delta.dogleg_deg),
        "dls_deg_per_100ft": float(delta.dls_deg_per_100ft),
    }
    if not all(math.isfinite(v) for v in result.values()):
        raise ValueError("Non-finite trajectory response.")
    return result, {
        "action": action, "requested_inc_deg": requested,
        "effective_inc_deg": effective, "clipped": abs(effective - requested) > 1e-9,
        "limit_reason": "inclination or dogleg bound" if abs(effective - requested) > 1e-9 else None,
    }
